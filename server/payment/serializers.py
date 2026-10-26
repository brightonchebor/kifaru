from rest_framework import serializers
from .models import Payment
from booking.models import Booking


class PaymentSerializer(serializers.ModelSerializer):
    """
    Read-only serializer used to embed payment info inside booking responses.
    """
    class Meta:
        model = Payment
        fields = [
            'id', 'transaction_id', 'payment_method', 'amount', 'currency',
            'prepayment_amount', 'remaining_amount',
            'bank_transfer_reference', 'mpesa_receipt_number', 'mpesa_phone_number',
            'payment_status', 'notes',
            'created_at', 'completed_at',
        ]
        read_only_fields = fields


class PaymentCreateSerializer(serializers.ModelSerializer):
    """
    Admin serializer for manually recording a payment received from a client.
    The owner fills this in after the client transfers money.
    """
    class Meta:
        model = Payment
        fields = [
            'booking', 'payment_method', 'amount', 'currency',
            'prepayment_amount', 'remaining_amount',
            'bank_transfer_reference', 'mpesa_receipt_number', 'mpesa_phone_number',
            'payment_status', 'notes', 'completed_at',
        ]

    def validate(self, attrs):
        booking = attrs.get('booking')
        # Prevent double-recording a payment for the same booking
        if self.instance is None:  # only on create
            if hasattr(booking, 'payment'):
                raise serializers.ValidationError({
                    'booking': (
                        f'A payment record already exists for booking '
                        f'{booking.booking_reference}. Edit the existing record instead.'
                    )
                })
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['user'] = request.user
        return super().create(validated_data)