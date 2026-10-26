from rest_framework import generics, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings

from .models import Payment
from .serializers import PaymentSerializer, PaymentCreateSerializer
from booking.models import Booking
from users.utils import send_normal_email
import logging

logger = logging.getLogger(__name__)


def require_admin(user):
    if not user.is_authenticated or getattr(user, 'role', None) != 'admin':
        raise PermissionDenied("Only admins can perform this action.")


# ── Admin: List all payments ──────────────────────────────────────────────────

class AdminPaymentListView(generics.ListAPIView):
    """
    GET /api/admin/payments/   — List all payment records (admin only)

    Supports filtering by:
      ?payment_status=completed
      ?payment_method=mpesa
      ?booking=<booking_id>
    """
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['payment_status', 'payment_method']
    search_fields = ['transaction_id', 'booking__booking_reference', 'user__email',
                     'mpesa_receipt_number', 'bank_transfer_reference']
    ordering_fields = ['created_at', 'amount']
    ordering = ['-created_at']
    pagination_class = PageNumberPagination

    def get_queryset(self):
        require_admin(self.request.user)
        return Payment.objects.all().select_related('booking', 'user')


# ── Admin: Record a new payment ───────────────────────────────────────────────

class PaymentRecordView(generics.CreateAPIView):
    """
    POST /api/payments/record/   — Manually record a payment received (admin only)

    The owner calls this after a client sends money via bank transfer or M-Pesa.

    Example body (M-Pesa):
    {
        "booking": 42,
        "payment_method": "mpesa",
        "amount": "250.00",
        "currency": "EUR",
        "mpesa_receipt_number": "QHX7234ABC",
        "mpesa_phone_number": "+254712345678",
        "payment_status": "completed"
    }

    Example body (bank transfer with deposit):
    {
        "booking": 42,
        "payment_method": "bank_transfer",
        "amount": "250.00",
        "prepayment_amount": "250.00",
        "remaining_amount": "250.00",
        "bank_transfer_reference": "REF-2026-00123",
        "payment_status": "partial",
        "notes": "Client paid 50% deposit. Remaining due on arrival."
    }
    """
    serializer_class = PaymentCreateSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        require_admin(self.request.user)
        payment = serializer.save()

        # If payment is marked completed, confirm the booking automatically
        if payment.payment_status == 'completed':
            booking = payment.booking
            if booking.status != 'confirmed':
                booking.status = 'confirmed'
                if not payment.completed_at:
                    payment.completed_at = timezone.now()
                    payment.save(update_fields=['completed_at'])
                booking.save(update_fields=['status'])
                self._send_confirmation_email(booking, payment)

    def _send_confirmation_email(self, booking, payment):
        """Send booking confirmation email to the guest."""
        currency = payment.currency or getattr(settings, 'DEFAULT_CURRENCY', 'EUR')
        subject = f"Booking CONFIRMED — {booking.booking_reference}"
        message = (
            f"Dear {booking.full_name},\n\n"
            f"Great news! Your booking has been confirmed.\n\n"
            f"Booking Reference : {booking.booking_reference}\n"
            f"Property          : {booking.property.name}\n"
            f"Check-in          : {booking.check_in.strftime('%d %b %Y')}\n"
            f"Check-out         : {booking.check_out.strftime('%d %b %Y')}\n"
            f"Amount Paid       : {currency} {payment.amount}\n\n"
            f"We look forward to welcoming you!\n\n"
            f"Kind regards,\nThe {booking.property.name} Team"
        )
        send_normal_email({
            'email_body': message,
            'email_subject': subject,
            'to_email': booking.email,
        })


# ── Admin: Retrieve + Update a payment ───────────────────────────────────────

class PaymentDetailView(generics.RetrieveUpdateAPIView):
    """
    GET   /api/payments/<id>/   — Get a payment record (admin only)
    PATCH /api/payments/<id>/   — Update a payment record (e.g. mark completed)

    Common PATCH use cases:
      - Mark as completed:  { "payment_status": "completed", "completed_at": "2026-11-15T10:00:00Z" }
      - Record remainder:   { "remaining_amount": "0.00", "payment_status": "completed" }
      - Mark as refunded:   { "payment_status": "refunded", "notes": "Client cancelled" }
    """
    serializer_class = PaymentCreateSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        require_admin(self.request.user)
        return Payment.objects.all().select_related('booking', 'user')

    def perform_update(self, serializer):
        payment = serializer.save()
        # Auto-confirm booking when payment is marked completed
        if payment.payment_status == 'completed':
            booking = payment.booking
            if booking.status != 'confirmed':
                booking.status = 'confirmed'
                booking.save(update_fields=['status'])
                if not payment.completed_at:
                    Payment.objects.filter(pk=payment.pk).update(completed_at=timezone.now())


# ── Admin: Get payment by booking ─────────────────────────────────────────────

class BookingPaymentView(generics.RetrieveAPIView):
    """
    GET /api/payments/booking/<booking_id>/   — Get payment for a specific booking (admin only)
    """
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        require_admin(self.request.user)
        booking = get_object_or_404(Booking, pk=self.kwargs['booking_id'])
        return get_object_or_404(Payment, booking=booking)