from rest_framework import serializers
from .models import Booking
from properties.serializers import PropertySerializer
from payment.serializers import PaymentSerializer
from properties.models import Property
from datetime import datetime, timedelta
from django.utils import timezone





class BookingSerializer(serializers.ModelSerializer):
    property_details = PropertySerializer(source='property', read_only=True)
    payment = PaymentSerializer(read_only=True)
    property_name = serializers.CharField(source='property.name', read_only=True)
    property_location = serializers.CharField(source='property.location', read_only=True)
    
    class Meta:
        model = Booking
        fields = [
            'id', 'booking_reference', 'user', 'property', 'property_details',
            'property_name', 'property_location', 'full_name', 'email', 'phone',
            'accommodation_type', 'guest_type', 'check_in', 'check_out', 'guests',
            'number_of_adults', 'number_of_children', 'total_days', 'total_amount',
            'includes_breakfast', 'includes_fullboard', 'dog_included', 'jacuzzi_reservation',
            'status', 'special_requests', 'payment',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['booking_reference', 'total_days', 'total_amount', 'user', 'created_at', 'updated_at']
    
    def validate(self, data):
        check_in = data.get('check_in')
        check_out = data.get('check_out')
        property_obj = data.get('property')
        
        # Validate dates
        if check_in and check_out:
            if check_in >= check_out:
                raise serializers.ValidationError("Check-out date must be after check-in date.")
            
            # Check if check-in is in the past
            if check_in < timezone.now().date():
                raise serializers.ValidationError("Check-in date cannot be in the past.")
            
            # Check minimum nights requirement
            if property_obj:
                total_nights = (check_out - check_in).days
                if total_nights < property_obj.min_nights:
                    raise serializers.ValidationError(
                        f"This property requires a minimum of {property_obj.min_nights} night(s)."
                    )
            
            # Check property availability
            if property_obj:
                overlapping_bookings = Booking.objects.filter(
                    property=property_obj,
                    status__in=['pending', 'confirmed'],
                    check_in__lt=check_out,
                    check_out__gt=check_in
                )
                
                # Exclude current booking if updating
                if self.instance:
                    overlapping_bookings = overlapping_bookings.exclude(id=self.instance.id)
                
                if overlapping_bookings.exists():
                    raise serializers.ValidationError("Property is not available for the selected dates.")
        
        return data
    
    def create(self, validated_data):
        # Set user from request context
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class BookingCreateSerializer(serializers.Serializer):
    """Simplified serializer for creating a booking with payment"""
    property_id = serializers.IntegerField()
    full_name = serializers.CharField(max_length=200)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20)
    accommodation_type = serializers.ChoiceField(choices=['master_bedroom', 'single_bedroom', 'full_apartment'])
    guest_type = serializers.ChoiceField(choices=['international', 'local'], default='international')
    check_in = serializers.DateField()
    check_out = serializers.DateField()
    guests = serializers.IntegerField(min_value=1)
    number_of_adults = serializers.IntegerField(min_value=1, default=1)
    number_of_children = serializers.IntegerField(min_value=0, default=0)
    special_requests = serializers.CharField(required=False, allow_blank=True)
    dog_included = serializers.BooleanField(default=False)
    jacuzzi_reservation = serializers.BooleanField(default=False)
    
    # Payment details
    payment_method = serializers.ChoiceField(choices=['card', 'bank_transfer', 'mpesa', 'paypal'])
    
    # Card payment fields
    card_number = serializers.CharField(max_length=19, required=False)
    card_expiry = serializers.CharField(max_length=7, required=False)  # MM/YY
    card_cvv = serializers.CharField(max_length=4, required=False)
    
    # M-Pesa fields
    mpesa_phone = serializers.CharField(max_length=15, required=False)
    
    def validate(self, data):
        # Validate property exists
        try:
            property_obj = Property.objects.get(id=data['property_id'])
            data['property'] = property_obj
        except Property.DoesNotExist:
            raise serializers.ValidationError("Property does not exist.")
        
        # Validate dates
        check_in = data['check_in']
        check_out = data['check_out']
        
        if check_in >= check_out:
            raise serializers.ValidationError("Check-out date must be after check-in date.")
        
        if check_in < timezone.now().date():
            raise serializers.ValidationError("Check-in date cannot be in the past.")
        
        # Validate payment method specific fields
        if data['payment_method'] == 'card':
            if not all([data.get('card_number'), data.get('card_expiry'), data.get('card_cvv')]):
                raise serializers.ValidationError("Card payment requires card_number, card_expiry, and card_cvv.")
        
        if data['payment_method'] == 'mpesa':
            if not data.get('mpesa_phone'):
                raise serializers.ValidationError("M-Pesa payment requires mpesa_phone.")
        
        return data


