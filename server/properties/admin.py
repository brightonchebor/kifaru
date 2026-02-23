from django.contrib import admin
from .models import (
    Property, Amenity, Highlight, PropertyImage, Review,
    PropertyPricing, PropertyFeature, PropertyContact, PropertyNetwork, Gallery
)


class AmenityInline(admin.TabularInline):
    model = Amenity
    extra = 1
    readonly_fields = ('image_preview',)
    
    def image_preview(self, instance):
        if instance.image:
            return f'<img src="{instance.image.url}" style="height: 50px;" />'
        return ''
    image_preview.allow_tags = True
    image_preview.short_description = 'Preview'


class HighlightInline(admin.TabularInline):
    model = Highlight
    extra = 1


class PropertyImageInline(admin.TabularInline):
    model = PropertyImage
    extra = 1
    readonly_fields = ('preview',)

    def preview(self, instance):
        if instance.image:
            return f'<img src="{instance.image.url}" style="height: 100px;" />'
        return ''
    preview.allow_tags = True
    preview.short_description = 'Preview'


class PropertyPricingInline(admin.TabularInline):
    model = PropertyPricing
    extra = 1


class PropertyFeatureInline(admin.TabularInline):
    model = PropertyFeature
    extra = 1


class PropertyContactInline(admin.TabularInline):
    model = PropertyContact
    extra = 1


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'tagline', 'location', 'country', 'property_category', 'price', 'bedrooms', 'max_guests'
    ]
    list_filter = ['country', 'property_category', 'bedrooms', 'created_at']
    search_fields = ['name', 'tagline', 'location', 'location_description', 'description']
    readonly_fields = ['slug', 'created_at', 'updated_at']
    inlines = [
        AmenityInline, HighlightInline, PropertyImageInline, PropertyPricingInline, PropertyFeatureInline, PropertyContactInline
    ]
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'tagline', 'slug', 'location', 'location_description', 'country', 'property_category')
        }),
        ('Property Details', {
            'fields': ('description', 'bedrooms', 'bathrooms', 'square_meters', 'terrace_size', 'max_guests')
        }),
        ('Pricing & Booking', {
            'fields': ('price', 'min_nights', 'check_in_time', 'check_out_time', 'prepayment_percentage', 'cancellation_days')
        }),
        ('Media', {
            'fields': ('background_image', 'wifi_password')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ['category', 'icon', 'title']
    list_filter = ['property']
    search_fields = ['title']
    # readonly_fields = ('image_preview',)
    
    # def image_preview(self, instance):
    #     if instance.image:
    #         return f'<img src="{instance.image.url}" style="height: 50px;" />'
    #     return ''
    # image_preview.allow_tags = True
    # image_preview.short_description = 'Image'

@admin.register(Highlight)
class HighlightAdmin(admin.ModelAdmin):
    list_display = ['image_preview', 'title']
    list_filter = ['property']
    search_fields = ['title']
    readonly_fields = ('image_preview',)
    
    def image_preview(self, instance):
        if instance.image:
            return f'<img src="{instance.image.url}" style="height: 50px;" />'
        return ''
    image_preview.allow_tags = True
    image_preview.short_description = 'Image'


@admin.register(PropertyPricing)
class PropertyPricingAdmin(admin.ModelAdmin):
    list_display = ['property', 'accommodation_type', 'guest_type', 'stay_type', 'price_per_night', 'weekly_price', 'includes_breakfast', 'includes_fullboard']
    list_filter = ['accommodation_type', 'guest_type', 'stay_type', 'property']
    search_fields = ['property__name']


@admin.register(PropertyFeature)
class PropertyFeatureAdmin(admin.ModelAdmin):
    list_display = ['property', 'name', 'feature_type', 'order']
    list_filter = ['feature_type', 'property']
    search_fields = ['name', 'description']
    list_editable = ['order']


@admin.register(PropertyContact)
class PropertyContactAdmin(admin.ModelAdmin):
    list_display = ['name', 'property', 'role', 'email']
    list_filter = ['property']
    search_fields = ['name', 'email', 'role']


@admin.register(PropertyNetwork)
class PropertyNetworkAdmin(admin.ModelAdmin):
    list_display = ['property', 'related_property', 'travel_time_minutes', 'transport_available']
    list_filter = ['transport_available']



@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['property', 'reviewer_name', 'rating', 'created_at']
    list_filter = ['rating', 'created_at', 'property']
    search_fields = ['reviewer_name', 'comment', 'property__name']
    date_hierarchy = 'created_at'


@admin.register(Gallery)
class GalleryAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'order', 'is_featured', 'is_active', 'created_at', 'image_preview']
    list_filter = ['category', 'is_featured', 'is_active', 'created_at']
    search_fields = ['title', 'category']
    list_editable = ['order', 'is_featured', 'is_active']
    readonly_fields = ['image_preview', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Image', {
            'fields': ('image', 'image_preview')
        }),
        ('Details', {
            'fields': ('title', 'category', 'order')
        }),
        ('Status', {
            'fields': ('is_featured', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def image_preview(self, instance):
        if instance.image:
            return f'<img src="{instance.image.url}" style="max-height: 200px; max-width: 300px;" />'
        return 'No image'
    image_preview.allow_tags = True
    image_preview.short_description = 'Preview'
