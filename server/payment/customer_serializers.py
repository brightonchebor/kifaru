"""Customer-facing payment state, including bookings without a payment record."""

from decimal import Decimal

from drf_yasg.utils import swagger_serializer_method
from rest_framework import serializers

from booking.models import Booking
from .models import Payment, PaymentTransaction
from .services import booking_currency


def payment_snapshot(booking):
    payment = getattr(booking, 'payment', None)
    received = payment.amount if payment else Decimal('0.00')
    refunded = payment.refunded_amount if payment else Decimal('0.00')
    net = received - refunded
    if payment and (received > 0 or payment.payment_status != 'pending'):
        state = payment.payment_status
    elif booking.status == 'cancelled':
        state = 'cancelled'
    elif booking.total_amount == 0:
        state = 'not_required'
    else:
        state = 'pending'
    balance = (Decimal('0.00') if booking.status == 'cancelled'
               else max(booking.total_amount - net, Decimal('0.00')))
    return {
        'payment_id': payment.pk if payment else None,
        'payment_status': state,
        'currency': payment.currency if payment else booking_currency(),
        'amount_paid': f'{received:.2f}',
        'refunded_amount': f'{refunded:.2f}',
        'net_received': f'{net:.2f}',
        'remaining_amount': f'{balance:.2f}',
    }


class BookingPaymentFieldsMixin(serializers.Serializer):
    payment_id = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    amount_paid = serializers.SerializerMethodField()
    refunded_amount = serializers.SerializerMethodField()
    net_received = serializers.SerializerMethodField()
    remaining_amount = serializers.SerializerMethodField()

    @swagger_serializer_method(serializer_or_field=serializers.IntegerField(allow_null=True))
    def get_payment_id(self, obj):
        return payment_snapshot(obj)['payment_id']

    @swagger_serializer_method(serializer_or_field=serializers.ChoiceField(
        choices=Payment.PAYMENT_STATUS_CHOICES + [('not_required', 'No payment required'), ('cancelled', 'Cancelled')]
    ))
    def get_payment_status(self, obj) -> str:
        return payment_snapshot(obj)['payment_status']

    def get_currency(self, obj) -> str:
        return payment_snapshot(obj)['currency']

    def get_amount_paid(self, obj) -> str:
        return payment_snapshot(obj)['amount_paid']

    def get_refunded_amount(self, obj) -> str:
        return payment_snapshot(obj)['refunded_amount']

    def get_net_received(self, obj) -> str:
        return payment_snapshot(obj)['net_received']

    def get_remaining_amount(self, obj) -> str:
        return payment_snapshot(obj)['remaining_amount']


class CustomerTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentTransaction
        fields = ['id', 'transaction_id', 'kind', 'amount', 'currency', 'payment_method',
                  'reference', 'occurred_at', 'created_at']
        read_only_fields = fields


class CustomerPaymentSerializer(BookingPaymentFieldsMixin, serializers.ModelSerializer):
    booking = serializers.IntegerField(source='pk', read_only=True)
    booking_status = serializers.CharField(source='status', read_only=True)
    property_name = serializers.CharField(source='property.name', read_only=True)
    transactions = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = ['booking', 'booking_reference', 'booking_status', 'property', 'property_name',
                  'check_in', 'check_out', 'created_at', 'original_amount', 'discount_amount', 'total_amount',
                  'payment_id', 'payment_status', 'currency', 'amount_paid', 'refunded_amount',
                  'net_received', 'remaining_amount', 'transactions']
        read_only_fields = fields

    @swagger_serializer_method(serializer_or_field=CustomerTransactionSerializer(many=True))
    def get_transactions(self, obj):
        payment = getattr(obj, 'payment', None)
        if payment is None:
            return []
        entries = getattr(payment, 'customer_transactions', None)
        if entries is None:
            entries = [entry for entry in payment.transactions.all() if entry.kind != 'legacy']
        return CustomerTransactionSerializer(entries, many=True).data
