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
    BookingCreateSerializer,
)
from properties.models import Property
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

class BookingListCreateView(generics.ListCreateAPIView):
    """List all bookings for authenticated user or create a new booking"""
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'property']
    search_fields = ['booking_reference', 'full_name', 'email']
    ordering_fields = ['created_at', 'check_in', 'total_amount']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Return bookings based on user role"""
        user = self.request.user
        
        # Admin sees all bookings
        if user.role == 'admin':
            return Booking.objects.all().select_related('property', 'user').prefetch_related('payment')
        
        # Staff sees only bookings from their assigned properties
        elif user.role == 'staff':
            assigned_property_ids = user.assigned_properties.values_list('id', flat=True)
            return Booking.objects.filter(property_id__in=assigned_property_ids).select_related('property', 'user').prefetch_related('payment')
        
        # External users see only their own bookings
        return Booking.objects.filter(user=user).select_related('property').prefetch_related('payment')


class BookingDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a specific booking"""
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        # Admin sees all bookings
        if user.role == 'admin':
            return Booking.objects.all().select_related('property', 'user').prefetch_related('payment')
        
        # Staff sees only bookings from their assigned properties
        elif user.role == 'staff':
            assigned_property_ids = user.assigned_properties.values_list('id', flat=True)
            return Booking.objects.filter(property_id__in=assigned_property_ids).select_related('property', 'user').prefetch_related('payment')
        
        # External users see only their own bookings
        return Booking.objects.filter(user=user).select_related('property').prefetch_related('payment')


class BookingCreateWithPaymentView(generics.GenericAPIView):
    """Create a booking and process payment in one step"""
    serializer_class = BookingCreateSerializer
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Create a booking and process payment in one step",
        request_body=BookingCreateSerializer,
        responses={
            201: openapi.Response(
                description="Booking created and payment processed successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'message': openapi.Schema(type=openapi.TYPE_STRING),
                        'booking': openapi.Schema(type=openapi.TYPE_OBJECT),
                        'payment': openapi.Schema(type=openapi.TYPE_OBJECT),
                    }
                )
            ),
            400: "Bad Request - Payment failed or validation error"
        }
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        property_obj = data['property']
        
        # Calculate booking details
        check_in = data['check_in']
        check_out = data['check_out']
        total_days = (check_out - check_in).days
        total_amount = property_obj.price * total_days
        
        # Create booking
        booking = Booking.objects.create(
            user=request.user,
            property=property_obj,
            full_name=data['full_name'],
            email=data['email'],
            phone=data['phone'],
            check_in=check_in,
            check_out=check_out,
            guests=data['guests'],
            total_days=total_days,
            total_amount=total_amount,
            notes=data.get('notes', ''),
            status='pending'
        )
        
        # Create payment
        payment = Payment.objects.create(
            booking=booking,
            user=request.user,
            payment_method=data['payment_method'],
            amount=total_amount,
            payment_status='processing'
        )
        
        # Process payment based on method
        payment_success = self._process_payment(payment, data)
        
        if payment_success:
            payment.payment_status = 'completed'
            payment.completed_at = timezone.now()
            payment.save()
            
            booking.status = 'confirmed'
            booking.save()
            
            # Update property status to booked
            property_obj.status = 'booked'
            property_obj.save()
            
            return Response({
                'message': 'Booking created and payment processed successfully',
                'booking': BookingSerializer(booking, context={'request': request}).data,
                'payment': PaymentSerializer(payment).data
            }, status=status.HTTP_201_CREATED)
        else:
            payment.payment_status = 'failed'
            payment.failure_reason = 'Payment processing failed'
            payment.save()
            
            return Response({
                'message': 'Booking created but payment failed',
                'booking': BookingSerializer(booking, context={'request': request}).data,
                'payment': PaymentSerializer(payment).data
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def _process_payment(self, payment, data):
        """
        Simulate payment processing.
        In production, integrate with actual payment gateways:
        - Stripe/PayPal for card payments
        - M-Pesa API for mobile money
        - Bank API for bank transfers
        """
        payment_method = data['payment_method']
        
        if payment_method == 'card':
            # Simulate card payment processing
            card_number = data.get('card_number', '')
            payment.card_number_last4 = card_number[-4:] if len(card_number) >= 4 else ''
            payment.card_type = self._detect_card_type(card_number)
            payment.save()
            
            # In production: Call Stripe/PayPal API
            # For now, simulate success
            return True
            
        elif payment_method == 'mpesa':
            # Simulate M-Pesa payment
            payment.mpesa_phone_number = data.get('mpesa_phone')
            payment.mpesa_receipt_number = f"MPESA{timezone.now().strftime('%Y%m%d%H%M%S')}"
            payment.save()
            
            # In production: Call M-Pesa API
            return True
            
        elif payment_method == 'bank':
            # Bank transfer - usually requires manual confirmation
            payment.payment_status = 'pending'
            payment.save()
            return True
        
        return False
    
    def _detect_card_type(self, card_number):
        """Detect card type from card number"""
        if card_number.startswith('4'):
            return 'Visa'
        elif card_number.startswith(('51', '52', '53', '54', '55')):
            return 'Mastercard'
        elif card_number.startswith(('34', '37')):
            return 'American Express'
        return 'Unknown'



class BookingCancelView(APIView):
    """Cancel a booking"""
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
    """Get all bookings for the authenticated user"""
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at', 'check_in']
    ordering = ['-created_at']
    
    def get_queryset(self):
        return Booking.objects.filter(user=self.request.user).select_related('property').prefetch_related('payment')


class PropertyAvailabilityView(APIView):
    """Check availability of a property for specific dates"""
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
    """Admin: View all bookings"""
    queryset = Booking.objects.all().select_related('property', 'user').prefetch_related('payment')
    serializer_class = BookingSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'property', 'user']
    search_fields = ['booking_reference', 'full_name', 'email', 'user__email']
    ordering_fields = ['created_at', 'check_in', 'total_amount']
    ordering = ['-created_at']


