from django.urls import path
from .views import (
    PropertyListCreateView,
    PropertyDetailView,
    ReviewListCreateView,
    ReviewDetailView
)

app_name = 'properties'

urlpatterns = [
    path('properties/', PropertyListCreateView.as_view(), name='property-list'),
    path('properties/<int:pk>/', PropertyDetailView.as_view(), name='property-detail'),
    path('reviews/', ReviewListCreateView.as_view(), name='review-list'),
    path('reviews/<int:pk>/', ReviewDetailView.as_view(), name='review-detail'),
]
