from rest_framework import generics, filters, status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from .models import (
    Property, PropertyImage, Review,
    PropertyFeature, PropertyPricing, PropertyContact
)
from .serializers import (
    PropertySerializer, ReviewSerializer,
    PropertyFeatureSerializer,
    PropertyPricingSerializer, PropertyContactSerializer
)
from rest_framework.permissions import IsAuthenticatedOrReadOnly
import json


class PropertyListCreateView(generics.ListCreateAPIView):
    queryset = Property.objects.all().prefetch_related(
        'amenities', 'highlights', 'images', 'reviews', 'pricing_options',
        'features', 'contacts', 'network_from'
    )
    serializer_class = PropertySerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'country', 'continent', 'property_category', 'bedrooms', 'bathrooms']
    search_fields = ['name', 'location', 'description']
    ordering_fields = ['price', 'created_at', 'bedrooms', 'max_guests']
    
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
        data = request.data. copy()  # QueryDict -> mutable
        # If frontend sent nested fields as JSON strings (multipart), parse them
        for field in ('amenities', 'highlights'):
            if field in data and isinstance(data.get(field), str):
                try:
                    data[field] = json.loads(data.get(field))
                except Exception:
                    return Response({'detail': f'{field} must be valid JSON.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        
        # Handle background_image upload
        background_image = request.FILES.get('background_image')
        if background_image:
            prop = serializer.save(background_image=background_image)
        else:
            prop = serializer.save()

        # handle uploaded files: multiple images under key "images"
        images = request.FILES.getlist('images')
        for idx, img in enumerate(images):
            PropertyImage.objects.create(property=prop, image=img, order=idx)

        return Response(self.get_serializer(prop, context={'request': request}).data, status=status.HTTP_201_CREATED)


class PropertyDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Property.objects.all().prefetch_related(
        'amenities', 'highlights', 'images', 'reviews', 'pricing_options',
        'features', 'contacts', 'network_from'
    )
    serializer_class = PropertySerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [IsAuthenticatedOrReadOnly]
    lookup_field = 'slug'

    def put(self, request, *args, **kwargs):
        return self._update(request, partial=False)

    def patch(self, request, *args, **kwargs):
        return self._update(request, partial=True)

    def _update(self, request, partial):
        instance = self.get_object()
        data = request.data.copy()
        for field in ('amenities', 'highlights'):
            if field in data and isinstance(data. get(field), str):
                try:
                    data[field] = json.loads(data. get(field))
                except Exception:
                    return Response({'detail': f'{field} must be valid JSON.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        # Handle background_image upload
        background_image = request.FILES.get('background_image')
        if background_image:
            prop = serializer.save(background_image=background_image)
        else:
            prop = serializer.save()

        # If images uploaded, replace existing images
        images = request.FILES.getlist('images')
        if images:
            prop.images.all(). delete()
            for idx, img in enumerate(images):
                PropertyImage.objects.create(property=prop, image=img, order=idx)

        return Response(self.get_serializer(prop, context={'request': request}).data)


class ReviewListCreateView(generics.ListCreateAPIView):
    queryset = Review.objects. all()
    serializer_class = ReviewSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['property']


class ReviewDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer


# Phase 2: Property Nested Resources CRUD

class PropertyFeatureListCreateView(generics.ListCreateAPIView):
    """List features for a property or create new feature (admin only)"""
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
    """Get, update, or delete a property feature (admin only for modifications)"""
    serializer_class = PropertyFeatureSerializer
    
    def get_permissions(self):
        if self.request.method in ['PUT', 'PATCH', 'DELETE']:
            return [IsAdminUser()]
        return [AllowAny()]
    
    def get_queryset(self):
        property_slug = self.kwargs['property_slug']
        property_obj = get_object_or_404(Property, slug=property_slug)
        return PropertyFeature.objects.filter(property=property_obj)


class PropertyPricingListCreateView(generics.ListCreateAPIView):
    """List pricing options for a property or create new pricing (admin only)"""
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
    """Get, update, or delete a property pricing option (admin only for modifications)"""
    serializer_class = PropertyPricingSerializer
    
    def get_permissions(self):
        if self.request.method in ['PUT', 'PATCH', 'DELETE']:
            return [IsAdminUser()]
        return [AllowAny()]
    
    def get_queryset(self):
        property_slug = self.kwargs['property_slug']
        property_obj = get_object_or_404(Property, slug=property_slug)
        return PropertyPricing.objects.filter(property=property_obj)


class PropertyContactListCreateView(generics.ListCreateAPIView):
    """List contacts for a property or create new contact (admin only)"""
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
    """Get, update, or delete a property contact (admin only for modifications)"""
    serializer_class = PropertyContactSerializer
    
    def get_permissions(self):
        if self.request.method in ['PUT', 'PATCH', 'DELETE']:
            return [IsAdminUser()]
        return [AllowAny()]
    
    def get_queryset(self):
        property_slug = self.kwargs['property_slug']
        property_obj = get_object_or_404(Property, slug=property_slug)
        return PropertyContact.objects.filter(property=property_obj)


@api_view(['POST'])
@permission_classes([AllowAny])
def check_availability(request, slug):
    """Check if a property is available for specific dates"""
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