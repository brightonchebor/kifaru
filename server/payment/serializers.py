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
            'created_at', 'completed_at', 'failure_reason'
        ]
        read_only_fields = ['transaction_id', 'created_at', 'completed_at', 'user']
        

class PaymentProcessSerializer(serializers.Serializer):
    """Serializer for processing payment for an existing booking"""
    booking_id = serializers.IntegerField()
    payment_method = serializers.ChoiceField(choices=['card', 'bank', 'mpesa'])
    
    # Card payment fields
    card_number = serializers.CharField(max_length=19, required=False)
    card_expiry = serializers.CharField(max_length=7, required=False)
    card_cvv = serializers.CharField(max_length=4, required=False)
    
    # M-Pesa fields
    mpesa_phone = serializers.CharField(max_length=15, required=False)
    
    def validate(self, data):
        # Validate booking exists
        try:
            booking = Booking.objects.get(id=data['booking_id'])
            data['booking'] = booking
        except Booking.DoesNotExist:
            raise serializers.ValidationError("Booking does not exist.")
        
        # Check if payment already exists
        if hasattr(booking, 'payment') and booking.payment.payment_status == 'completed':
            raise serializers.ValidationError("Payment has already been completed for this booking.")
        
        # Validate payment method specific fields
        if data['payment_method'] == 'card':
            if not all([data.get('card_number'), data.get('card_expiry'), data.get('card_cvv')]):
                raise serializers.ValidationError("Card payment requires card_number, card_expiry, and card_cvv.")
        
        if data['payment_method'] == 'mpesa':
            if not data.get('mpesa_phone'):
                raise serializers.ValidationError("M-Pesa payment requires mpesa_phone.")
        
        return data