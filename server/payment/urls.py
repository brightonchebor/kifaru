from django.urls import path
from .views import (
    PaymentProcessView,
    AdminPaymentListView,
)


urlpatterns = [    
    # Payment endpoints
    path('payments/process/', PaymentProcessView.as_view(), name='payment-process'),
    
    # Admin endpoints
    path('admin/payments/', AdminPaymentListView.as_view(), name='admin-payments'),
]