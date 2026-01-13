from rest_framework import serializers
from .models import (
    CompanyInfo, TeamMember, Service, Testimonial,
    FAQ, CulturalHighlight, NewsletterSubscriber
)


class CompanyInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyInfo
        fields = [
            'id', 'mission_statement', 'vision_statement', 'about_text',
            'brand_story', 'tagline', 'kifaru_meaning', 'primary_contact_email',
            'whatsapp_number', 'facebook_url', 'instagram_url', 'linkedin_url',
            'reference_website', 'updated_at'
        ]
        read_only_fields = ['updated_at']


class TeamMemberSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source='property.name', read_only=True)
    photo_url = serializers.SerializerMethodField()
    
    class Meta:
        model = TeamMember
        fields = [
            'id', 'name', 'role', 'bio', 'photo', 'photo_url',
            'property', 'property_name', 'email', 'order', 'is_featured'
        ]
    
    def get_photo_url(self, obj):
        if obj.photo:
            return obj.photo.url
        return None


class ServiceSerializer(serializers.ModelSerializer):
    available_at_names = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Service
        fields = [
            'id', 'title', 'category', 'description', 'icon', 'image', 'image_url',
            'available_at', 'available_at_names', 'is_featured', 'order'
        ]
    
    def get_available_at_names(self, obj):
        return [p.name for p in obj.available_at.all()]
    
    def get_image_url(self, obj):
        if obj.image:
            return obj.image.url
        return None


class TestimonialSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source='property.name', read_only=True)
    guest_photo_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Testimonial
        fields = [
            'id', 'guest_name', 'guest_photo', 'guest_photo_url', 'content',
            'rating', 'property', 'property_name', 'is_approved', 'is_featured',
            'created_at'
        ]
        read_only_fields = ['created_at', 'is_approved']
    
    def get_guest_photo_url(self, obj):
        if obj.guest_photo:
            return obj.guest_photo.url
        return None


class FAQSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source='property.name', read_only=True)
    
    class Meta:
        model = FAQ
        fields = [
            'id', 'question', 'answer', 'category', 'property',
            'property_name', 'order', 'is_published'
        ]


class CulturalHighlightSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source='property.name', read_only=True)
    image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = CulturalHighlight
        fields = [
            'id', 'property', 'property_name', 'title', 'description',
            'category', 'image', 'image_url', 'order'
        ]
    
    def get_image_url(self, obj):
        if obj.image:
            return obj.image.url
        return None


class NewsletterSubscriberSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsletterSubscriber
        fields = [
            'id', 'email', 'name', 'preferred_language', 'interests',
            'subscribed_at', 'is_active'
        ]
        read_only_fields = ['subscribed_at']
