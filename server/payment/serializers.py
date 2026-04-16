from rest_framework import serializers
from .models import Payment
from booking.models import Booking
from datetime import datetime, timedelta
from django.utils import timezone


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            'id', 'booking', 'payment_method', 'amount', 'currency',
            'card_number_last4', 'card_type', 'transaction_id',
            'payment_status', 'mpesa_receipt_number', 'mpesa_phone_number',
            'paystack_reference', 'paystack_access_code', 'authorization_url',
            'created_at', 'completed_at', 'failure_reason'
        ]
        read_only_fields = ['transaction_id', 'created_at', 'completed_at', 'user', 
                           'paystack_reference', 'paystack_access_code', 'authorization_url']


class PaymentInitializeSerializer(serializers.Serializer):
    """Serializer for initializing Paystack payment"""
    booking_id = serializers.IntegerField()
    callback_url = serializers.URLField(required=False, help_text="URL to redirect after payment")
    
    def validate_booking_id(self, value):
        try:
            booking = Booking.objects.get(id=value)
        except Booking.DoesNotExist:
            raise serializers.ValidationError("Booking does not exist.")
        
        # Check if payment already completed
        if hasattr(booking, 'payment') and booking.payment.payment_status == 'completed':
            raise serializers.ValidationError("Payment has already been completed for this booking.")
        
        return value
        
        return data