from rest_framework import generics, filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import Property, Review
from .serializers import PropertySerializer, ReviewSerializer


class PropertyListCreateView(generics.ListCreateAPIView):
    queryset = Property.objects.all().prefetch_related('amenities', 'highlights', 'images', 'reviews')
    serializer_class = PropertySerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'country']
    search_fields = ['name', 'location', 'description']
    ordering_fields = ['price', 'created_at']


class PropertyDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Property.objects.all().prefetch_related('amenities', 'highlights', 'images', 'reviews')
    serializer_class = PropertySerializer


class ReviewListCreateView(generics.ListCreateAPIView):
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['property']


class ReviewDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer
