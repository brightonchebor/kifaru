from django.utils import timezone
from decimal import Decimal
from rest_framework import serializers

from booking.models import Booking
from .models import Payment, PaymentTransaction
from .services import record_receipt, record_refund


class PaymentTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentTransaction
        fields = ['id', 'transaction_id', 'kind', 'amount', 'currency', 'payment_method',
                  'reference', 'recorded_by', 'occurred_at', 'created_at', 'notes']
        read_only_fields = fields


class PaymentSerializer(serializers.ModelSerializer):
    booking_reference = serializers.CharField(source='booking.booking_reference', read_only=True)
    guest_name = serializers.CharField(source='booking.full_name', read_only=True)
    guest_email = serializers.EmailField(source='booking.email', read_only=True)
    guest_phone = serializers.CharField(source='booking.phone', read_only=True)
    property_name = serializers.CharField(source='booking.property.name', read_only=True)
    booking_status = serializers.CharField(source='booking.status', read_only=True)
    booking_total = serializers.DecimalField(source='booking.total_amount', max_digits=10, decimal_places=2, read_only=True)
    net_received = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    refundable_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    transactions = PaymentTransactionSerializer(many=True, read_only=True)

    class Meta:
        model = Payment
        fields = [
            'id', 'transaction_id', 'booking', 'booking_reference', 'booking_status', 'booking_total',
            'guest_name', 'guest_email', 'guest_phone', 'property_name', 'user',
            'recorded_by', 'updated_by', 'payment_method', 'amount', 'currency',
            'prepayment_amount', 'remaining_amount', 'refunded_amount', 'net_received', 'refundable_amount',
            'bank_transfer_reference', 'mpesa_receipt_number', 'mpesa_phone_number',
            'payment_status', 'notes', 'created_at', 'updated_at', 'completed_at', 'transactions',
        ]
        read_only_fields = fields


class TransactionInputSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))
    currency = serializers.CharField(max_length=3, required=False)
    payment_method = serializers.ChoiceField(choices=Payment.PAYMENT_METHOD_CHOICES, required=False)
    bank_transfer_reference = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    mpesa_receipt_number = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    mpesa_phone_number = serializers.CharField(max_length=15, required=False, allow_blank=True, allow_null=True)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    occurred_at = serializers.DateTimeField(required=False)
    idempotency_key = serializers.UUIDField(required=False)

    def validate_occurred_at(self, value):
        if value > timezone.now():
            raise serializers.ValidationError('A recorded transfer cannot be dated in the future.')
        return value

    def to_representation(self, instance):
        return PaymentSerializer(instance, context=self.context).data


class PaymentCreateSerializer(TransactionInputSerializer):
    booking = serializers.PrimaryKeyRelatedField(queryset=Booking.objects.all())
    payment_method = serializers.ChoiceField(choices=Payment.PAYMENT_METHOD_CHOICES)
    payment_status = serializers.ChoiceField(choices=Payment.PAYMENT_STATUS_CHOICES, required=False)
    prepayment_amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False, allow_null=True)
    remaining_amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False, allow_null=True)

    def validate(self, attrs):
        if 'completed_at' in self.initial_data:
            raise serializers.ValidationError({'completed_at': 'Managed automatically; use occurred_at for the transfer date.'})
        if self.instance and 'booking' in attrs and attrs['booking'].pk != self.instance.booking_id:
            raise serializers.ValidationError({'booking': 'A payment cannot be moved to another booking.'})
        return attrs

    def create(self, validated_data):
        booking = validated_data.pop('booking')
        return record_receipt(booking.pk, self.context['request'].user, validated_data)

    def update(self, instance, validated_data):
        validated_data.pop('booking', None)
        return record_receipt(instance.booking_id, self.context['request'].user, validated_data,
                              payment_id=instance.pk, cumulative=True)


class RefundSerializer(TransactionInputSerializer):
    refund_confirmed = serializers.BooleanField(required=True)

    def create(self, validated_data):
        return record_refund(self.context['payment'].pk, self.context['request'].user, validated_data)
