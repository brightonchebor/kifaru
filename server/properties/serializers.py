from rest_framework import serializers
from .models import (
    Property, Amenity, Highlight, PropertyImage, Review,
    PropertyPricing, PropertyFeature, PropertyContact, PropertyNetwork
)
import json


class AmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = ['icon', 'label']


class HighlightSerializer(serializers.ModelSerializer):
    class Meta:
        model = Highlight
        fields = ['text']


class PropertyImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyImage
        fields = ['id', 'image', 'order']

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if instance.image:
            rep['image'] = instance.image.url
        return rep


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    
    class Meta:
        model = Review
        fields = ['id', 'user', 'user_name', 'rating', 'comment', 'created_at']
        read_only_fields = ['created_at']


class PropertyPricingSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyPricing
        fields = [
            'id', 'accommodation_type', 'guest_type', 'stay_type',
            'min_nights', 'max_nights', 'price_per_night', 'weekly_price',
            'includes_breakfast', 'includes_fullboard'
        ]


class PropertyFeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyFeature
        fields = ['id', 'feature_type', 'name', 'description', 'icon']


class PropertyContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyContact
        fields = ['id', 'name', 'role', 'email', 'phone', 'whatsapp']


class PropertyNetworkSerializer(serializers.ModelSerializer):
    related_property_name = serializers.CharField(source='related_property.name', read_only=True)
    related_property_slug = serializers.CharField(source='related_property.slug', read_only=True)
    
    class Meta:
        model = PropertyNetwork
        fields = [
            'id', 'related_property', 'related_property_name', 'related_property_slug',
            'travel_time_minutes', 'transport_available', 'description'
        ]


class PropertySerializer(serializers.ModelSerializer):
    amenities = AmenitySerializer(many=True, required=False)
    highlights = HighlightSerializer(many=True, required=False)
    images = PropertyImageSerializer(many=True, read_only=True)
    pricing_options = PropertyPricingSerializer(many=True, read_only=True)
    features = PropertyFeatureSerializer(many=True, read_only=True)
    contacts = PropertyContactSerializer(many=True, read_only=True)
    network_properties = PropertyNetworkSerializer(source='network_from', many=True, read_only=True)
    background_image = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = [
            'id', 'name', 'slug', 'location', 'country', 
            'property_category', 'price', 'description',
            'bedrooms', 'bathrooms', 'square_meters', 'terrace_size', 'max_guests',
            'min_nights', 'check_in_time', 'check_out_time', 'prepayment_percentage',
            'cancellation_days', 'background_image',
            'wifi_password', 'amenities', 'highlights', 'images',
            'pricing_options', 'features', 'contacts', 'network_properties',
            'average_rating', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'slug']

    def get_background_image(self, obj):
        if obj.background_image:
            return obj.background_image.url
        return None
    
    def get_average_rating(self, obj):
        reviews = obj.reviews.all()
        if reviews:
            return round(sum(r.rating for r in reviews) / len(reviews), 1)
        return None

    def _create_nested(self, property_obj, amenities_data, highlights_data):
        if amenities_data:
            for amen in amenities_data:
                Amenity.objects.create(property=property_obj, **amen)
        if highlights_data:
            for hl in highlights_data:
                text = hl.get('text') if isinstance(hl, dict) else hl
                Highlight.objects.create(property=property_obj, text=text)

    def create(self, validated_data):
        amenities_data = validated_data.pop('amenities', [])
        highlights_data = validated_data.pop('highlights', [])
        prop = Property.objects.create(**validated_data)
        self._create_nested(prop, amenities_data, highlights_data)
        return prop

    def update(self, instance, validated_data):
        amenities_data = validated_data.pop('amenities', None)
        highlights_data = validated_data.pop('highlights', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if amenities_data is not None:
            instance.amenities.all().delete()
            self._create_nested(instance, amenities_data, highlights_data)
        elif highlights_data is not None:
            instance.highlights.all().delete()
            self._create_nested(instance, [], highlights_data)

        return instance

