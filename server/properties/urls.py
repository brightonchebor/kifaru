from django.urls import path
from .views import (
    PropertyListCreateView,
    PropertyDetailView,
    ReviewListCreateView,
    ReviewDetailView,
    PropertyFeatureListCreateView,
    PropertyFeatureDetailView,
    PropertyPricingListCreateView,
    PropertyPricingDetailView,
    PropertyContactListCreateView,
    PropertyContactDetailView,
    check_availability,
    GalleryListView,
    GalleryDetailView,
)

app_name = 'properties'

urlpatterns = [
    # Properties
    path('properties/', PropertyListCreateView.as_view(), name='property-list'),
    path('properties/<slug:slug>/', PropertyDetailView.as_view(), name='property-detail'),
    path('properties/<slug:slug>/availability/', check_availability, name='property-availability'),
    
    # Phase 2: Property Nested Resources
    path('properties/<slug:property_slug>/features/', PropertyFeatureListCreateView.as_view(), name='property-feature-list'),
    path('properties/<slug:property_slug>/features/<int:pk>/', PropertyFeatureDetailView.as_view(), name='property-feature-detail'),
    path('properties/<slug:property_slug>/pricing/', PropertyPricingListCreateView.as_view(), name='property-pricing-list'),
    path('properties/<slug:property_slug>/pricing/<int:pk>/', PropertyPricingDetailView.as_view(), name='property-pricing-detail'),
    path('properties/<slug:property_slug>/contacts/', PropertyContactListCreateView.as_view(), name='property-contact-list'),
    path('properties/<slug:property_slug>/contacts/<int:pk>/', PropertyContactDetailView.as_view(), name='property-contact-detail'),
    
    # Reviews
    path('reviews/', ReviewListCreateView.as_view(), name='review-list'),
    path('reviews/<int:pk>/', ReviewDetailView.as_view(), name='review-detail'),
    
    # Gallery
    path('gallery/', GalleryListView.as_view(), name='gallery-list'),
    path('gallery/<int:pk>/', GalleryDetailView.as_view(), name='gallery-detail'),
]
