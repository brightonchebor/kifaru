from rest_framework import generics, filters, status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from drf_yasg.utils import swagger_auto_schema
from django.db.models import Prefetch
from booking.models import Booking

from .models import Payment, PaymentTransaction
from .serializers import PaymentSerializer, PaymentCreateSerializer, RefundSerializer
from .customer_serializers import CustomerPaymentSerializer


class IsPaymentAdmin(BasePermission):
    message = "Only admins can manage payment records."

    def has_permission(self, request, view):
        user = request.user
        return bool(user.is_authenticated and (getattr(user, 'role', None) == 'admin' or user.is_superuser))


def payment_queryset():
    return Payment.objects.select_related(
        'booking__property', 'user', 'recorded_by', 'updated_by'
    ).prefetch_related('transactions')


class UserPaymentsView(generics.ListAPIView):
    """Read payment state for all bookings belonging to the current account.

    Includes unpaid bookings and free bookings before any payment record exists.
    No user/email query parameter can expand this account's scope.
    """
    serializer_class = CustomerPaymentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at', 'check_in']
    ordering = ['-created_at']
    pagination_class = PageNumberPagination
    http_method_names = ['get', 'head', 'options']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return Booking.objects.none()
        return Booking.objects.filter(user=self.request.user).select_related('property', 'payment').prefetch_related(
            Prefetch('payment__transactions', queryset=PaymentTransaction.objects.exclude(kind='legacy'),
                     to_attr='customer_transactions')
        )


class AdminPaymentListView(generics.ListAPIView):
    """List receipts and balances, including booking, guest and property details."""
    serializer_class = PaymentSerializer
    permission_classes = [IsPaymentAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['payment_status', 'payment_method', 'booking', 'currency']
    search_fields = ['transaction_id', 'booking__booking_reference', 'booking__full_name',
                     'booking__email', 'booking__phone', 'transactions__reference']
    ordering_fields = ['created_at', 'amount']
    ordering = ['-created_at']
    pagination_class = PageNumberPagination

    def get_queryset(self):
        return payment_queryset()


@method_decorator(name='post', decorator=swagger_auto_schema(responses={201: PaymentSerializer}))
class PaymentRecordView(generics.CreateAPIView):
    """Record one verified receipt. Repeating a booking adds an instalment to its history.

    amount is this receipt's amount. Status and remaining balance are calculated.
    Include a unique idempotency_key to safely retry the same request.
    """
    serializer_class = PaymentCreateSerializer
    permission_classes = [IsPaymentAdmin]


@method_decorator(name='patch', decorator=swagger_auto_schema(responses={200: PaymentSerializer}))
class PaymentDetailView(generics.RetrieveUpdateAPIView):
    """Read a payment summary or update notes / increase its cumulative amount.

    PATCH amount is the new cumulative received total; the increase becomes a new
    receipt. Booking links are immutable and refunds use the refunds endpoint.
    """
    permission_classes = [IsPaymentAdmin]
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_serializer_class(self):
        return PaymentSerializer if self.request.method == 'GET' else PaymentCreateSerializer

    def get_queryset(self):
        return payment_queryset()


class BookingPaymentView(generics.RetrieveAPIView):
    """Get a booking's payment summary and immutable receipt/refund history."""
    serializer_class = PaymentSerializer
    permission_classes = [IsPaymentAdmin]

    def get_object(self):
        return get_object_or_404(payment_queryset(), booking_id=self.kwargs['booking_id'])


@method_decorator(name='post', decorator=swagger_auto_schema(responses={201: PaymentSerializer}))
class PaymentRefundView(generics.CreateAPIView):
    """Record money actually returned for a cancelled booking, including partial refunds.

    Return the money externally first, then submit amount, payment_method,
    reference, notes and refund_confirmed=true. This endpoint does not transfer money.
    """
    serializer_class = RefundSerializer
    permission_classes = [IsPaymentAdmin]
    queryset = Payment.objects.none()  # Supplies model metadata for the path parameter in Swagger.

    def create(self, request, *args, **kwargs):
        payment = get_object_or_404(Payment, pk=self.kwargs['pk'])
        context = dict(self.get_serializer_context(), payment=payment)
        serializer = self.get_serializer(data=request.data, context=context)
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()
        return Response(PaymentSerializer(payment, context=context).data, status=status.HTTP_201_CREATED)
