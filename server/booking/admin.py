from django.contrib import admin
from .models import Booking, BlockedDate

# Register your models here.
@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['booking_reference', 'full_name', 'email', 'user', 'property', 'check_in', 'check_out', 'total_amount', 'status', 'created_at']
    list_filter = ['status', 'accommodation_type', 'guest_type', 'stay_type', 'created_at', 'check_in']
    search_fields = ['booking_reference', 'user__email', 'property__name', 'full_name', 'email', 'id_passport_number']
    readonly_fields = ['booking_reference', 'total_days', 'total_amount', 'stay_type', 'guest_type', 'selected_pricing', 'includes_breakfast', 'includes_fullboard', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Booking Information', {
            'fields': ('booking_reference', 'user', 'property', 'status')
        }),
        ('Personal Details', {
            'fields': ('full_name', 'email', 'phone', 'id_passport_number')
        }),
        ('Booking Details', {
            'fields': ('accommodation_type', 'guest_type', 'stay_type', 'check_in', 'check_out', 
                      'number_of_guests', 'number_of_adults', 'number_of_children', 
                      'total_days', 'total_amount')
        }),
        ('Pricing & Meals', {
            'fields': ('selected_pricing', 'includes_breakfast', 'includes_fullboard')
        }),
        ('Additional Options', {
            'fields': ('dog_included', 'jacuzzi_reservation', 'special_requests')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(BlockedDate)
class BlockedDateAdmin(admin.ModelAdmin):
    list_display = ['property', 'start_date', 'end_date', 'reason', 'created_by', 'created_at']
    list_filter = ['property', 'created_at']
    search_fields = ['property__name', 'reason']
    readonly_fields = ['created_by', 'created_at']
    
    fieldsets = (
        ('Blocked Date Information', {
            'fields': ('property', 'start_date', 'end_date', 'reason')
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at')
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
