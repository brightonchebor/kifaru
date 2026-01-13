from rest_framework import generics, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from .models import Booking, Payment
from .serializers import (
    PaymentSerializer,
    PaymentProcessSerializer
)


class PaymentProcessView(APIView):
    """Process payment for an existing booking"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = PaymentProcessSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        booking = data['booking']
        
        # Check if user owns the booking
        if booking.user != request.user and not request.user.is_staff:
            return Response({'error': 'You do not have permission to pay for this booking'}, 
                          status=status.HTTP_403_FORBIDDEN)
        
        # Create or update payment
        payment, created = Payment.objects.get_or_create(
            booking=booking,
            defaults={
                'user': request.user,
                'payment_method': data['payment_method'],
                'amount': booking.total_amount,
                'payment_status': 'processing'
            }
        )
        
        if not created:
            payment.payment_method = data['payment_method']
            payment.payment_status = 'processing'
            payment.save()
        
        # Process payment
        payment_success = self._process_payment(payment, data)
        
        if payment_success:
            payment.payment_status = 'completed'
            payment.completed_at = timezone.now()
            payment.save()
            
            booking.status = 'confirmed'
            booking.save()
            
            booking.property.status = 'booked'
            booking.property.save()
            
            return Response({
                'message': 'Payment processed successfully',
                'payment': PaymentSerializer(payment).data
            }, status=status.HTTP_200_OK)
        else:
            payment.payment_status = 'failed'
            payment.failure_reason = 'Payment processing failed'
            payment.save()
            
            return Response({
                'message': 'Payment processing failed',
                'payment': PaymentSerializer(payment).data
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def _process_payment(self, payment, data):
        """Same as in BookingCreateWithPaymentView"""
        payment_method = data['payment_method']
        
        if payment_method == 'card':
            card_number = data.get('card_number', '')
            payment.card_number_last4 = card_number[-4:] if len(card_number) >= 4 else ''
            payment.card_type = self._detect_card_type(card_number)
            payment.save()
            return True
            
        elif payment_method == 'mpesa':
            payment.mpesa_phone_number = data.get('mpesa_phone')
            payment.mpesa_receipt_number = f"MPESA{timezone.now().strftime('%Y%m%d%H%M%S')}"
            payment.save()
            return True
            
        elif payment_method == 'bank':
            payment.payment_status = 'pending'
            payment.save()
            return True
        
        return False
    
    def _detect_card_type(self, card_number):
        if card_number.startswith('4'):
            return 'Visa'
        elif card_number.startswith(('51', '52', '53', '54', '55')):
            return 'Mastercard'
        elif card_number.startswith(('34', '37')):
            return 'American Express'
        return 'Unknown'
    


class AdminPaymentListView(generics.ListAPIView):
    """Admin: View all payments"""
    queryset = Payment.objects.all().select_related('booking', 'user')
    serializer_class = PaymentSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['payment_status', 'payment_method']
    search_fields = ['transaction_id', 'booking__booking_reference']
    ordering_fields = ['created_at', 'amount']
    ordering = ['-created_at']