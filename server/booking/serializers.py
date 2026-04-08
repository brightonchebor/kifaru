from rest_framework import serializers
from .models import Booking, BlockedDate
from payment.serializers import PaymentSerializer
from properties.models import Property
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import models
import phonenumbers
from phonenumbers import geocoder


class PropertyBasicSerializer(serializers.ModelSerializer):
    """Lightweight property serializer for booking responses"""
    background_image = serializers.SerializerMethodField()
    
    class Meta:
        model = Property
        fields = ['id', 'name', 'slug', 'location', 'country', 'background_image', 'property_category']
    
    def get_background_image(self, obj):
        if obj.background_image:
            return obj.background_image.url
        return None


class BookingListSerializer(serializers.ModelSerializer):
    """Simplified serializer for booking list view - less data"""
    property_name = serializers.CharField(source='property.name', read_only=True)
    property_location = serializers.CharField(source='property.location', read_only=True)
    property_image = serializers.SerializerMethodField()
    # payment_status = serializers.SerializerMethodField()
    
    class Meta:
        model = Booking
        fields = [
            'id', 'booking_reference', 'property_name', 'property_location', 'property_image',
            'check_in', 'check_out', 'total_days', 'total_amount',
            'accommodation_type', 'guest_type', 'stay_type',
            'number_of_guests', 'number_of_adults', 'number_of_children',
            'full_name', 'email', 'phone',
            'status', 'created_at'
        ]
    
    def get_property_image(self, obj):
        if obj.property.background_image:
            return obj.property.background_image.url
        return None
    
    def get_payment_status(self, obj):
        if hasattr(obj, 'payment'):
            return obj.payment.payment_status
        return None





class BookingCreateRequestSerializer(serializers.ModelSerializer):
    """Serializer for creating bookings - only writable fields"""
    # Make personal details writable for guest bookings
    full_name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    
    class Meta:
        model = Booking
        fields = [
            'property', 'accommodation_type', 'check_in', 'check_out',
            'number_of_guests', 'number_of_adults', 'number_of_children',
            'full_name', 'email', 'phone', 'id_passport_number',
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
        
        # Get user if authenticated
        user = self.context['request'].user
        is_authenticated = user and user.is_authenticated
        
        # For guest bookings, validate required personal details are provided
        if not is_authenticated:
            if not data.get('full_name'):
                raise serializers.ValidationError({
                    'full_name': 'Full name is required for guest bookings.'
                })
            if not data.get('email'):
                raise serializers.ValidationError({
                    'email': 'Email is required for guest bookings.'
                })
            if not data.get('phone'):
                raise serializers.ValidationError({
                    'phone': 'Phone number is required for guest bookings.'
                })
        
        # For authenticated users without required profile info
        if is_authenticated:
            if not user.phone_number and not data.get('phone'):
                raise serializers.ValidationError(
                    "Please add your phone number to your profile or provide it in the booking."
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
                # Check for overlapping bookings
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
                    booking_refs = ', '.join(overlapping_bookings.values_list('booking_reference', flat=True))
                    raise serializers.ValidationError(
                        f"Property is not available for the selected dates. "
                        f"Conflicting booking(s): {booking_refs}"
                    )
                
                # Check for blocked dates
                blocked_dates = BlockedDate.objects.filter(
                    property=property_obj,
                    start_date__lt=check_out,
                    end_date__gt=check_in
                )
                
                if blocked_dates.exists():
                    reasons = ', '.join(blocked_dates.values_list('reason', flat=True))
                    raise serializers.ValidationError(
                        f"Property is blocked for the selected dates. Reason(s): {reasons}"
                    )
                
                # Buffer day check: prevent same-day checkout/checkin
                # Check if someone is checking out on our check-in day
                same_day_checkout = Booking.objects.filter(
                    property=property_obj,
                    status__in=['pending', 'confirmed'],
                    check_out=check_in
                )
                
                if self.instance:
                    same_day_checkout = same_day_checkout.exclude(id=self.instance.id)
                
                if same_day_checkout.exists():
                    raise serializers.ValidationError(
                        f"Cannot check in on {check_in}. Another guest is checking out on this date. "
                        "Please select the next day for check-in."
                    )
                
                # Validate pricing exists for this booking
                total_nights = (check_out - check_in).days
                
                # Determine stay_type intelligently
                # Check if property has weekly pricing and if nights is a multiple of 7
                from properties.models import PropertyPricing
                has_weekly_pricing = PropertyPricing.objects.filter(
                    property=property_obj,
                    accommodation_type=accommodation_type,
                    stay_type='weekly'
                ).exists()
                
                if total_nights % 7 == 0 and has_weekly_pricing:
                    # Multiples of 7 (7, 14, 21, 28...) use weekly pricing if available
                    stay_type = 'weekly'
                elif total_nights >= 10:
                    stay_type = 'long_term'
                elif total_nights < 7:
                    stay_type = 'short_term'
                else:
                    # 8 or 9 nights - check what's available
                    stay_type = 'short_term'
                
                # Determine guest_type
                if is_authenticated and user.country_of_residence:
                    user_country = user.country_of_residence.lower()
                    property_country = property_obj.country.lower()
                    guest_type = 'local' if user_country == property_country else 'international'
                else:
                    # For guest bookings, determine from phone number
                    guest_type = 'international'  # Default
                    phone = data.get('phone', '')
                    if phone:
                        try:
                            parsed = phonenumbers.parse(phone, None)
                            if not phonenumbers.is_valid_number(parsed):
                                raise serializers.ValidationError({
                                    'phone': 'Please provide a valid phone number with country code (e.g., +254712345678).'
                                })
                            
                            phone_country = geocoder.description_for_number(parsed, "en")
                            if phone_country:
                                property_country = property_obj.country.lower()
                                # Compare phone country with property country
                                if phone_country.lower() == property_country:
                                    guest_type = 'local'
                        except phonenumbers.NumberParseException:
                            raise serializers.ValidationError({
                                'phone': 'Invalid phone number format. Please include country code (e.g., +254712345678).'
                            })
                
                # Check if pricing exists (try specific guest_type first, then 'all_guests')
                # First try exact guest_type match
                pricing_query = PropertyPricing.objects.filter(
                    property=property_obj,
                    accommodation_type=accommodation_type,
                    guest_type=guest_type,
                    stay_type=stay_type,
                    min_nights__lte=total_nights
                ).filter(
                    models.Q(max_nights__isnull=True) | models.Q(max_nights__gte=total_nights)
                )
                
                # If no match, try 'all'
                if not pricing_query.exists():
                    pricing_query = PropertyPricing.objects.filter(
                        property=property_obj,
                        accommodation_type=accommodation_type,
                        guest_type='all',
                        stay_type=stay_type,
                        min_nights__lte=total_nights
                    ).filter(
                        models.Q(max_nights__isnull=True) | models.Q(max_nights__gte=total_nights)
                    )
                
                if number_of_guests:
                    # Check if accommodation can accommodate this many guests
                    pricing_with_capacity = pricing_query.filter(
                        models.Q(number_of_guests__gte=number_of_guests) | 
                        models.Q(number_of_guests__isnull=True)
                    )
                    
                    if pricing_with_capacity.exists():
                        pricing_exists = True
                    else:
                        # Check max capacity for this accommodation type
                        max_capacity = PropertyPricing.objects.filter(
                            property=property_obj,
                            accommodation_type=accommodation_type,
                            stay_type=stay_type
                        ).aggregate(models.Max('number_of_guests'))['number_of_guests__max']
                        
                        if max_capacity and number_of_guests > max_capacity:
                            raise serializers.ValidationError({
                                'number_of_guests': f'{accommodation_type.replace("_", " ").title()} accommodates maximum {max_capacity} guest(s). You requested {number_of_guests} guest(s).'
                            })
                        pricing_exists = False
                else:
                    pricing_exists = pricing_query.exists()
                
                if not pricing_exists:
                    # Detailed error checking to provide helpful messages
                    
                    # 1. Check if the accommodation type exists at all for this property
                    accommodation_exists = PropertyPricing.objects.filter(
                        property=property_obj,
                        accommodation_type=accommodation_type
                    ).exists()
                    
                    if not accommodation_exists:
                        # Accommodation type doesn't exist - show available options
                        available_accommodations = PropertyPricing.objects.filter(
                            property=property_obj
                        ).values_list('accommodation_type', flat=True).distinct()
                        
                        # Make accommodation names more readable
                        accommodation_display = {
                            'master_bedroom': 'Master Bedroom',
                            'full_apartment': 'Full Apartment'
                        }
                        
                        available_names = [accommodation_display.get(acc, acc.replace('_', ' ').title()) 
                                          for acc in available_accommodations]
                        
                        raise serializers.ValidationError({
                            'success': False,
                            'error_type': 'accommodation_unavailable',
                            'message': f'Sorry! {property_obj.name} does not offer {accommodation_display.get(accommodation_type, accommodation_type)} accommodation.',
                            'suggestion': f'This property offers: {", ".join(available_names)}. Would you like to select one of these instead?',
                            'details': {
                                'property_name': property_obj.name,
                                'requested': accommodation_type,
                                'available_options': list(available_accommodations)
                            }
                        })
                    
                    # 2. Check if min_nights requirement is not met
                    min_nights_pricing = PropertyPricing.objects.filter(
                        property=property_obj,
                        accommodation_type=accommodation_type
                    ).aggregate(models.Min('min_nights'))['min_nights__min']
                    
                    if min_nights_pricing and total_nights < min_nights_pricing:
                        accommodation_display = {
                            'master_bedroom': 'Master Bedroom',
                            'full_apartment': 'Full Apartment'
                        }
                        raise serializers.ValidationError({
                            'success': False,
                            'error_type': 'minimum_nights_not_met',
                            'message': f'{accommodation_display.get(accommodation_type, accommodation_type.replace("_", " ").title())} at {property_obj.name} requires a minimum of {min_nights_pricing} night(s).',
                            'suggestion': f'Your booking is for {total_nights} night(s). Please extend your stay to at least {min_nights_pricing} night(s).',
                            'details': {
                                'property_name': property_obj.name,
                                'accommodation_type': accommodation_type,
                                'min_nights_required': min_nights_pricing,
                                'requested_nights': total_nights
                            }
                        })
                    
                    # 3. Check if max_nights is exceeded for available pricing
                    max_nights_pricing = PropertyPricing.objects.filter(
                        property=property_obj,
                        accommodation_type=accommodation_type,
                        min_nights__lte=total_nights
                    ).exclude(max_nights__isnull=True).aggregate(
                        models.Max('max_nights')
                    )['max_nights__max']
                    
                    # Check if there's any pricing without max_nights restriction
                    has_unlimited = PropertyPricing.objects.filter(
                        property=property_obj,
                        accommodation_type=accommodation_type,
                        max_nights__isnull=True
                    ).exists()
                    
                    if max_nights_pricing and not has_unlimited and total_nights > max_nights_pricing:
                        accommodation_display = {
                            'master_bedroom': 'Master Bedroom',
                            'full_apartment': 'Full Apartment'
                        }
                        raise serializers.ValidationError({
                            'success': False,
                            'error_type': 'maximum_nights_exceeded',
                            'message': f'{accommodation_display.get(accommodation_type, accommodation_type.replace("_", " ").title())} at {property_obj.name} allows a maximum of {max_nights_pricing} night(s) for this booking type.',
                            'suggestion': f'Your booking is for {total_nights} night(s). Please reduce your stay to {max_nights_pricing} night(s) or less, or contact the property for longer stays.',
                            'details': {
                                'property_name': property_obj.name,
                                'accommodation_type': accommodation_type,
                                'max_nights_allowed': max_nights_pricing,
                                'requested_nights': total_nights
                            }
                        })
                    
                    # 3. Check what stay types are available (without guest_type filter)
                    available_stay_types = PropertyPricing.objects.filter(
                        property=property_obj,
                        accommodation_type=accommodation_type
                    ).values_list('stay_type', flat=True).distinct()
                    
                    # Check if the issue is stay_type/duration mismatch
                    if available_stay_types and stay_type not in available_stay_types:
                        # Build helpful suggestions based on available stay types
                        stay_type_info = {
                            'short_term': 'less than 7 nights',
                            'weekly': 'exactly 7 nights or multiples of 7 (7, 14, 21 nights)',
                            'long_term': '10 or more nights'
                        }
                        
                        suggestions = [stay_type_info.get(st, st) for st in available_stay_types]
                        
                        raise serializers.ValidationError({
                            'success': False,
                            'error_type': 'invalid_stay_duration',
                            'message': f'Sorry! This accommodation requires bookings of {", or ".join(suggestions)}.',
                            'suggestion': f'Your {total_nights}-night booking doesn\'t match the available options. Please adjust your dates.',
                            'details': {
                                'property_name': property_obj.name,
                                'your_nights': total_nights,
                                'your_stay_type': stay_type,
                                'available_stay_types': list(available_stay_types),
                                'accommodation_type': accommodation_type
                            }
                        })
                    
                    # 4. Check if guest_type pricing exists
                    available_for_all = PropertyPricing.objects.filter(
                        property=property_obj,
                        accommodation_type=accommodation_type,
                        guest_type='all'
                    ).exists()
                    
                    if not available_for_all:
                        guest_type_available = PropertyPricing.objects.filter(
                            property=property_obj,
                            accommodation_type=accommodation_type,
                            guest_type=guest_type
                        ).exists()
                        
                        if not guest_type_available:
                            raise serializers.ValidationError({
                                'success': False,
                                'error_type': 'guest_type_not_supported',
                                'message': f'Sorry! This property does not accept {guest_type} guests for {accommodation_type}.',
                                'suggestion': 'Please contact the property manager or try a different property.',
                                'details': {
                                    'property_name': property_obj.name,
                                    'property_country': property_obj.country,
                                    'user_country': getattr(user, 'country_of_residence', None) if is_authenticated else None,
                                    'guest_type': guest_type,
                                    'accommodation_type': accommodation_type
                                }
                            })
                    
                    # Generic pricing not available error
                    raise serializers.ValidationError({
                        'success': False,
                        'error_type': 'pricing_not_available',
                        'message': f'Sorry! No pricing available for your requested booking configuration.',
                        'suggestion': 'Please try different dates or number of guests.',
                        'details': {
                            'property_name': property_obj.name,
                            'nights': total_nights,
                            'accommodation_type': accommodation_type,
                            'stay_type': stay_type
                        }
                    })
        
        return data
    
    def create(self, validated_data):
        # Get user if authenticated
        user = self.context['request'].user
        is_authenticated = user and user.is_authenticated
        
        if is_authenticated:
            # For authenticated users, link to user account
            validated_data['user'] = user
            # Auto-fill from profile if not provided in request
            if not validated_data.get('full_name'):
                validated_data['full_name'] = user.get_full_name()
            if not validated_data.get('email'):
                validated_data['email'] = user.email
            if not validated_data.get('phone'):
                validated_data['phone'] = user.phone_number
        else:
            # For guest bookings, user field is null
            validated_data['user'] = None
            # Personal details already validated to be present
        
        return super().create(validated_data)


class BookingSerializer(serializers.ModelSerializer):
    """Complete serializer for reading bookings - includes all calculated fields"""
    property_details = PropertyBasicSerializer(source='property', read_only=True)
    payment = PaymentSerializer(read_only=True)
    property_name = serializers.CharField(source='property.name', read_only=True)
    property_location = serializers.CharField(source='property.location', read_only=True)
    pricing_breakdown = serializers.SerializerMethodField()
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    
    class Meta:
        model = Booking
        fields = [
            'id', 'booking_reference', 'user', 'user_name', 'user_email',
            'property', 'property_details', 'property_name', 'property_location',
            'full_name', 'email', 'phone', 'id_passport_number',
            'accommodation_type', 'guest_type', 'stay_type', 'check_in', 'check_out',
            'number_of_guests', 'number_of_adults', 'number_of_children',
            'total_days', 'total_amount', 'pricing_breakdown',
            'includes_breakfast', 'includes_fullboard', 'dog_included', 'jacuzzi_reservation',
            'status', 'special_requests', 'payment',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'booking_reference', 'total_days', 'total_amount', 'user', 
            'user_name', 'user_email', 'stay_type', 'includes_breakfast', 'includes_fullboard', 
            'created_at', 'updated_at', 'property_details', 'payment', 
            'property_name', 'property_location', 'pricing_breakdown'
        ]
    
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


class BlockedDateSerializer(serializers.ModelSerializer):
    """Serializer for blocked dates"""
    property_name = serializers.CharField(source='property.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    
    class Meta:
        model = BlockedDate
        fields = ['id', 'property', 'property_name', 'start_date', 'end_date', 'reason', 
                  'created_by', 'created_by_name', 'created_at']
        read_only_fields = ['id', 'created_by', 'created_at', 'property_name', 'created_by_name']
    
    def validate(self, data):
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if start_date and end_date:
            if end_date <= start_date:
                raise serializers.ValidationError("End date must be after start date.")
        
        return data


class CalendarEventSerializer(serializers.Serializer):
    """Serializer for calendar events (bookings and blocked dates)"""
    type = serializers.ChoiceField(choices=['booking', 'blocked'])
    id = serializers.IntegerField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    title = serializers.CharField()
    status = serializers.CharField(required=False)
    booking_reference = serializers.CharField(required=False)
    guest_name = serializers.CharField(required=False)
    reason = serializers.CharField(required=False)


class AvailabilityDetailSerializer(serializers.Serializer):
    """Detailed availability response with conflict information"""
    property_id = serializers.IntegerField()
    property_name = serializers.CharField()
    check_in = serializers.DateField()
    check_out = serializers.DateField()
    is_available = serializers.BooleanField()
    total_nights = serializers.IntegerField()
    conflicting_bookings = serializers.ListField(child=serializers.DictField(), required=False)
    blocked_dates = serializers.ListField(child=serializers.DictField(), required=False)
    buffer_conflicts = serializers.ListField(child=serializers.DictField(), required=False)
    unavailable_dates = serializers.ListField(child=serializers.DateField(), required=False)
