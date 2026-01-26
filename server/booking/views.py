from rest_framework import generics, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import datetime
from .models import Booking
from payment.models import Payment
from .serializers import (
    BookingSerializer, 
    BookingCreateRequestSerializer,
    PriceCalculationSerializer,
)
from properties.models import Property, PropertyPricing
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from decimal import Decimal
from django.db import models as django_models

class BookingListCreateView(generics.ListCreateAPIView):
    """
    List bookings (role-based) and create new bookings.
    
    GET: Returns bookings based on user role:
        - Admin: All bookings from all users
        - Staff: Bookings from their assigned properties only
        - External users: Only their own bookings
    
    POST: Create a new booking with auto-filled user details
    
    Features: Filtering, search, ordering
    Use /bookings/my-bookings/ for guaranteed personal bookings only
    """
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'property']
    search_fields = ['booking_reference', 'full_name', 'email']
    ordering_fields = ['created_at', 'check_in', 'total_amount']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Use different serializers for read vs write operations"""
        if self.request.method == 'POST':
            return BookingCreateRequestSerializer
        return BookingSerializer
    
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


class CalculatePriceView(APIView):
    """
    Preview booking price before creation.
    
    Returns calculated price based on:
    - User's country (determines guest_type and pricing tier)
    - Stay duration (short_term/long_term/weekly)
    - Property and accommodation type
    - Number of guests (affects pricing for some properties)
    
    Use this endpoint to show price preview to users before booking.
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Calculate price for a potential booking based on user's country and booking details",
        manual_parameters=[
            openapi.Parameter('property', openapi.IN_QUERY, description="Property ID", type=openapi.TYPE_INTEGER, required=True),
            openapi.Parameter('check_in', openapi.IN_QUERY, description="Check-in date (YYYY-MM-DD)", type=openapi.TYPE_STRING, required=True),
            openapi.Parameter('check_out', openapi.IN_QUERY, description="Check-out date (YYYY-MM-DD)", type=openapi.TYPE_STRING, required=True),
            openapi.Parameter('accommodation_type', openapi.IN_QUERY, description="Accommodation type", type=openapi.TYPE_STRING, required=True, enum=['master_bedroom', 'full_apartment']),
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
        number_of_guests = request.query_params.get('number_of_guests')
        
        # Validate required parameters
        if not all([property_id, check_in, check_out, accommodation_type]):
            return Response(
                {'error': 'Missing required parameters: property, check_in, check_out, accommodation_type'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get property
        try:
            property_obj = Property.objects.get(id=property_id)
        except Property.DoesNotExist:
            return Response({'error': 'Property not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Parse dates
        try:
            check_in_date = datetime.strptime(check_in, '%Y-%m-%d').date()
            check_out_date = datetime.strptime(check_out, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Calculate total days
        total_days = (check_out_date - check_in_date).days
        if total_days <= 0:
            return Response(
                {'error': 'Check-out date must be after check-in date'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Determine stay_type
        if total_days == 7:
            stay_type = 'weekly'
        elif total_days >= 10:
            stay_type = 'long_term'
        else:
            stay_type = 'short_term'
        
        # Determine guest_type from user's country vs property's country
        user = request.user
        if user.country_of_residence and property_obj.country:
            user_country = user.country_of_residence.lower()
            property_country = property_obj.country.lower()
            guest_type = 'local' if user_country == property_country else 'international'
        else:
            guest_type = 'international'  # Default
        
        # Find matching PropertyPricing
        pricing_query = PropertyPricing.objects.filter(
            property=property_obj,
            accommodation_type=accommodation_type,
            guest_type=guest_type,
            stay_type=stay_type,
            min_nights__lte=total_days
        )
        
        # Filter by max_nights if specified
        pricing_query = pricing_query.filter(
            django_models.Q(max_nights__isnull=True) | django_models.Q(max_nights__gte=total_days)
        )
        
        # Filter by number_of_guests if pricing has this field (for Marble Inn)
        if number_of_guests:
            pricing_with_guests = pricing_query.filter(number_of_guests=int(number_of_guests))
            if pricing_with_guests.exists():
                selected_pricing = pricing_with_guests.first()
            else:
                # Use pricing without guest restriction
                selected_pricing = pricing_query.filter(number_of_guests__isnull=True).first()
        else:
            selected_pricing = pricing_query.filter(number_of_guests__isnull=True).first()
        
        if not selected_pricing:
            return Response(
                {'error': 'No pricing available for the selected criteria'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Calculate total amount
        if total_days == 7 and selected_pricing.weekly_price:
            total_amount = selected_pricing.weekly_price
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
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at', 'check_in']
    ordering = ['-created_at']
    
    def get_queryset(self):
        return Booking.objects.filter(user=self.request.user).select_related('property').prefetch_related('payment')


class PropertyAvailabilityView(APIView):
    """
    Check property availability for specific dates.
    
    Returns whether property is available and count of conflicting bookings.
    Checks for overlapping pending/confirmed bookings only.
    Cancelled bookings don't block availability.
    """
    permission_classes = [IsAuthenticated]
    
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
        
        # Check for overlapping bookings
        overlapping_bookings = Booking.objects.filter(
            property=property_obj,
            status__in=['pending', 'confirmed'],
            check_in__lt=check_out_date,
            check_out__gt=check_in_date
        )
        
        is_available = not overlapping_bookings.exists()
        
        return Response({
            'property_id': property_id,
            'check_in': check_in,
            'check_out': check_out,
            'is_available': is_available,
            'conflicting_bookings': overlapping_bookings.count()
        }, status=status.HTTP_200_OK)


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
    serializer_class = BookingSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'property', 'user']
    search_fields = ['booking_reference', 'full_name', 'email', 'user__email']
    ordering_fields = ['created_at', 'check_in', 'total_amount']
    ordering = ['-created_at']


