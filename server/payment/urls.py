from django.urls import path
from .views import (
    AdminPaymentListView,
    PaymentInitializeView,
    PaymentVerifyView,
    PaystackWebhookView,
)


urlpatterns = [    
    # Paystack payment endpoints
    path('payments/initialize/', PaymentInitializeView.as_view(), name='payment-initialize'),
    path('payments/verify/<str:reference>/', PaymentVerifyView.as_view(), name='payment-verify'),
    path('payments/webhook/', PaystackWebhookView.as_view(), name='payment-webhook'),
    
    # Admin endpoints
    path('admin/payments/', AdminPaymentListView.as_view(), name='admin-payments'),
]