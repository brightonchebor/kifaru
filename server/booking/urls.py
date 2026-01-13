from django.urls import path
from .views import (
    BookingListCreateView,
    BookingDetailView,
    BookingCreateWithPaymentView,
    BookingCancelView,
    UserBookingsView,
    PropertyAvailabilityView,
    AdminBookingListView,
)


urlpatterns = [
    # User booking endpoints
    path('bookings/', BookingListCreateView.as_view(), name='booking-list-create'),
    path('bookings/<int:pk>/', BookingDetailView.as_view(), name='booking-detail'),
    path('bookings/create-with-payment/', BookingCreateWithPaymentView.as_view(), name='booking-create-payment'),
    path('bookings/<int:pk>/cancel/', BookingCancelView.as_view(), name='booking-cancel'),
    path('bookings/my-bookings/', UserBookingsView.as_view(), name='user-bookings'),
    
    # Property availability
    path('properties/<int:property_id>/availability/', PropertyAvailabilityView.as_view(), name='property-availability'),
    
    # Admin endpoints
    path('admin/bookings/', AdminBookingListView.as_view(), name='admin-bookings'),
]