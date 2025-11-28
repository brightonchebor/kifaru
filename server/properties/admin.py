from django.contrib import admin
from .models import Property, Amenity, Highlight, PropertyImage, Review


class AmenityInline(admin.TabularInline):
    model = Amenity
    extra = 1


class HighlightInline(admin.TabularInline):
    model = Highlight
    extra = 1


class PropertyImageInline(admin.TabularInline):
    model = PropertyImage
    extra = 1


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ['name', 'location', 'country', 'status', 'price', 'created_at']
    list_filter = ['status', 'country', 'created_at']
    search_fields = ['name', 'location', 'description']
    inlines = [AmenityInline, HighlightInline, PropertyImageInline]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['property', 'user', 'rating', 'created_at']
    list_filter = ['rating', 'created_at']
