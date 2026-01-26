from rest_framework import serializers
from .models import Booking
from properties.serializers import PropertySerializer
from payment.serializers import PaymentSerializer
from properties.models import Property
from datetime import datetime, timedelta
from django.utils import timezone





class BookingCreateRequestSerializer(serializers.ModelSerializer):
    """Serializer for creating bookings - only writable fields"""
    class Meta:
        model = Booking
        fields = [
            'property', 'accommodation_type', 'check_in', 'check_out',
            'number_of_guests', 'number_of_adults', 'number_of_children',
            'dog_included', 'jacuzzi_reservation', 'special_requests'
        ]
    
    def validate(self, data):
        check_in = data.get('check_in')
        check_out = data.get('check_out')
        property_obj = data.get('property')
        accommodation_type = data.get('accommodation_type')
        number_of_guests = data.get('number_of_guests')
        number_of_adults = data.get('number_of_adults')
        number_of_children = data.get('number_of_children')
        dog_included = data.get('dog_included', False)
        
        # Validate user has country_of_residence set
        user = self.context['request'].user
        if not user.country_of_residence:
            raise serializers.ValidationError(
                "Please add your country of residence to your profile before booking. "
                "This is required to determine the correct pricing."
            )
        
        # Validate user has phone number
        if not user.phone_number:
            raise serializers.ValidationError(
                "Please add your phone number to your profile before booking."
            )
        
        # Validate guest numbers match
        if number_of_adults and number_of_children:
            if number_of_adults + number_of_children != number_of_guests:
                raise serializers.ValidationError(
                    f"Number of adults ({number_of_adults}) + children ({number_of_children}) "
                    f"must equal total guests ({number_of_guests})."
                )
        
        # Validate against property max_guests
        if property_obj and property_obj.max_guests and number_of_guests:
            if number_of_guests > property_obj.max_guests:
                raise serializers.ValidationError(
                    f"This property has a maximum capacity of {property_obj.max_guests} guest(s). "
                    f"You requested {number_of_guests} guest(s)."
                )
        
        # Validate dog only allowed for North Sea property
        if dog_included and property_obj:
            if 'North-Sea' not in property_obj.name:
                raise serializers.ValidationError(
                    "Dogs are only allowed at Ocean Kifaru North-Sea property."
                )
        
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
        # Auto-fill user info from authenticated user profile
        user = self.context['request'].user
        validated_data['user'] = user
        validated_data['full_name'] = user.get_full_name
        validated_data['email'] = user.email
        validated_data['phone'] = user.phone_number
        return super().create(validated_data)


class BookingSerializer(serializers.ModelSerializer):
    """Complete serializer for reading bookings - includes all calculated fields"""
    property_details = PropertySerializer(source='property', read_only=True)
    payment = PaymentSerializer(read_only=True)
    property_name = serializers.CharField(source='property.name', read_only=True)
    property_location = serializers.CharField(source='property.location', read_only=True)
    pricing_breakdown = serializers.SerializerMethodField()
    
    class Meta:
        model = Booking
        fields = [
            'id', 'booking_reference', 'user', 'property', 'property_details',
            'property_name', 'property_location', 'full_name', 'email', 'phone',
            'accommodation_type', 'guest_type', 'stay_type', 'check_in', 'check_out',
            'number_of_guests', 'number_of_adults', 'number_of_children',
            'total_days', 'total_amount', 'selected_pricing', 'pricing_breakdown',
            'includes_breakfast', 'includes_fullboard', 'dog_included', 'jacuzzi_reservation',
            'status', 'special_requests', 'payment',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'booking_reference', 'total_days', 'total_amount', 'user', 'stay_type', 'selected_pricing', 'includes_breakfast', 'includes_fullboard', 'created_at', 'updated_at', 'property_details', 'payment', 'property_name', 'property_location', 'pricing_breakdown']
    
    def get_pricing_breakdown(self, obj):
        """Return detailed pricing information"""
        if obj.selected_pricing:
            return {
                'price_per_night': str(obj.selected_pricing.price_per_night),
                'weekly_price': str(obj.selected_pricing.weekly_price) if obj.selected_pricing.weekly_price else None,
                'total_nights': obj.total_days,
                'total_amount': str(obj.total_amount),
                'includes_breakfast': obj.includes_breakfast,
                'includes_fullboard': obj.includes_fullboard,
            }
        return None

class PriceCalculationSerializer(serializers.Serializer):
    """Serializer for pricing calculation response"""
    guest_type = serializers.CharField()
    stay_type = serializers.CharField()
    price_per_night = serializers.DecimalField(max_digits=10, decimal_places=2)
    weekly_price = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    total_nights = serializers.IntegerField()
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    includes_breakfast = serializers.BooleanField()
    includes_fullboard = serializers.BooleanField()
    property_name = serializers.CharField()
    accommodation_type = serializers.CharField()

