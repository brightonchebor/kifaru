from rest_framework import generics, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import api_view, permission_classes
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .models import Booking, Payment
from .serializers import (
    PaymentSerializer,
    PaymentInitializeSerializer
)
from .paystack_utils import initialize_payment, verify_payment, verify_webhook_signature
import json
import logging
from users.utils import send_normal_email

logger = logging.getLogger(__name__)


def _send_payment_status_email(payment, status_label, failure_reason=None):
    """Notify guest and property contacts of payment status changes."""
    booking = payment.booking
    property_obj = booking.property
    ref = booking.booking_reference
    guest_name = booking.full_name
    guest_email = booking.email
    check_in = booking.check_in.strftime('%d %b %Y')
    check_out = booking.check_out.strftime('%d %b %Y')
    currency = payment.currency or getattr(settings, 'DEFAULT_CURRENCY', 'EUR')

    status_line = f"Payment status: {status_label}"
    if failure_reason:
        status_line = f"{status_line}\nReason: {failure_reason}"

    guest_subject = f"Payment {status_label.lower()} — {ref}"
    guest_message = (
        f"Hi {guest_name},\n\n"
        f"{status_line}\n\n"
        f"Booking Reference: {ref}\n"
        f"Property: {property_obj.name}\n"
        f"Check-in:  {check_in}\n"
        f"Check-out: {check_out}\n"
        f"Amount: {currency} {payment.amount}\n\n"
        f"If you need help, please contact us with your booking reference.\n\n"
        f"Kind regards,\nThe {property_obj.name} Team"
    )

    send_normal_email({
        'email_body': guest_message,
        'email_subject': guest_subject,
        'to_email': guest_email
    })

    contact_emails = list(
        property_obj.contacts.values_list('email', flat=True).exclude(email='')
    )
    if contact_emails:
        staff_subject = f"[Admin] Payment {status_label.lower()} — {ref}"
        staff_message = (
            f"Payment update for {property_obj.name}.\n\n"
            f"Booking Reference: {ref}\n"
            f"Guest: {guest_name} <{guest_email}>\n"
            f"Check-in:  {check_in}\n"
            f"Check-out: {check_out}\n"
            f"Amount: {currency} {payment.amount}\n\n"
            f"{status_line}\n"
        )

        for email in contact_emails:
            send_normal_email({
                'email_body': staff_message,
                'email_subject': staff_subject,
                'to_email': email
            })


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
    pagination_class = PageNumberPagination


class PaymentInitializeView(APIView):
    """Initialize Paystack payment for a booking (supports both authenticated users and guests)"""
    permission_classes = [AllowAny]
    serializer_class = PaymentInitializeSerializer
    
    @swagger_auto_schema(
        request_body=PaymentInitializeSerializer,
        responses={
            200: openapi.Response(
                description="Payment initialized successfully",
                examples={
                    "application/json": {
                        "message": "Payment initialized successfully",
                        "payment_id": 1,
                        "authorization_url": "https://checkout.paystack.com/abc123",
                        "reference": "BK-1-ABC12345",
                        "access_code": "abc123xyz"
                    }
                }
            ),
            400: "Bad Request - Payment initialization failed",
            403: "Forbidden - User doesn't own booking",
            404: "Not Found - Booking not found"
        },
        operation_description="Initialize a Paystack payment for a booking. Returns authorization URL to redirect user to Paystack payment page."
    )
    def post(self, request):
        serializer = PaymentInitializeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        booking_id = serializer.validated_data['booking_id']
        callback_url = serializer.validated_data.get('callback_url')
        
        try:
            booking = Booking.objects.get(id=booking_id)
        except Booking.DoesNotExist:
            return Response({'error': 'Booking not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user owns the booking (allow for guest bookings or matching user)
        is_authenticated = request.user and request.user.is_authenticated
        is_guest_booking = booking.user is None
        is_owner = is_authenticated and booking.user == request.user
        is_staff = is_authenticated and request.user.is_staff
        
        if not (is_guest_booking or is_owner or is_staff):
            return Response({'error': 'You do not have permission to pay for this booking'}, 
                          status=status.HTTP_403_FORBIDDEN)
        
        # Create or get payment record
        payment, created = Payment.objects.get_or_create(
            booking=booking,
            defaults={
                'user': request.user if is_authenticated else None,
                'payment_method': 'card',
                'amount': booking.total_amount,
                'currency': 'KES',  # Change to your default currency
                'payment_status': 'pending'
            }
        )
        
        # If payment exists and not pending, update it
        if not created and payment.payment_status != 'pending':
            payment.payment_status = 'pending'
            payment.save()
        
        # Generate unique reference if not exists
        if not payment.paystack_reference:
            import uuid
            payment.paystack_reference = f"BK-{booking.id}-{uuid.uuid4().hex[:8].upper()}"
            payment.save()
        
        # Initialize Paystack payment (use booking email for both authenticated and guest users)
        paystack_result = initialize_payment(
            email=booking.email,
            amount=payment.amount,
            reference=payment.paystack_reference,
            callback_url=callback_url,
            metadata={
                'booking_id': booking.id,
                'booking_reference': booking.booking_reference,
                'user_id': request.user.id if is_authenticated else None,
                'customer_name': booking.full_name
            }
        )
        
        if paystack_result['status']:
            # Update payment with Paystack details
            payment.paystack_access_code = paystack_result['data']['access_code']
            payment.authorization_url = paystack_result['data']['authorization_url']
            payment.save()
            
            return Response({
                'message': 'Payment initialized successfully',
                'payment_id': payment.id,
                'authorization_url': payment.authorization_url,
                'reference': payment.paystack_reference,
                'access_code': payment.paystack_access_code
            }, status=status.HTTP_200_OK)
        else:
            payment.payment_status = 'failed'
            payment.failure_reason = paystack_result['message']
            payment.save()
            
            return Response({
                'error': 'Payment initialization failed',
                'message': paystack_result['message']
            }, status=status.HTTP_400_BAD_REQUEST)


class PaymentVerifyView(APIView):
    """Verify Paystack payment after customer returns from payment page (supports both authenticated users and guests)"""
    permission_classes = [AllowAny]
    serializer_class = PaymentSerializer
    
    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                'reference',
                openapi.IN_PATH,
                description="Payment reference to verify (e.g., BK-1-ABC12345)",
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        responses={
            200: openapi.Response(
                description="Payment verified successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'message': openapi.Schema(type=openapi.TYPE_STRING),
                        'payment': openapi.Schema(type=openapi.TYPE_OBJECT),
                        'booking_reference': openapi.Schema(type=openapi.TYPE_STRING),
                    }
                )
            ),
            400: "Bad Request - Payment verification failed",
            403: "Forbidden - User doesn't own payment",
            404: "Not Found - Payment not found"
        },
        operation_description="Verify payment status after user completes payment on Paystack. Call this after user returns from Paystack payment page."
    )
    def get(self, request, reference):
        try:
            payment = Payment.objects.get(paystack_reference=reference)
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user owns the payment (allow for guest payments or matching user)
        is_authenticated = request.user and request.user.is_authenticated
        is_guest_payment = payment.user is None
        is_owner = is_authenticated and payment.user == request.user
        is_staff = is_authenticated and request.user.is_staff
        
        if not (is_guest_payment or is_owner or is_staff):
            return Response({'error': 'You do not have permission to verify this payment'}, 
                          status=status.HTTP_403_FORBIDDEN)
        
        # Verify payment with Paystack
        verify_result = verify_payment(reference)
        
        if verify_result['status'] and verify_result['data']:
            transaction_data = verify_result['data']
            
            if transaction_data['status'] == 'success':
                booking = payment.booking
                # Payment successful
                if payment.payment_status != 'completed':
                    payment.payment_status = 'completed'
                    payment.completed_at = timezone.now()
                    payment.transaction_id = transaction_data.get('id')
                
                    # Update booking status
                    booking.status = 'confirmed'
                    booking.save()
                    
                    payment.save()
                    _send_payment_status_email(payment, 'Completed')
                
                return Response({
                    'message': 'Payment verified successfully',
                    'payment': PaymentSerializer(payment).data,
                    'booking_reference': booking.booking_reference
                }, status=status.HTTP_200_OK)
            
            else:
                # Payment failed or abandoned
                if payment.payment_status != 'failed':
                    payment.payment_status = 'failed'
                    payment.failure_reason = f"Transaction status: {transaction_data['status']}"
                    payment.save()
                    _send_payment_status_email(payment, 'Failed', payment.failure_reason)
                
                return Response({
                    'error': 'Payment verification failed',
                    'status': transaction_data['status']
                }, status=status.HTTP_400_BAD_REQUEST)
        
        else:
            return Response({
                'error': 'Payment verification failed',
                'message': verify_result['message']
            }, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
class PaystackWebhookView(APIView):
    """Handle Paystack webhook notifications"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        # Get signature from headers
        signature = request.headers.get('X-Paystack-Signature')
        
        if not signature:
            logger.warning("Webhook received without signature")
            return Response({'error': 'No signature provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Verify webhook signature
        if not verify_webhook_signature(request.body, signature):
            logger.warning("Invalid webhook signature")
            return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse webhook data
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            logger.error("Invalid JSON in webhook payload")
            return Response({'error': 'Invalid JSON'}, status=status.HTTP_400_BAD_REQUEST)
        
        event = data.get('event')
        event_data = data.get('data', {})
        
        logger.info(f"Webhook received: {event}")
        
        # Handle charge.success event
        if event == 'charge.success':
            reference = event_data.get('reference')
            
            try:
                payment = Payment.objects.get(paystack_reference=reference)
                
                if payment.payment_status != 'completed':
                    payment.payment_status = 'completed'
                    payment.completed_at = timezone.now()
                    payment.transaction_id = event_data.get('id')
                    
                    # Update booking status
                    booking = payment.booking
                    booking.status = 'confirmed'
                    booking.save()
                    
                    payment.save()
                    _send_payment_status_email(payment, 'Completed')
                    logger.info(f"Payment completed via webhook: {reference}")
                
            except Payment.DoesNotExist:
                logger.warning(f"Payment not found for reference: {reference}")
        
        return Response({'message': 'Webhook processed'}, status=status.HTTP_200_OK)