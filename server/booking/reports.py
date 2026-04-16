from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from django.db.models import Count, Sum, Avg, Q, F
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from .models import Booking
from payment.models import Payment
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


class PaymentReportsView(APIView):
    """Detailed payment reports and statistics"""
    permission_classes = [IsAdminUser]
    
    @swagger_auto_schema(
        operation_description="Get detailed payment reports",
        manual_parameters=[
            openapi.Parameter('start_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, format='date'),
            openapi.Parameter('end_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, format='date'),
        ],
        responses={200: 'Detailed payment reports'}
    )
    def get(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        payments = Payment.objects.all()
        
        if start_date:
            payments = payments.filter(created_at__gte=start_date)
        if end_date:
            payments = payments.filter(created_at__lte=end_date)
        
        # Payment statistics
        total_payments = payments.count()
        completed_payments = payments.filter(payment_status='completed').count()
        pending_payments = payments.filter(payment_status='pending').count()
        failed_payments = payments.filter(payment_status='failed').count()
        
        # Revenue by payment status
        completed_amount = payments.filter(payment_status='completed').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        pending_amount = payments.filter(payment_status='pending').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        failed_amount = payments.filter(payment_status='failed').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        # Payments by status
        by_status = list(payments.values('payment_status').annotate(
            count=Count('id'),
            total_amount=Sum('amount')
        ).order_by('-count'))
        
        # Payments by method
        by_method = list(payments.values('payment_method').annotate(
            count=Count('id'),
            total_amount=Sum('amount')
        ).order_by('-count'))
        
        # Success rate
        success_rate = round((completed_payments / total_payments * 100), 2) if total_payments > 0 else 0
        failure_rate = round((failed_payments / total_payments * 100), 2) if total_payments > 0 else 0
        
        # Monthly payment trend
        twelve_months_ago = timezone.now() - timedelta(days=365)
        monthly_payments = list(payments.filter(
            created_at__gte=twelve_months_ago
        ).annotate(
            month=TruncMonth('created_at')
        ).values('month').annotate(
            payment_count=Count('id'),
            total_amount=Sum('amount'),
            completed_count=Count('id', filter=Q(payment_status='completed'))
        ).order_by('month'))
        
        return Response({
            'summary': {
                'total_payments': total_payments,
                'completed_payments': completed_payments,
                'pending_payments': pending_payments,
                'failed_payments': failed_payments,
                'completed_amount': str(completed_amount),
                'pending_amount': str(pending_amount),
                'failed_amount': str(failed_amount),
                'success_rate': success_rate,
                'failure_rate': failure_rate,
            },
            'by_status': by_status,
            'by_method': by_method,
            'monthly_trend': monthly_payments,
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
    """Quick dashboard summary for admin overview"""
    permission_classes = [IsAdminUser]
    
    @swagger_auto_schema(
        operation_description="Get dashboard summary with key metrics",
        responses={200: 'Dashboard summary'}
    )
    def get(self, request):
        # Today's stats
        today = timezone.now().date()
        today_bookings = Booking.objects.filter(created_at__date=today).count()
        today_revenue = Booking.objects.filter(created_at__date=today).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        
        # This month
        month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_bookings = Booking.objects.filter(created_at__gte=month_start).count()
        month_revenue = Booking.objects.filter(created_at__gte=month_start).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        
        # All time
        total_bookings = Booking.objects.count()
        total_revenue = Booking.objects.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        total_properties = Property.objects.count()
        
        # Pending actions
        pending_bookings = Booking.objects.filter(status='pending').count()
        pending_payments = Payment.objects.filter(payment_status='pending').count()
        
        # Recent bookings
        recent_bookings = Booking.objects.select_related('property').order_by('-created_at')[:10]
        recent_bookings_data = [{
            'id': b.id,
            'booking_reference': b.booking_reference,
            'property_name': b.property.name,
            'guest_name': b.full_name,
            'check_in': b.check_in,
            'total_amount': str(b.total_amount),
            'status': b.status,
            'created_at': b.created_at,
        } for b in recent_bookings]
        
        return Response({
            'today': {
                'bookings': today_bookings,
                'revenue': str(today_revenue),
            },
            'this_month': {
                'bookings': month_bookings,
                'revenue': str(month_revenue),
            },
            'all_time': {
                'bookings': total_bookings,
                'revenue': str(total_revenue),
                'properties': total_properties,
            },
            'pending_actions': {
                'pending_bookings': pending_bookings,
                'pending_payments': pending_payments,
            },
            'recent_bookings': recent_bookings_data,
        })
