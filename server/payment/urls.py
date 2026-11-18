from django.urls import path
from .views import (
    AdminPaymentListView,
    PaymentRecordView,
    PaymentDetailView,
    BookingPaymentView,
    PaymentRefundView,
    UserPaymentsView,
)

urlpatterns = [
    path('my-payments/', UserPaymentsView.as_view(), name='my-payments'),
    path('payments/my-payments/', UserPaymentsView.as_view(), name='payments-my-payments'),
    # Admin manual payment endpoints
    path('admin/payments/', AdminPaymentListView.as_view(), name='admin-payments'),
    path('payments/record/', PaymentRecordView.as_view(), name='payment-record'),
    path('payments/<int:pk>/', PaymentDetailView.as_view(), name='payment-detail'),
    path('payments/<int:pk>/refunds/', PaymentRefundView.as_view(), name='payment-refund'),
    path('payments/booking/<int:booking_id>/', BookingPaymentView.as_view(), name='payment-by-booking'),
]
