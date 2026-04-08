from rest_framework import serializers
from .models import (
    Property, Amenity, Highlight, PropertyImage, Review,
    PropertyPricing, PropertyFeature, PropertyContact, Gallery
)
import json


class AmenitySerializer(serializers.ModelSerializer):
    # image = serializers.ImageField(required=False, allow_null=True)
    
    class Meta:
        model = Amenity
        # fields = ['image', 'label']
        fields = ['category', 'icon','title']
    
    # def to_representation(self, instance):
    #     rep = super().to_representation(instance)
    #     if instance.image:
    #         rep['image'] = instance.image.url
    #     return rep


class HighlightSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = Highlight
        fields = ['title', 'image']
    
    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if instance.image:
            rep['image'] = instance.image.url
        return rep


class PropertyImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyImage
        fields = ['id', 'image', 'category', 'order']

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if instance.image:
            rep['image'] = instance.image.url
        return rep


class ReviewSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source='property.name', read_only=True)
    
    class Meta:
        model = Review
        fields = ['id', 'property', 'property_name', 'reviewer_name', 'rating', 'comment', 'avatar', 'country', 'created_at']
        read_only_fields = ['created_at']


class PropertyPricingSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyPricing
        fields = [
            'id', 'accommodation_type', 'guest_type', 'stay_type', 'number_of_guests',
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


class PropertySerializer(serializers.ModelSerializer):
    # Read-only nested serializers for GET requests
    amenities = AmenitySerializer(many=True, read_only=True)
    highlights = HighlightSerializer(many=True, read_only=True)
    pricing_options = PropertyPricingSerializer(many=True, read_only=True)
    features = PropertyFeatureSerializer(many=True, read_only=True)
    contacts = PropertyContactSerializer(many=True, read_only=True)
    
    # Image fields - writable for POST/PUT, returns URL for GET
    background_image = serializers.ImageField(
        required=False, 
        allow_null=True,
        help_text="Upload property background/cover image"
    )
    
    images = serializers.ListField(
        child=serializers.ImageField(),
        write_only=True,
        required=False,
        help_text="Upload multiple property images (bedroom, kitchen, etc.)"
    )
    
    # Amenity image uploads (separate from amenities JSON)
    highlights_images = serializers.ListField(
        child=serializers.ImageField(),
        write_only=True,
        required=False,
        help_text="Upload amenity images (matches amenities array by index)"
    )
    
    # For GET requests - return image objects with metadata
    # For POST requests - accept metadata (category, order) matching the images array
    property_images = PropertyImageSerializer(source='images', many=True, read_only=True)
    
    average_rating = serializers.FloatField(read_only=True)

    class Meta:
        model = Property
        fields = [
            'id', 'name', 'slug', 'location', 'location_description', 'tagline', 'country', 
            'property_category', 'price', 'description',
            'bedrooms', 'bathrooms', 'square_meters', 'terrace_size', 'max_guests',
            'min_nights', 'check_in_time', 'check_out_time', 'prepayment_percentage',
            'cancellation_days', 'background_image', 'images', 'property_images',
            'wifi_password', 
            'amenities', 'highlights_images', 'highlights', 'pricing_options', 'features', 'contacts',
            'average_rating', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'slug', 'property_images']

    def to_internal_value(self, data):
        """Parse JSON strings from FormData and map to write-only fields. Also flatten grouped amenities input."""
        import json

        # Create a mutable copy of data
        if hasattr(data, '_mutable'):
            data._mutable = True

        field_mapping = {
            'amenities': 'amenities_data',
            'highlights': 'highlights_data',
            'pricing_options': 'pricing_options_data',
            'features': 'features_data',
            'contacts': 'contacts_data',
            'property_images': 'property_images_data'
        }

        is_update = self.instance is not None
        nested_data = {}
        for old_name, new_name in field_mapping.items():
            if old_name in data:
                value = data.pop(old_name)

                # For updates, SKIP read-only nested fields unless they're being explicitly edited
                if is_update and old_name in ['amenities', 'highlights', 'pricing_options', 'features', 'contacts']:
                    continue

                # Django QueryDict wraps values in lists, extract first element
                if isinstance(value, list) and len(value) == 1:
                    value = value[0]

                # Parse if it's a JSON string
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        pass

                # FLATTEN grouped amenities dict to list of amenity objects
                if old_name == 'amenities' and isinstance(value, dict):
                    flat_amenities = []
                    for category, items in value.items():
                        for item in items:
                            flat_amenity = dict(item)
                            flat_amenity['category'] = category
                            flat_amenities.append(flat_amenity)
                    value = flat_amenities

                nested_data[new_name] = value

        ret = super().to_internal_value(data)
        ret.update(nested_data)
        return ret
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Replace background_image with URL string in GET responses
        if instance.background_image:
            data['background_image'] = instance.background_image.url
        else:
            data['background_image'] = None
        # Remove images list from GET (already have property_images)
        data.pop('images', None)

        # Group amenities by category, but keep the field name 'amenities'
        amenities = data.get('amenities', [])
        grouped = {}
        for amenity in amenities:
            cat = amenity.get('category', 'other')
            grouped.setdefault(cat, []).append({
                'icon': amenity.get('icon'),
                'title': amenity.get('title')
            })
        data['amenities'] = grouped
        return data

    def _create_nested(self, property_obj, amenities_data, highlights_data, highlights_images=None):
        if amenities_data:
            for amen in amenities_data:
                category = amen.get('category') if isinstance(amen, dict) else 'other'
                icon = amen.get('icon') if isinstance(amen, dict) else ''
                title = amen.get('title') if isinstance(amen, dict) else ''
                Amenity.objects.create(property=property_obj, category=category, icon=icon, title=title)

        if highlights_data:
            for idx, hl in enumerate(highlights_data):
                hl_copy = hl.copy() if isinstance(hl, dict) else {'title': hl}
                hl_copy.pop('image', None)
                if highlights_images and idx < len(highlights_images):
                    hl_copy['image'] = highlights_images[idx]
                Highlight.objects.create(property=property_obj, **hl_copy)

    def create(self, validated_data):
        # Extract nested data from write-only fields
        amenities_data = validated_data.pop('amenities_data', [])
        highlights_data = validated_data.pop('highlights_data', [])
        pricing_data = validated_data.pop('pricing_options_data', [])
        features_data = validated_data.pop('features_data', [])
        contacts_data = validated_data.pop('contacts_data', [])
        highlights_images_files = validated_data.pop('highlights_images', [])
        images_files = validated_data.pop('images', [])
        images_metadata = validated_data.pop('property_images_data', [])

        # Create property (background_image is handled automatically by Django)
        prop = Property.objects.create(**validated_data)

        # Create amenities and highlights
        self._create_nested(prop, amenities_data, highlights_data, highlights_images_files)

        # Create pricing options (if provided)
        for pricing in pricing_data:
            PropertyPricing.objects.create(property=prop, **pricing)

        # Create features (if provided)
        for feature in features_data:
            PropertyFeature.objects.create(property=prop, **feature)

        # Create contacts (if provided)
        for contact in contacts_data:
            PropertyContact.objects.create(property=prop, **contact)

        # Create property images (if provided)
        for idx, img_file in enumerate(images_files):
            metadata = images_metadata[idx] if idx < len(images_metadata) else {}
            category = metadata.get('category', 'other')
            order = metadata.get('order', idx)
            PropertyImage.objects.create(
                property=prop,
                image=img_file,
                category=category,
                order=order
            )
        return prop

    def update(self, instance, validated_data):
        # Extract nested data (should be None for PATCH unless explicitly sent with images)
        amenities_data = validated_data.pop('amenities_data', None)
        highlights_data = validated_data.pop('highlights_data', None)
        pricing_data = validated_data.pop('pricing_options_data', None)
        features_data = validated_data.pop('features_data', None)
        contacts_data = validated_data.pop('contacts_data', None)
        images_files = validated_data.pop('images', None)
        amenity_images_files = validated_data.pop('amenity_images', None)
        validated_data.pop('property_images_data', None)

        # Update only changed property fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # These will only be processed if explicitly sent (e.g., with image uploads via FormData)
        # Normal JSON PATCH requests will skip these entirely due to to_internal_value filtering
        
        if images_files:
            # Add new property images (don't delete existing)
            for idx, img_file in enumerate(images_files):
                PropertyImage.objects.create(property=instance, image=img_file, order=idx)

        return instance


class GallerySerializer(serializers.ModelSerializer):
    class Meta:
        model = Gallery
        fields = ['id', 'image', 'title', 'category', 'order', 'is_featured', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def to_representation(self, instance):
        """Return image URL in GET responses"""
        data = super().to_representation(instance)
        if instance.image:
            data['image'] = instance.image.url
        return data
