from rest_framework import serializers
from .models import Property, Amenity, Highlight, PropertyImage, Review


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
        fields = ['image_url', 'order']


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ['id', 'user', 'rating', 'comment', 'created_at']
        read_only_fields = ['created_at']


class PropertySerializer(serializers.ModelSerializer):
    amenities = AmenitySerializer(many=True)
    highlights = HighlightSerializer(many=True)
    images = PropertyImageSerializer(many=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    geolocation = serializers.SerializerMethodField()
    
    class Meta:
        model = Property
        fields = '__all__'
    
    def get_geolocation(self, obj):
        return [obj.latitude, obj.longitude]
    
    def create(self, validated_data):
        amenities_data = validated_data.pop('amenities', [])
        highlights_data = validated_data.pop('highlights', [])
        images_data = validated_data.pop('images', [])
        
        property_instance = Property.objects.create(**validated_data)
        
        for amenity in amenities_data:
            Amenity.objects.create(property=property_instance, **amenity)
        
        for highlight in highlights_data:
            Highlight.objects.create(property=property_instance, **highlight)
        
        for image in images_data:
            PropertyImage.objects.create(property=property_instance, **image)
        
        return property_instance
    
    def update(self, instance, validated_data):
        amenities_data = validated_data.pop('amenities', None)
        highlights_data = validated_data.pop('highlights', None)
        images_data = validated_data.pop('images', None)
        
        # Update property fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update amenities
        if amenities_data is not None:
            instance.amenities.all().delete()
            for amenity in amenities_data:
                Amenity.objects.create(property=instance, **amenity)
        
        # Update highlights
        if highlights_data is not None:
            instance.highlights.all().delete()
            for highlight in highlights_data:
                Highlight.objects.create(property=instance, **highlight)
        
        # Update images
        if images_data is not None:
            instance.images.all().delete()
            for image in images_data:
                PropertyImage.objects.create(property=instance, **image)
        
        return instance
