from rest_framework import generics, filters, status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.db.models import Avg, Prefetch
from .models import (
    Property, PropertyImage, Review,
    PropertyFeature, PropertyPricing, PropertyContact, Gallery
)
from .serializers import (
    PropertySerializer, ReviewSerializer,
    PropertyFeatureSerializer,
    PropertyPricingSerializer, PropertyContactSerializer, GallerySerializer
)
from rest_framework.permissions import IsAuthenticatedOrReadOnly
import json


class PropertyListCreateView(generics.ListCreateAPIView):
    """
    List all properties or create a new property.
    
    GET: Public endpoint - anyone can view properties
        - Staff users only see their assigned properties
        - Filtering: country, category, bedrooms, bathrooms, price range, min_guests
        - Search: name, location, description
        - Ordering: price, created_at, bedrooms, max_guests
    
    POST: Authenticated users only
        - Handles multipart/form-data for image uploads
        - Multiple property images via 'images' field
        - Background image via 'background_image' field
    """
    
    queryset = Property.objects.all().select_related().prefetch_related(
        'amenities',
        'images',
        Prefetch('reviews', queryset=Review.objects.only('rating', 'property')),
        'pricing_options',
        'features',
        'contacts'
    ).annotate(
        average_rating=Avg('reviews__rating')
    )
    serializer_class = PropertySerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['country', 'property_category', 'bedrooms', 'bathrooms']
    search_fields = ['name', 'location', 'description']
    ordering_fields = ['price', 'created_at', 'bedrooms', 'max_guests']
    
    def get_permissions(self):
        """Only admin/staff can create properties, everyone can view"""
        if self.request.method == 'POST':
            return [IsAdminUser()]
        return [AllowAny()]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by user role - staff sees only assigned properties
        user = self.request.user
        if user.is_authenticated and user.role == 'staff':
            assigned_property_ids = user.assigned_properties.values_list('id', flat=True)
            queryset = queryset.filter(id__in=assigned_property_ids)
        
        # Filter by price range
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        if min_price:
            queryset = queryset.filter(price__gte=min_price)
        if max_price:
            queryset = queryset.filter(price__lte=max_price)
        
        # Filter by minimum guests
        min_guests = self.request.query_params.get('min_guests')
        if min_guests:
            queryset = queryset.filter(max_guests__gte=min_guests)
        
        return queryset

    def post(self, request, *args, **kwargs):
        # Serializer handles JSON parsing in to_internal_value()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Let the serializer handle everything (nested data + images)
        prop = serializer.save()

        return Response(self.get_serializer(prop, context={'request': request}).data, status=status.HTTP_201_CREATED)


class PropertyDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or delete a property by slug.
    
    GET: Public - anyone can view property details
    PUT/PATCH: Admin only
        - Updates property, handles image uploads
        - Replacing images deletes old ones
    DELETE: Admin only
    
    Lookup by: slug (e.g., /properties/kifaru-brussels/)
    """
    queryset = Property.objects.all().prefetch_related(
        'amenities', 'highlights', 'images', 'reviews', 'pricing_options',
        'features', 'contacts', 'network_from'
    )
    serializer_class = PropertySerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    lookup_field = 'slug'
    
    def get_permissions(self):
        """Only admin can update/delete properties, everyone can view"""
        if self.request.method in ['PUT', 'PATCH', 'DELETE']:
            return [IsAdminUser()]
        return [AllowAny()]

    def put(self, request, *args, **kwargs):
        return self._update(request, partial=False)

    def patch(self, request, *args, **kwargs):
        return self._update(request, partial=True)

    def _update(self, request, partial):
        instance = self.get_object()
        data = request.data.copy()
        for field in ('amenities', 'highlights', 'pricing_options', 'features', 'contacts'):
            if field in data and isinstance(data. get(field), str):
                try:
                    data[field] = json.loads(data. get(field))
                except Exception:
                    return Response({'detail': f'{field} must be valid JSON.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        # Let the serializer handle everything (nested data + images)
        prop = serializer.save()

        return Response(self.get_serializer(prop, context={'request': request}).data)


class ReviewListCreateView(generics.ListCreateAPIView):
    """
    List all reviews or create a new review.
    
    GET: Public - view all reviews
        - Filter by property: ?property=<property_id>
    POST: Create new review for a property
    """
    queryset = Review.objects. all()
    serializer_class = ReviewSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['property']
    pagination_class = PageNumberPagination


class ReviewDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or delete a specific review.
    
    GET: View review details
    PUT/PATCH: Update review
    DELETE: Delete review
    """
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer


# Phase 2: Property Nested Resources CRUD

class PropertyFeatureListCreateView(generics.ListCreateAPIView):
    """
    List features for a property or create new feature.
    
    GET: Public - view all features for a property
    POST: Admin only - create new feature for property
    
    URL: /properties/{slug}/features/
    Example: Feature(icon='wifi', title='High-Speed WiFi', description='...')
    """
    serializer_class = PropertyFeatureSerializer
    
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminUser()]
        return [AllowAny()]
    
    def get_queryset(self):
        property_slug = self.kwargs['property_slug']
        property_obj = get_object_or_404(Property, slug=property_slug)
        return PropertyFeature.objects.filter(property=property_obj)
    
    def perform_create(self, serializer):
        property_slug = self.kwargs['property_slug']
        property_obj = get_object_or_404(Property, slug=property_slug)
        serializer.save(property=property_obj)


class PropertyFeatureDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or delete a property feature.
    
    GET: Public - view feature details
    PUT/PATCH: Admin only - update feature
    DELETE: Admin only - delete feature
    
    URL: /properties/{slug}/features/{id}/
    """
    serializer_class = PropertyFeatureSerializer
    
    def get_permissions(self):
        if self.request.method in ['PUT', 'PATCH', 'DELETE']:
            return [IsAdminUser()]
        return [AllowAny()]
    
    def get_queryset(self):
        # Handle swagger schema generation
        if getattr(self, 'swagger_fake_view', False):
            return PropertyFeature.objects.none()
        
        property_slug = self.kwargs['property_slug']
        property_obj = get_object_or_404(Property, slug=property_slug)
        return PropertyFeature.objects.filter(property=property_obj)


class PropertyPricingListCreateView(generics.ListCreateAPIView):
    """
    List pricing options for a property or create new pricing.
    
    GET: Public - view all pricing tiers for a property
        Returns pricing by: guest_type (local/foreign), stay_type (short/long/weekly),
        accommodation_type (master_bedroom/full_apartment), number_of_guests
    
    POST: Admin only - create new pricing tier
    
    URL: /properties/{slug}/pricing/
    Critical for booking price calculations.
    """
    serializer_class = PropertyPricingSerializer
    
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminUser()]
        return [AllowAny()]
    
    def get_queryset(self):
        property_slug = self.kwargs['property_slug']
        property_obj = get_object_or_404(Property, slug=property_slug)
        return PropertyPricing.objects.filter(property=property_obj)
    
    def perform_create(self, serializer):
        property_slug = self.kwargs['property_slug']
        property_obj = get_object_or_404(Property, slug=property_slug)
        serializer.save(property=property_obj)


class PropertyPricingDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or delete a property pricing option.
    
    GET: Public - view specific pricing tier
    PUT/PATCH: Admin only - update pricing
    DELETE: Admin only - delete pricing tier
    
    URL: /properties/{slug}/pricing/{id}/
    """
    serializer_class = PropertyPricingSerializer
    
    def get_permissions(self):
        if self.request.method in ['PUT', 'PATCH', 'DELETE']:
            return [IsAdminUser()]
        return [AllowAny()]
    
    def get_queryset(self):
        # Handle swagger schema generation
        if getattr(self, 'swagger_fake_view', False):
            return PropertyPricing.objects.none()
        
        property_slug = self.kwargs['property_slug']
        property_obj = get_object_or_404(Property, slug=property_slug)
        return PropertyPricing.objects.filter(property=property_obj)


class PropertyContactListCreateView(generics.ListCreateAPIView):
    """
    List contacts for a property or create new contact.
    
    GET: Public - view all contacts (property managers, caretakers, etc.)
    POST: Admin only - add new contact for property
    
    URL: /properties/{slug}/contacts/
    Example: Contact(name='John Doe', role='Property Manager', phone='+123...')
    """
    serializer_class = PropertyContactSerializer
    
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminUser()]
        return [AllowAny()]
    
    def get_queryset(self):
        property_slug = self.kwargs['property_slug']
        property_obj = get_object_or_404(Property, slug=property_slug)
        return PropertyContact.objects.filter(property=property_obj)
    
    def perform_create(self, serializer):
        property_slug = self.kwargs['property_slug']
        property_obj = get_object_or_404(Property, slug=property_slug)
        serializer.save(property=property_obj)


class PropertyContactDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or delete a property contact.
    
    GET: Public - view contact details
    PUT/PATCH: Admin only - update contact
    DELETE: Admin only - delete contact
    
    URL: /properties/{slug}/contacts/{id}/
    """
    serializer_class = PropertyContactSerializer
    
    def get_permissions(self):
        if self.request.method in ['PUT', 'PATCH', 'DELETE']:
            return [IsAdminUser()]
        return [AllowAny()]
    
    def get_queryset(self):
        # Handle swagger schema generation
        if getattr(self, 'swagger_fake_view', False):
            return PropertyContact.objects.none()
        
        property_slug = self.kwargs['property_slug']
        property_obj = get_object_or_404(Property, slug=property_slug)
        return PropertyContact.objects.filter(property=property_obj)


@api_view(['POST'])
@permission_classes([AllowAny])
def check_availability(request, slug):
    """
    Check if a property is available for specific dates.
    
    POST: Public endpoint
    Request body: {"start_date": "2026-03-01", "end_date": "2026-03-07"}
    
    Checks for overlapping pending/confirmed bookings.
    Cancelled bookings don't block availability.
    
    Note: Prefer using /api/properties/{id}/availability/ (from booking app)
    which is the canonical availability endpoint.
    """
    try:
        property_obj = Property.objects.get(slug=slug)
    except Property.DoesNotExist:
        return Response({'error': 'Property not found'}, status=status.HTTP_404_NOT_FOUND)
    
    start_date = request.data.get('start_date')
    end_date = request.data.get('end_date')
    
    if not start_date or not end_date:
        return Response(
            {'error': 'start_date and end_date are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    from booking.models import Booking
    from datetime import datetime
    
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        return Response(
            {'error': 'Invalid date format. Use YYYY-MM-DD'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check for overlapping bookings
    overlapping = Booking.objects.filter(
        property=property_obj,
        status__in=['pending', 'confirmed'],
        check_in__lt=end,
        check_out__gt=start
    )
    
    is_available = not overlapping.exists()
    
    return Response({
        'available': is_available,
        'property': property_obj.name,
        'start_date': start_date,
        'end_date': end_date,
        'message': 'Available' if is_available else 'Not available for selected dates'
    })
    serializer_class = ReviewSerializer


class GalleryListView(generics.ListCreateAPIView):
    """
    GET: Anyone can view active gallery images
        - Only returns active images for public
        - Optional filtering by category via query param: ?category=lifestyle
    
    POST: Admin only - create new gallery image
        - Upload image file with metadata (title, category, order, etc.)
    """
    serializer_class = GallerySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['category', 'is_featured']
    
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAdminUser()]
    
    def get_queryset(self):
        # Admin sees all, public sees only active
        if self.request.user.is_staff:
            return Gallery.objects.all()
        return Gallery.objects.filter(is_active=True)


class GalleryDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET: Anyone can view single gallery image
    PUT/PATCH: Admin only - update gallery image
    DELETE: Admin only - delete gallery image
    """
    serializer_class = GallerySerializer
    queryset = Gallery.objects.all()
    lookup_field = 'pk'
    
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAdminUser()]