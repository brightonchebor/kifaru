from django.urls import path
from .views import (
    PromoCodeListCreateView,
    PromoCodeDetailView,
    PromoCodeGenerateView,
    PromoCodeUsageView,
    PromoValidateView,
)

urlpatterns = [
    # Public
    path('promos/validate/', PromoValidateView.as_view(), name='promo-validate'),

    # Admin — specific paths before generic ones
    path('promos/generate/', PromoCodeGenerateView.as_view(), name='promo-generate'),
    path('promos/<int:pk>/usage/', PromoCodeUsageView.as_view(), name='promo-usage'),
    path('promos/<int:pk>/', PromoCodeDetailView.as_view(), name='promo-detail'),
    path('promos/', PromoCodeListCreateView.as_view(), name='promo-list-create'),
]
