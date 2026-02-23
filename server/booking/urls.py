from django.urls import path
from .views import (
    BookingListCreateView,
    BookingDetailView,
    BookingCancelView,
    UserBookingsView,
    PropertyAvailabilityView,
    PropertyCalendarView,
    AdminBookingListView,
    CalculatePriceView,
    BlockedDateListCreateView,
    BlockedDateDetailView,
)
from .reports import (
    BookingReportsView,
    PaymentReportsView,
    PropertyReportsView,
    DashboardSummaryView,
)


urlpatterns = [
    # User booking endpoints - specific paths first!
    path('bookings/calculate-price/', CalculatePriceView.as_view(), name='calculate-price'),
    path('bookings/my-bookings/', UserBookingsView.as_view(), name='user-bookings'),
    path('bookings/<int:pk>/cancel/', BookingCancelView.as_view(), name='booking-cancel'),
    path('bookings/<int:pk>/', BookingDetailView.as_view(), name='booking-detail'),
    path('bookings/', BookingListCreateView.as_view(), name='booking-list-create'),
    
    # Property availability and calendar
    path('properties/<int:property_id>/availability/', PropertyAvailabilityView.as_view(), name='property-availability'),
    path('properties/<int:property_id>/calendar/', PropertyCalendarView.as_view(), name='property-calendar'),
    
    # Blocked dates management
    path('blocked-dates/', BlockedDateListCreateView.as_view(), name='blocked-dates-list'),
    path('blocked-dates/<int:pk>/', BlockedDateDetailView.as_view(), name='blocked-dates-detail'),
    
    # Admin endpoints
    path('admin/bookings/', AdminBookingListView.as_view(), name='admin-bookings'),
    
    # Reports endpoints (Admin only)
    path('reports/dashboard/', DashboardSummaryView.as_view(), name='dashboard-summary'),
    path('reports/bookings/', BookingReportsView.as_view(), name='booking-reports'),
    path('reports/payments/', PaymentReportsView.as_view(), name='payment-reports'),
    path('reports/properties/', PropertyReportsView.as_view(), name='property-reports'),
]