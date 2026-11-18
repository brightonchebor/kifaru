from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from django.db.models import Count, Sum, Avg, Q, F
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from .models import Booking
from payment.models import Payment, PaymentTransaction
from payment.services import booking_currency
from properties.models import Property
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi


class BookingReportsView(APIView):
    """Comprehensive booking reports and statistics"""
    permission_classes = [IsAdminUser]
    
    @swagger_auto_schema(
        operation_description="Get detailed booking reports with filters",
        manual_parameters=[
            openapi.Parameter('start_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, format='date', description='Start date (YYYY-MM-DD)'),
            openapi.Parameter('end_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, format='date', description='End date (YYYY-MM-DD)'),
            openapi.Parameter('property_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description='Filter by property'),
        ],
        responses={200: 'Detailed booking reports'}
    )
    def get(self, request):
        # Get filters from query params
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        property_id = request.query_params.get('property_id')
        
        # Base queryset
        bookings = Booking.objects.all()
        
        # Apply filters
        if start_date:
            bookings = bookings.filter(created_at__gte=start_date)
        if end_date:
            bookings = bookings.filter(created_at__lte=end_date)
        if property_id:
            bookings = bookings.filter(property_id=property_id)
        
        # Overall statistics
        total_bookings = bookings.count()
        confirmed_bookings = bookings.filter(status='confirmed').count()
        pending_bookings = bookings.filter(status='pending').count()
        cancelled_bookings = bookings.filter(status='cancelled').count()
        completed_bookings = bookings.filter(status='completed').count()
        
        # Revenue statistics
        total_revenue = bookings.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        confirmed_revenue = bookings.filter(status='confirmed').aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        pending_revenue = bookings.filter(status='pending').aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        
        # Average booking value
        avg_booking_value = bookings.aggregate(avg=Avg('total_amount'))['avg'] or Decimal('0.00')
        
        # Average stay duration
        avg_stay_duration = bookings.aggregate(avg=Avg('total_days'))['avg'] or 0
        
        # Bookings by status
        by_status = list(bookings.values('status').annotate(
            count=Count('id'),
            revenue=Sum('total_amount')
        ).order_by('-count'))
        
        # Bookings by property
        by_property = list(bookings.values(
            'property__id',
            'property__name',
            'property__location'
        ).annotate(
            booking_count=Count('id'),
            total_revenue=Sum('total_amount'),
            avg_booking_value=Avg('total_amount'),
            avg_stay=Avg('total_days')
        ).order_by('-booking_count'))
        
        # Bookings by guest type
        by_guest_type = list(bookings.values('guest_type').annotate(
            count=Count('id'),
            revenue=Sum('total_amount'),
            avg_value=Avg('total_amount')
        ).order_by('-count'))
        
        # Bookings by accommodation type
        by_accommodation = list(bookings.values('accommodation_type').annotate(
            count=Count('id'),
            revenue=Sum('total_amount')
        ).order_by('-count'))
        
        # Bookings by stay type
        by_stay_type = list(bookings.values('stay_type').annotate(
            count=Count('id'),
            revenue=Sum('total_amount')
        ).order_by('-count'))
        
        # Monthly trend (last 12 months)
        twelve_months_ago = timezone.now() - timedelta(days=365)
        monthly_trend = list(bookings.filter(
            created_at__gte=twelve_months_ago
        ).annotate(
            month=TruncMonth('created_at')
        ).values('month').annotate(
            booking_count=Count('id'),
            revenue=Sum('total_amount')
        ).order_by('month'))
        
        # Daily trend (last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        daily_trend = list(bookings.filter(
            created_at__gte=thirty_days_ago
        ).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            booking_count=Count('id'),
            revenue=Sum('total_amount')
        ).order_by('date'))
        
        # User vs Guest bookings
        user_bookings = bookings.filter(user__isnull=False).count()
        guest_bookings = bookings.filter(user__isnull=True).count()
        
        # Top properties by revenue
        top_properties_revenue = list(bookings.values(
            'property__id',
            'property__name',
            'property__location'
        ).annotate(
            total_revenue=Sum('total_amount')
        ).order_by('-total_revenue')[:5])
        
        # Top properties by booking count
        top_properties_bookings = list(bookings.values(
            'property__id',
            'property__name',
            'property__location'
        ).annotate(
            booking_count=Count('id')
        ).order_by('-booking_count')[:5])
        
        return Response({
            'summary': {
                'total_bookings': total_bookings,
                'confirmed_bookings': confirmed_bookings,
                'pending_bookings': pending_bookings,
                'cancelled_bookings': cancelled_bookings,
                'completed_bookings': completed_bookings,
                'user_bookings': user_bookings,
                'guest_bookings': guest_bookings,
                'total_revenue': str(total_revenue),
                'confirmed_revenue': str(confirmed_revenue),
                'pending_revenue': str(pending_revenue),
                'avg_booking_value': str(avg_booking_value),
                'avg_stay_duration': round(float(avg_stay_duration), 2) if avg_stay_duration else 0,
                'conversion_rate': round((confirmed_bookings / total_bookings * 100), 2) if total_bookings > 0 else 0,
            },
            'by_status': by_status,
            'by_property': by_property,
            'by_guest_type': by_guest_type,
            'by_accommodation_type': by_accommodation,
            'by_stay_type': by_stay_type,
            'monthly_trend': monthly_trend,
            'daily_trend': daily_trend,
            'top_properties_by_revenue': top_properties_revenue,
            'top_properties_by_bookings': top_properties_bookings,
        })


def payment_totals(entries):
    totals = entries.aggregate(
        received=Sum('amount', filter=Q(kind='receipt')),
        refunded=Sum('amount', filter=Q(kind='refund')),
    )
    received = (totals['received'] or Decimal('0.00')).quantize(Decimal('0.01'))
    refunded = (totals['refunded'] or Decimal('0.00')).quantize(Decimal('0.01'))
    return received, refunded, received - refunded


class PaymentReportsView(APIView):
    """Report actual receipts and refunds in one currency (EUR by default)."""
    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter('start_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, format='date'),
            openapi.Parameter('end_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, format='date'),
            openapi.Parameter('currency', openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description='Single reporting currency; defaults to the booking currency.'),
        ],
        responses={200: 'Actual receipts, refunds, balances and monthly payment history'},
    )
    def get(self, request):
        from rest_framework import serializers
        currency = request.query_params.get('currency', booking_currency()).strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise serializers.ValidationError({'currency': 'Supply a three-letter currency code.'})
        payments = Payment.objects.filter(currency=currency)
        entries = PaymentTransaction.objects.filter(currency=currency).exclude(kind='legacy')
        filtered = False
        for parameter, lookup in [('start_date', 'gte'), ('end_date', 'lte')]:
            if request.query_params.get(parameter):
                day = serializers.DateField().run_validation(request.query_params[parameter])
                entries = entries.filter(**{f'occurred_at__date__{lookup}': day})
                filtered = True
        if filtered:
            payments = payments.filter(pk__in=entries.values('payment_id'))
        received, refunded, net = payment_totals(entries)
        completed = payments.filter(payment_status='completed')
        pending = payments.filter(payment_status='pending')
        count = payments.count()
        by_method = list(entries.values('payment_method').annotate(
            count=Count('id', filter=Q(kind='receipt')),
            total_amount=Sum('amount', filter=Q(kind='receipt')),
            refunded_amount=Sum('amount', filter=Q(kind='refund')),
        ).order_by('payment_method'))
        for row in by_method:
            row['total_amount'] = row['total_amount'] or Decimal('0.00')
            row['refunded_amount'] = row['refunded_amount'] or Decimal('0.00')
            row['net_amount'] = row['total_amount'] - row['refunded_amount']
        monthly = list(entries.filter(occurred_at__gte=timezone.now() - timedelta(days=365)).annotate(
            month=TruncMonth('occurred_at'),
        ).values('month').annotate(
            payment_count=Count('id', filter=Q(kind='receipt')),
            total_amount=Sum('amount', filter=Q(kind='receipt')),
            refunded_amount=Sum('amount', filter=Q(kind='refund')),
            completed_count=Count('payment_id', filter=Q(payment__payment_status='completed'), distinct=True),
        ).order_by('month'))
        for row in monthly:
            row['total_amount'] = row['total_amount'] or Decimal('0.00')
            row['refunded_amount'] = row['refunded_amount'] or Decimal('0.00')
            row['net_amount'] = row['total_amount'] - row['refunded_amount']
        return Response({
            'currency': currency,
            'summary': {
                'total_payments': count, 'completed_payments': completed.count(),
                'pending_payments': pending.count(),
                'partial_payments': payments.filter(payment_status='partial').count(),
                'refund_pending_payments': payments.filter(payment_status='refund_pending').count(),
                'refunded_payments': payments.filter(payment_status__in=['refunded', 'partially_refunded']).count(),
                'completed_amount': str(completed.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')),
                'pending_amount': str(pending.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')),
                'received_amount': str(received), 'refunded_amount': str(refunded), 'net_received': str(net),
                'failed_payments': 0, 'failed_amount': '0.00', 'failure_rate': 0,
                'success_rate': round(completed.count() / count * 100, 2) if count else 0,
            },
            'by_status': list(payments.values('payment_status').annotate(count=Count('id'), total_amount=Sum('amount'))),
            'by_method': by_method, 'monthly_payments': monthly,
        })


class PropertyReportsView(APIView):
    """Property performance and occupancy reports"""
    permission_classes = [IsAdminUser]
    
    @swagger_auto_schema(
        operation_description="Get property performance reports",
        responses={200: 'Property performance data'}
    )
    def get(self, request):
        properties = Property.objects.all()
        
        property_reports = []
        for prop in properties:
            bookings = Booking.objects.filter(property=prop)
            
            total_bookings = bookings.count()
            confirmed_bookings = bookings.filter(status='confirmed').count()
            total_revenue = bookings.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
            confirmed_revenue = bookings.filter(status='confirmed').aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
            avg_booking_value = bookings.aggregate(avg=Avg('total_amount'))['avg'] or Decimal('0.00')
            avg_stay = bookings.aggregate(avg=Avg('total_days'))['avg'] or 0
            
            # Calculate occupancy rate (simplified - days booked / days in period)
            # For last 30 days
            thirty_days_ago = timezone.now() - timedelta(days=30)
            recent_bookings = bookings.filter(
                check_in__gte=thirty_days_ago,
                status__in=['confirmed', 'completed']
            )
            total_booked_days = recent_bookings.aggregate(total=Sum('total_days'))['total'] or 0
            occupancy_rate = round((total_booked_days / 30 * 100), 2) if total_booked_days else 0
            
            property_reports.append({
                'property_id': prop.id,
                'property_name': prop.name,
                'location': prop.location,
                'total_bookings': total_bookings,
                'confirmed_bookings': confirmed_bookings,
                'total_revenue': str(total_revenue),
                'confirmed_revenue': str(confirmed_revenue),
                'avg_booking_value': str(avg_booking_value),
                'avg_stay_duration': round(float(avg_stay), 2) if avg_stay else 0,
                'occupancy_rate_30days': occupancy_rate,
            })
        
        # Sort by revenue
        property_reports.sort(key=lambda x: float(x['total_revenue']), reverse=True)
        
        return Response({
            'properties': property_reports,
            'total_properties': len(property_reports),
        })


class DashboardSummaryView(APIView):
    """Dashboard revenue is net recorded receipts, separate from quoted booking value."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        today = timezone.localdate()
        month_start = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        currency = booking_currency()
        entries = PaymentTransaction.objects.filter(currency=currency).exclude(kind='legacy')

        def statistics(bookings, transactions):
            received, refunded, net = payment_totals(transactions)
            value = (bookings.exclude(status='cancelled').aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')).quantize(Decimal('0.01'))
            return {'bookings': bookings.count(), 'revenue': str(net), 'booking_value': str(value),
                    'received_amount': str(received), 'refunded_amount': str(refunded)}

        all_time = statistics(Booking.objects.all(), entries)
        all_time['properties'] = Property.objects.count()
        unpaid = Booking.objects.filter(total_amount__gt=0, status__in=['pending', 'confirmed']).filter(
            Q(payment__isnull=True) | Q(payment__payment_status__in=['pending', 'partial'])
        ).count()
        recent = Booking.objects.select_related('property', 'payment').order_by('-created_at')[:10]
        rows = []
        for booking in recent:
            payment = getattr(booking, 'payment', None)
            rows.append({
                'id': booking.pk, 'booking_reference': booking.booking_reference,
                'property_name': booking.property.name, 'guest_name': booking.full_name,
                'check_in': booking.check_in, 'total_amount': str(booking.total_amount),
                'status': booking.status, 'created_at': booking.created_at,
                'payment_status': payment.payment_status if payment else 'not_required' if booking.total_amount == 0 else 'pending',
                'amount_paid': str(payment.amount if payment else Decimal('0.00')),
                'remaining_amount': str(payment.remaining_amount if payment else Decimal('0.00') if booking.status == 'cancelled' else booking.total_amount),
            })
        return Response({
            'currency': currency,
            'today': statistics(Booking.objects.filter(created_at__date=today), entries.filter(occurred_at__date=today)),
            'this_month': statistics(Booking.objects.filter(created_at__gte=month_start), entries.filter(occurred_at__gte=month_start)),
            'all_time': all_time,
            'pending_actions': {
                'pending_bookings': Booking.objects.filter(status='pending').count(),
                'pending_payments': unpaid,
                'refund_reviews': Payment.objects.filter(booking__status='cancelled', amount__gt=F('refunded_amount')).count(),
            },
            'recent_bookings': rows,
        })
