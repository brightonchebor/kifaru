from rest_framework import generics, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import datetime, timedelta
import phonenumbers
from phonenumbers import geocoder
from .models import Booking, BlockedDate
from payment.models import Payment
from .serializers import (
    BookingSerializer, 
    BookingListSerializer,
    BookingCreateRequestSerializer,
    PriceCalculationSerializer,
    BlockedDateSerializer,
    CalendarEventSerializer,
    AvailabilityDetailSerializer,
)
from properties.models import Property, PropertyPricing
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from decimal import Decimal
from django.db import models as django_models

class BookingListCreateView(generics.ListCreateAPIView):
    """
    List bookings (role-based) and create new bookings.
    
    GET: Returns bookings based on user role (authentication required):
        - Admin: All bookings from all users
        - Staff: Bookings from their assigned properties only
        - Regular users: Only their own bookings
    
    POST: Create a new booking (no authentication required for guests)
        - Authenticated users: Auto-fill details from profile, link to user account
        - Guest users: Must provide full_name, email, phone manually
    
    Features: Filtering, search, ordering, pagination
    Use /bookings/my-bookings/ for guaranteed personal bookings only
    """
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'property']
    search_fields = ['booking_reference', 'full_name', 'email']
    ordering_fields = ['created_at', 'check_in', 'total_amount']
    ordering = ['-created_at']
    pagination_class = PageNumberPagination
    
    def get_permissions(self):
        """Allow guest bookings (POST without auth), require auth for listing (GET)"""
        if self.request.method == 'POST':
            return [AllowAny()]
        return [IsAuthenticated()]
    
    def get_serializer_class(self):
        """Use different serializers for read vs write operations"""
        if self.request.method == 'POST':
            return BookingCreateRequestSerializer
        # Use simplified serializer for list view
        return BookingListSerializer
    
    def get_queryset(self):
        """Return bookings based on user role"""
        # Handle swagger schema generation
        if getattr(self, 'swagger_fake_view', False):
            return Booking.objects.none()
        
        user = self.request.user
        
        # Handle anonymous users
        if not user.is_authenticated:
            return Booking.objects.none()
        
        # Admin sees all bookings
        if user.role == 'admin':
            return Booking.objects.all().select_related('property', 'user').prefetch_related('payment')
        
        # Staff sees only bookings from their assigned properties
        elif user.role == 'staff':
            assigned_property_ids = user.assigned_properties.values_list('id', flat=True)
            return Booking.objects.filter(property_id__in=assigned_property_ids).select_related('property', 'user').prefetch_related('payment')
        
        # External users see only their own bookings
        return Booking.objects.filter(user=user).select_related('property').prefetch_related('payment')
    
    def create(self, request, *args, **kwargs):
        """Override to return full booking details in response"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()
        
        # Return full booking details using BookingSerializer
        response_serializer = BookingSerializer(booking, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class CalculatePriceView(APIView):
    """
    Preview booking price before creation (available to everyone, no authentication required).
    
    Returns calculated price based on:
    - User's country if authenticated (determines guest_type and pricing tier)
    - For guest users: Phone number determines local vs international pricing (optional but recommended)
    - Stay duration (short_term/long_term/weekly)
    - Property and accommodation type
    - Number of guests (affects pricing for some properties)
    
    Use this endpoint to show price preview to users before booking.
    """
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        operation_description="Calculate price for a potential booking. Phone number with country code is required for accurate local/international pricing.",
        manual_parameters=[
            openapi.Parameter('property', openapi.IN_QUERY, description="Property ID", type=openapi.TYPE_INTEGER, required=True),
            openapi.Parameter('check_in', openapi.IN_QUERY, description="Check-in date (YYYY-MM-DD)", type=openapi.TYPE_STRING, required=True),
            openapi.Parameter('check_out', openapi.IN_QUERY, description="Check-out date (YYYY-MM-DD)", type=openapi.TYPE_STRING, required=True),
            openapi.Parameter('accommodation_type', openapi.IN_QUERY, description="Accommodation type", type=openapi.TYPE_STRING, required=True, enum=['master_bedroom', 'full_apartment']),
            openapi.Parameter('phone', openapi.IN_QUERY, description="Phone number with country code (e.g., +254712345678). Required for guests and users without country in profile.", type=openapi.TYPE_STRING, required=True),
            openapi.Parameter('number_of_guests', openapi.IN_QUERY, description="Number of guests", type=openapi.TYPE_INTEGER, required=False),
        ],
        responses={
            200: PriceCalculationSerializer(),
            400: 'Bad Request - Missing or invalid parameters',
            404: 'Property not found or no pricing available'
        }
    )
    def get(self, request):
        # Get query parameters
        property_id = request.query_params.get('property')
        check_in = request.query_params.get('check_in')
        check_out = request.query_params.get('check_out')
        accommodation_type = request.query_params.get('accommodation_type')
        phone = request.query_params.get('phone')
        number_of_guests = request.query_params.get('number_of_guests')
        
        # Validate required parameters (including phone for authenticated users and guests)
        user = request.user
        is_authenticated = user and user.is_authenticated
        
        # Phone is required for guests, or for authenticated users without country_of_residence
        phone_required = not is_authenticated or not user.country_of_residence
        
        if not all([property_id, check_in, check_out, accommodation_type]):
            return Response({
                'success': False,
                'error_type': 'missing_parameters',
                'message': 'Please provide all required information to calculate the price.',
                'details': {
                    'required': ['property', 'check_in', 'check_out', 'accommodation_type'],
                    'missing': [k for k in ['property', 'check_in', 'check_out', 'accommodation_type'] 
                               if not request.query_params.get(k.replace('_', ''))]
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate phone number is provided when required
        if phone_required and not phone:
            return Response({
                'success': False,
                'error_type': 'missing_phone',
                'message': 'Phone number is required to calculate accurate pricing.',
                'suggestion': 'Please provide your phone number with country code (e.g., +254712345678 for Kenya).',
                'details': {
                    'required_format': 'International format with country code',
                    'examples': {
                        'Kenya': '+254712345678',
                        'Belgium': '+32471234567',
                        'USA': '+14155552671'
                    }
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get property
        try:
            property_obj = Property.objects.get(id=property_id)
        except (Property.DoesNotExist, ValueError, TypeError):
            return Response({
                'success': False,
                'error_type': 'property_not_found',
                'message': f'Property with ID {property_id} does not exist or is invalid.',
                'details': {'property_id': property_id}
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Parse dates
        try:
            check_in_date = datetime.strptime(check_in, '%Y-%m-%d').date()
            check_out_date = datetime.strptime(check_out, '%Y-%m-%d').date()
        except ValueError:
            return Response({
                'success': False,
                'error_type': 'invalid_date_format',
                'message': 'Please provide dates in the correct format (YYYY-MM-DD).',
                'details': {
                    'check_in': check_in,
                    'check_out': check_out,
                    'expected_format': 'YYYY-MM-DD',
                    'example': '2026-03-15'
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Calculate total days
        total_days = (check_out_date - check_in_date).days
        if total_days <= 0:
            return Response({
                'success': False,
                'error_type': 'invalid_date_range',
                'message': 'Check-out date must be after check-in date.',
                'details': {
                    'check_in': check_in,
                    'check_out': check_out
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Determine stay_type intelligently
        # Check if property has weekly pricing and if nights is a multiple of 7
        has_weekly_pricing = PropertyPricing.objects.filter(
            property=property_obj,
            accommodation_type=accommodation_type,
            stay_type='weekly'
        ).exists()
        
        if total_days % 7 == 0 and has_weekly_pricing:
            # Multiples of 7 (7, 14, 21, 28...) use weekly pricing if available
            stay_type = 'weekly'
        elif total_days >= 10:
            stay_type = 'long_term'
        elif total_days < 7:
            stay_type = 'short_term'
        else:
            # 8 or 9 nights - check what's available
            stay_type = 'short_term'
        
        # Determine guest_type from user's country vs property's country
        if is_authenticated and user.country_of_residence and property_obj.country:
            user_country = user.country_of_residence.lower()
            property_country = property_obj.country.lower()
            guest_type = 'local' if user_country == property_country else 'international'
        else:
            # For guest users or authenticated users without country, determine from phone number
            # Phone is already validated to exist at this point
            try:
                parsed = phonenumbers.parse(phone, None)
                if not phonenumbers.is_valid_number(parsed):
                    return Response({
                        'success': False,
                        'error_type': 'invalid_phone_format',
                        'message': 'Please provide a valid phone number with country code.',
                        'suggestion': 'Use international format with country code (e.g., +254712345678 for Kenya, +32471234567 for Belgium).',
                        'details': {
                            'phone_provided': phone,
                            'format_example': '+254712345678'
                        }
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                phone_country = geocoder.description_for_number(parsed, "en")
                if phone_country:
                    property_country = property_obj.country.lower()
                    # Compare phone country with property country
                    guest_type = 'local' if phone_country.lower() == property_country else 'international'
                else:
                    guest_type = 'international'
            except phonenumbers.NumberParseException:
                return Response({
                    'success': False,
                    'error_type': 'invalid_phone_format',
                    'message': 'Invalid phone number format. Please include country code.',
                    'suggestion': 'Use international format starting with + and country code (e.g., +254712345678).',
                    'details': {
                        'phone_provided': phone,
                        'format_example': '+254712345678'
                    }
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Find matching PropertyPricing (try specific guest_type first, then 'all_guests')
        # First try exact guest_type match
        pricing_query = PropertyPricing.objects.filter(
            property=property_obj,
            accommodation_type=accommodation_type,
            guest_type=guest_type,
            stay_type=stay_type,
            min_nights__lte=total_days
        ).filter(
            django_models.Q(max_nights__isnull=True) | django_models.Q(max_nights__gte=total_days)
        )
        
        # If no match, try 'all'
        if not pricing_query.exists():
            pricing_query = PropertyPricing.objects.filter(
                property=property_obj,
                accommodation_type=accommodation_type,
                guest_type='all',
                stay_type=stay_type,
                min_nights__lte=total_days
            ).filter(
                django_models.Q(max_nights__isnull=True) | django_models.Q(max_nights__gte=total_days)
            )
        
        # Check if base pricing query found anything before filtering by guest count
        if not pricing_query.exists():
            selected_pricing = None
        elif number_of_guests:
            try:
                guest_count = int(number_of_guests)
                # Find pricing that can accommodate this many guests (capacity >= requested)
                # OR pricing without guest restriction (NULL)
                pricing_with_capacity = pricing_query.filter(
                    django_models.Q(number_of_guests__gte=guest_count) | 
                    django_models.Q(number_of_guests__isnull=True)
                ).order_by('number_of_guests').first()  # Prefer smallest capacity that fits
                
                if pricing_with_capacity:
                    selected_pricing = pricing_with_capacity
                else:
                    # Pricing exists for this stay type but guest count exceeds capacity
                    max_capacity = pricing_query.aggregate(
                        django_models.Max('number_of_guests')
                    )['number_of_guests__max']
                    
                    if max_capacity and guest_count > max_capacity:
                        return Response({
                            'success': False,
                            'error_type': 'guest_capacity_exceeded',
                            'message': f'{accommodation_type.replace("_", " ").title()} accommodates maximum {max_capacity} guest(s).',
                            'suggestion': f'You requested {guest_count} guest(s). Please reduce the number of guests or choose a different accommodation type.',
                            'details': {
                                'accommodation_type': accommodation_type,
                                'max_capacity': max_capacity,
                                'requested_guests': guest_count
                            }
                        }, status=status.HTTP_400_BAD_REQUEST)
                    else:
                        selected_pricing = None
            except (ValueError, TypeError):
                return Response({
                    'success': False,
                    'error_type': 'invalid_parameter',
                    'message': 'Number of guests must be a valid number.',
                    'details': {'number_of_guests': number_of_guests}
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            # No guest count provided, get any pricing (preferably without restriction)
            selected_pricing = pricing_query.filter(number_of_guests__isnull=True).first()
            if not selected_pricing:
                selected_pricing = pricing_query.first()
        
        if not selected_pricing:
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
                
                error_details = {
                    'success': False,
                    'error_type': 'accommodation_unavailable',
                    'message': f'Sorry! {property_obj.name} does not offer {accommodation_display.get(accommodation_type, accommodation_type)} accommodation.',
                    'suggestion': f'This property offers: {", ".join(available_names)}. Would you like to select one of these instead?',
                    'details': {
                        'property_name': property_obj.name,
                        'requested': accommodation_type,
                        'available_options': list(available_accommodations)
                    }
                }
                return Response(error_details, status=status.HTTP_400_BAD_REQUEST)
            
            # 2. Check if min_nights requirement is not met
            min_nights_required = PropertyPricing.objects.filter(
                property=property_obj,
                accommodation_type=accommodation_type
            ).aggregate(django_models.Min('min_nights'))['min_nights__min']
            
            if min_nights_required and total_days < min_nights_required:
                accommodation_display = {
                    'master_bedroom': 'Master Bedroom',
                    'full_apartment': 'Full Apartment'
                }
                return Response({
                    'success': False,
                    'error_type': 'minimum_nights_not_met',
                    'message': f'{accommodation_display.get(accommodation_type, accommodation_type.replace("_", " ").title())} at {property_obj.name} requires a minimum of {min_nights_required} night(s).',
                    'suggestion': f'Your booking is for {total_days} night(s). Please extend your stay to at least {min_nights_required} night(s).',
                    'details': {
                        'property_name': property_obj.name,
                        'accommodation_type': accommodation_type,
                        'min_nights_required': min_nights_required,
                        'requested_nights': total_days
                    }
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 3. Check if max_nights is exceeded for available pricing
            # Get the highest max_nights from pricing that matches min_nights criteria
            max_nights_allowed = PropertyPricing.objects.filter(
                property=property_obj,
                accommodation_type=accommodation_type,
                min_nights__lte=total_days
            ).exclude(max_nights__isnull=True).aggregate(
                django_models.Max('max_nights')
            )['max_nights__max']
            
            # Also check if there's any pricing without max_nights restriction
            has_unlimited = PropertyPricing.objects.filter(
                property=property_obj,
                accommodation_type=accommodation_type,
                max_nights__isnull=True
            ).exists()
            
            if max_nights_allowed and not has_unlimited and total_days > max_nights_allowed:
                accommodation_display = {
                    'master_bedroom': 'Master Bedroom',
                    'full_apartment': 'Full Apartment'
                }
                return Response({
                    'success': False,
                    'error_type': 'maximum_nights_exceeded',
                    'message': f'{accommodation_display.get(accommodation_type, accommodation_type.replace("_", " ").title())} at {property_obj.name} allows a maximum of {max_nights_allowed} night(s) for this booking type.',
                    'suggestion': f'Your booking is for {total_days} night(s). Please reduce your stay to {max_nights_allowed} night(s) or less, or contact the property for longer stays.',
                    'details': {
                        'property_name': property_obj.name,
                        'accommodation_type': accommodation_type,
                        'max_nights_allowed': max_nights_allowed,
                        'requested_nights': total_days
                    }
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 3. Check what stay types are available (without guest_type filter first)
            available_for_all = PropertyPricing.objects.filter(
                property=property_obj,
                accommodation_type=accommodation_type,
                guest_type='all'
            ).exists()
            
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
                
                error_details = {
                    'success': False,
                    'error_type': 'invalid_stay_duration',
                    'message': f'Sorry! This accommodation requires bookings of {", or ".join(suggestions)}.',
                    'suggestion': f'Your {total_days}-night booking doesn\'t match the available options. Please adjust your dates.',
                    'details': {
                        'property_name': property_obj.name,
                        'your_nights': total_days,
                        'your_stay_type': stay_type,
                        'available_stay_types': list(available_stay_types),
                        'accommodation_type': accommodation_type
                    }
                }
            # 4. Only then check if it's a guest_type issue
            elif not available_for_all:
                # Check if specific guest_type pricing exists
                guest_type_available = PropertyPricing.objects.filter(
                    property=property_obj,
                    accommodation_type=accommodation_type,
                    guest_type=guest_type
                ).exists()
                
                if not guest_type_available:
                    error_details = {
                        'success': False,
                        'error_type': 'guest_type_not_supported',
                        'message': f'Sorry! This property does not accept {guest_type} guests for {accommodation_type}.',
                        'suggestion': 'Please contact the property manager or try a different property.',
                        'details': {
                            'property_name': property_obj.name,
                            'property_country': property_obj.country,
                            'user_country': user.country_of_residence if is_authenticated else None,
                            'guest_type': guest_type,
                            'accommodation_type': accommodation_type
                        }
                    }
                else:
                    # Generic pricing not found error
                    error_details = {
                        'success': False,
                        'error_type': 'pricing_not_available',
                        'message': f'Sorry! No pricing available for your requested booking.',
                        'suggestion': 'Please try different dates or contact the property manager.',
                        'details': {
                            'property_name': property_obj.name,
                            'nights': total_days,
                            'accommodation_type': accommodation_type
                        }
                    }
            else:
                # Generic error - pricing exists but something else is wrong
                error_details = {
                    'success': False,
                    'error_type': 'pricing_not_available',
                    'message': f'Sorry! No pricing available for your requested booking configuration.',
                    'suggestion': 'Please try different dates or number of guests.',
                    'details': {
                        'property_name': property_obj.name,
                        'nights': total_days,
                        'accommodation_type': accommodation_type,
                        'stay_type': stay_type
                    }
                }
            
            return Response(error_details, status=status.HTTP_400_BAD_REQUEST)
        
        # Calculate total amount
        if selected_pricing.weekly_price and total_days % 7 == 0:
            # Use weekly price for multiples of 7 (7, 14, 21, 28 nights)
            num_weeks = total_days // 7
            total_amount = selected_pricing.weekly_price * num_weeks
        else:
            total_amount = selected_pricing.price_per_night * Decimal(str(total_days))
        
        # Build response
        response_data = {
            'guest_type': guest_type,
            'stay_type': stay_type,
            'price_per_night': selected_pricing.price_per_night,
            'weekly_price': selected_pricing.weekly_price,
            'total_nights': total_days,
            'total_amount': total_amount,
            'includes_breakfast': selected_pricing.includes_breakfast,
            'includes_fullboard': selected_pricing.includes_fullboard,
            'property_name': property_obj.name,
            'accommodation_type': accommodation_type,
        }
        
        serializer = PriceCalculationSerializer(response_data)
        return Response(serializer.data, status=status.HTTP_200_OK)


class BookingDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or delete a specific booking.
    
    Permissions:
    - User can access their own bookings
    - Staff can access bookings from their assigned properties
    - Admin can access all bookings
    """
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Handle swagger schema generation
        if getattr(self, 'swagger_fake_view', False):
            return Booking.objects.none()
        
        user = self.request.user
        
        # Handle anonymous users
        if not user.is_authenticated:
            return Booking.objects.none()
        
        # Admin sees all bookings
        if user.role == 'admin':
            return Booking.objects.all().select_related('property', 'user').prefetch_related('payment')
        
        # Staff sees only bookings from their assigned properties
        elif user.role == 'staff':
            assigned_property_ids = user.assigned_properties.values_list('id', flat=True)
            return Booking.objects.filter(property_id__in=assigned_property_ids).select_related('property', 'user').prefetch_related('payment')
        
        # External users see only their own bookings
        return Booking.objects.filter(user=user).select_related('property').prefetch_related('payment')


class BookingCancelView(APIView):
    """
    Cancel a booking and handle refunds.
    
    - Updates booking status to 'cancelled'
    - Marks property as 'free' again
    - Initiates payment refund if payment was completed
    - Cannot cancel already completed bookings
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)
        user = request.user
        
        # Check permissions
        has_permission = (
            booking.user == user or 
            user.role == 'admin' or 
            (user.role == 'staff' and user.assigned_properties.filter(id=booking.property.id).exists())
        )
        
        if not has_permission:
            return Response({'error': 'You do not have permission to cancel this booking'}, 
                          status=status.HTTP_403_FORBIDDEN)
        
        # Check if booking can be cancelled
        if booking.status == 'cancelled':
            return Response({'error': 'Booking is already cancelled'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        if booking.status == 'completed':
            return Response({'error': 'Cannot cancel a completed booking'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        # Cancel booking
        booking.status = 'cancelled'
        booking.save()
        
        # Update property status
        booking.property.status = 'free'
        booking.property.save()
        
        # Handle payment refund if needed
        if hasattr(booking, 'payment') and booking.payment.payment_status == 'completed':
            payment = booking.payment
            payment.payment_status = 'refunded'
            payment.save()
        
        return Response({
            'message': 'Booking cancelled successfully',
            'booking': BookingSerializer(booking, context={'request': request}).data
        }, status=status.HTTP_200_OK)


class UserBookingsView(generics.ListAPIView):
    """
    Get personal bookings for the authenticated user.
    
    Always returns ONLY the current user's bookings, regardless of role.
    Even admins/staff will only see their personal bookings here.
    
    Use this endpoint for "My Bookings" profile pages.
    For admin/staff dashboards, use /bookings/ instead.
    """
    serializer_class = BookingListSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at', 'check_in']
    ordering = ['-created_at']
    
    def get_queryset(self):
        return Booking.objects.filter(user=self.request.user).select_related('property').prefetch_related('payment')


class PropertyAvailabilityView(APIView):
    """
    Check property availability for specific dates with detailed conflict information.
    
    Public endpoint - no authentication required (guests need to check availability).
    
    Returns:
    - Whether property is available
    - List of conflicting bookings with details
    - Blocked dates if any
    - Buffer day conflicts (same-day checkout/checkin)
    - Specific unavailable dates
    """
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        operation_description="Check detailed availability with conflict information",
        manual_parameters=[
            openapi.Parameter('check_in', openapi.IN_QUERY, description="Check-in date (YYYY-MM-DD)", type=openapi.TYPE_STRING, required=True),
            openapi.Parameter('check_out', openapi.IN_QUERY, description="Check-out date (YYYY-MM-DD)", type=openapi.TYPE_STRING, required=True),
        ],
        responses={
            200: AvailabilityDetailSerializer(),
            400: 'Bad Request',
            404: 'Property not found'
        }
    )
    def get(self, request, property_id):
        check_in = request.query_params.get('check_in')
        check_out = request.query_params.get('check_out')
        
        if not check_in or not check_out:
            return Response({'error': 'check_in and check_out parameters are required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        try:
            check_in_date = datetime.strptime(check_in, '%Y-%m-%d').date()
            check_out_date = datetime.strptime(check_out, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        property_obj = get_object_or_404(Property, id=property_id)
        
        # Calculate total nights
        total_nights = (check_out_date - check_in_date).days
        
        # Check for overlapping bookings
        overlapping_bookings = Booking.objects.filter(
            property=property_obj,
            status__in=['pending', 'confirmed'],
            check_in__lt=check_out_date,
            check_out__gt=check_in_date
        )
        
        # Check for blocked dates
        blocked_dates = BlockedDate.objects.filter(
            property=property_obj,
            start_date__lt=check_out_date,
            end_date__gt=check_in_date
        )
        
        # Check for buffer conflicts (same-day checkout/checkin)
        buffer_conflicts = Booking.objects.filter(
            property=property_obj,
            status__in=['pending', 'confirmed'],
            check_out=check_in_date
        )
        
        # Determine if available
        is_available = (
            not overlapping_bookings.exists() and 
            not blocked_dates.exists() and 
            not buffer_conflicts.exists()
        )
        
        # Build detailed conflict information
        conflicting_bookings_data = []
        for booking in overlapping_bookings:
            conflicting_bookings_data.append({
                'booking_reference': booking.booking_reference,
                'check_in': booking.check_in.isoformat(),
                'check_out': booking.check_out.isoformat(),
                'guest_name': booking.full_name,
                'status': booking.status,
                'conflict_dates': self._get_overlap_dates(check_in_date, check_out_date, booking.check_in, booking.check_out)
            })
        
        blocked_dates_data = []
        for blocked in blocked_dates:
            blocked_dates_data.append({
                'start_date': blocked.start_date.isoformat(),
                'end_date': blocked.end_date.isoformat(),
                'reason': blocked.reason,
                'conflict_dates': self._get_overlap_dates(check_in_date, check_out_date, blocked.start_date, blocked.end_date)
            })
        
        buffer_conflicts_data = []
        for booking in buffer_conflicts:
            buffer_conflicts_data.append({
                'booking_reference': booking.booking_reference,
                'checkout_date': booking.check_out.isoformat(),
                'message': f"Guest checking out on your check-in date ({check_in_date})"
            })
        
        # Collect all unavailable dates
        unavailable_dates = set()
        for booking in overlapping_bookings:
            unavailable_dates.update(self._get_date_range(
                max(check_in_date, booking.check_in),
                min(check_out_date, booking.check_out)
            ))
        
        for blocked in blocked_dates:
            unavailable_dates.update(self._get_date_range(
                max(check_in_date, blocked.start_date),
                min(check_out_date, blocked.end_date)
            ))
        
        response_data = {
            'property_id': property_id,
            'property_name': property_obj.name,
            'check_in': check_in_date,
            'check_out': check_out_date,
            'is_available': is_available,
            'total_nights': total_nights,
            'conflicting_bookings': conflicting_bookings_data,
            'blocked_dates': blocked_dates_data,
            'buffer_conflicts': buffer_conflicts_data,
            'unavailable_dates': sorted([d.isoformat() for d in unavailable_dates])
        }
        
        serializer = AvailabilityDetailSerializer(response_data)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def _get_overlap_dates(self, start1, end1, start2, end2):
        """Get list of overlapping dates between two ranges"""
        overlap_start = max(start1, start2)
        overlap_end = min(end1, end2)
        return [d.isoformat() for d in self._get_date_range(overlap_start, overlap_end)]
    
    def _get_date_range(self, start_date, end_date):
        """Generate list of dates between start and end (exclusive of end)"""
        dates = []
        current = start_date
        while current < end_date:
            dates.append(current)
            current += timedelta(days=1)
        return dates


# Admin Views
class AdminBookingListView(generics.ListAPIView):
    """
    Admin-only endpoint: View all bookings across all users and properties.
    
    Features:
    - Filter by status, property, user
    - Search by booking reference, name, email, user email
    - Full ordering capabilities
    
    Note: Regular admins can also use /bookings/ which has the same access.
    This endpoint is explicitly admin-only for stricter access control.
    """
    queryset = Booking.objects.all().select_related('property', 'user').prefetch_related('payment')
    serializer_class = BookingListSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'property', 'user']
    search_fields = ['booking_reference', 'full_name', 'email', 'user__email']
    ordering_fields = ['created_at', 'check_in', 'total_amount']
    ordering = ['-created_at']



class PropertyCalendarView(APIView):
    """
    Get calendar view of all bookings and blocked dates for a property.
    
    Supports multiple modes:
    1. All future events (default) - Returns all upcoming bookings and blocked dates
    2. Specific month - Returns events for a specific month
    3. Custom date range - Returns events within a date range
    
    Query params:
    - all: true - Get all future bookings and blocked dates (default if no other params)
    - month: YYYY-MM (e.g., 2026-02) - Get events for specific month
    - start_date: YYYY-MM-DD - Custom start date
    - end_date: YYYY-MM-DD - Custom end date
    
    Examples:
    - /calendar/ or /calendar/?all=true - All future events
    - /calendar/?month=2026-02 - February 2026 only
    - /calendar/?start_date=2026-02-01&end_date=2026-06-30 - Custom range
    
    Public endpoint - no authentication required (guests need to see occupied dates).
    """
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        operation_description="Get calendar events (bookings and blocked dates) for a property",
        manual_parameters=[
            openapi.Parameter('all', openapi.IN_QUERY, description="Get all future events (true/false)", type=openapi.TYPE_BOOLEAN),
            openapi.Parameter('month', openapi.IN_QUERY, description="Month in YYYY-MM format", type=openapi.TYPE_STRING),
            openapi.Parameter('start_date', openapi.IN_QUERY, description="Start date (YYYY-MM-DD)", type=openapi.TYPE_STRING),
            openapi.Parameter('end_date', openapi.IN_QUERY, description="End date (YYYY-MM-DD)", type=openapi.TYPE_STRING),
        ],
        responses={
            200: CalendarEventSerializer(many=True),
            400: 'Bad Request',
            404: 'Property not found'
        }
    )
    def get(self, request, property_id):
        property_obj = get_object_or_404(Property, id=property_id)
        
        # Determine date range
        get_all = request.query_params.get('all', 'false').lower() == 'true'
        month = request.query_params.get('month')
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        
        if month:
            # Parse month (YYYY-MM)
            try:
                year, month_num = map(int, month.split('-'))
                start_date = datetime(year, month_num, 1).date()
                # Get last day of month
                if month_num == 12:
                    end_date = datetime(year + 1, 1, 1).date()
                else:
                    end_date = datetime(year, month_num + 1, 1).date()
            except (ValueError, AttributeError):
                return Response({'error': 'Invalid month format. Use YYYY-MM'}, 
                              status=status.HTTP_400_BAD_REQUEST)
        elif start_date_str and end_date_str:
            # Parse custom date range
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, 
                              status=status.HTTP_400_BAD_REQUEST)
        elif get_all or (not month and not start_date_str):
            # Get all future events (default)
            start_date = timezone.now().date()
            end_date = None  # No end date - get everything future
        else:
            # Default to current month (fallback)
            now = timezone.now()
            start_date = datetime(now.year, now.month, 1).date()
            if now.month == 12:
                end_date = datetime(now.year + 1, 1, 1).date()
            else:
                end_date = datetime(now.year, now.month + 1, 1).date()
        
        # Build booking query
        booking_query = Booking.objects.filter(
            property=property_obj,
            status__in=['pending', 'confirmed', 'completed'],
            check_out__gte=start_date  # Only future/current bookings
        )
        
        # Add end date filter if specified
        if end_date:
            booking_query = booking_query.filter(check_in__lt=end_date)
        
        bookings = booking_query.order_by('check_in')
        
        # Build blocked dates query
        blocked_query = BlockedDate.objects.filter(
            property=property_obj,
            end_date__gte=start_date  # Only future/current blocked dates
        )
        
        # Add end date filter if specified
        if end_date:
            blocked_query = blocked_query.filter(start_date__lt=end_date)
        
        blocked_dates = blocked_query.order_by('start_date')
        
        # Build calendar events
        events = []
        
        # Add bookings as events
        for booking in bookings:
            events.append({
                'type': 'booking',
                'id': booking.id,
                'start_date': booking.check_in,
                'end_date': booking.check_out,
                'title': f"{booking.full_name} - {booking.booking_reference}",
                'status': booking.status,
                'booking_reference': booking.booking_reference,
                'guest_name': booking.full_name,
            })
        
        # Add blocked dates as events
        for blocked in blocked_dates:
            events.append({
                'type': 'blocked',
                'id': blocked.id,
                'start_date': blocked.start_date,
                'end_date': blocked.end_date,
                'title': f"Blocked: {blocked.reason}",
                'reason': blocked.reason,
            })
        
        # Sort events by start date
        events.sort(key=lambda x: x['start_date'])
        
        serializer = CalendarEventSerializer(events, many=True)
        return Response({
            'property_id': property_id,
            'property_name': property_obj.name,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat() if end_date else None,
            'events': serializer.data
        }, status=status.HTTP_200_OK)


class BlockedDateListCreateView(generics.ListCreateAPIView):
    """
    List and create blocked dates for properties.
    
    Admin/Staff only. Used to block dates for maintenance, renovations, etc.
    """
    serializer_class = BlockedDateSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['property']
    ordering_fields = ['start_date', 'created_at']
    ordering = ['start_date']
    
    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'admin':
            return BlockedDate.objects.all().select_related('property', 'created_by')
        elif user.role == 'staff':
            # Staff can only see blocked dates for their assigned properties
            assigned_property_ids = user.assigned_properties.values_list('id', flat=True)
            return BlockedDate.objects.filter(property_id__in=assigned_property_ids).select_related('property', 'created_by')
        else:
            # Regular users can see blocked dates (read-only)
            return BlockedDate.objects.all().select_related('property')
    
    def perform_create(self, serializer):
        # Auto-fill created_by
        user = self.request.user
        
        # Only admin and staff can create blocked dates
        if user.role not in ['admin', 'staff']:
            raise PermissionError("Only admin and staff can block dates.")
        
        # Staff can only block dates for their assigned properties
        if user.role == 'staff':
            property_id = serializer.validated_data['property'].id
            if not user.assigned_properties.filter(id=property_id).exists():
                raise PermissionError("You can only block dates for your assigned properties.")
        
        serializer.save(created_by=user)


class BlockedDateDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or delete a blocked date.
    
    Admin/Staff only.
    """
    serializer_class = BlockedDateSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'admin':
            return BlockedDate.objects.all()
        elif user.role == 'staff':
            assigned_property_ids = user.assigned_properties.values_list('id', flat=True)
            return BlockedDate.objects.filter(property_id__in=assigned_property_ids)
        else:
            return BlockedDate.objects.none()
