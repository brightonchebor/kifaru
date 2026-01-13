from django.contrib import admin
from .models import Booking

# Register your models here.
@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['booking_reference', 'user', 'property', 'check_in', 'check_out', 'total_amount', 'status', 'created_at']
    list_filter = ['status', 'created_at', 'check_in']
    search_fields = ['booking_reference', 'user__email', 'property__name', 'full_name', 'email']
    readonly_fields = ['booking_reference', 'total_days', 'total_amount', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Booking Information', {
            'fields': ('booking_reference', 'user', 'property', 'status')
        }),
        ('Personal Details', {
            'fields': ('full_name', 'email', 'phone')
        }),
        ('Booking Details', {
            'fields': ('check_in', 'check_out', 'guests', 'total_days', 'total_amount', 'notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )