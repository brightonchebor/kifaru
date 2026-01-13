from django.contrib import admin
from .models import Payment

# Register your models here.
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['transaction_id', 'booking', 'user', 'amount', 'payment_method', 'payment_status', 'created_at']
    list_filter = ['payment_status', 'payment_method', 'created_at']
    search_fields = ['transaction_id', 'booking__booking_reference', 'user__email']
    readonly_fields = ['transaction_id', 'created_at', 'updated_at', 'completed_at']
    
    fieldsets = (
        ('Payment Information', {
            'fields': ('transaction_id', 'booking', 'user', 'amount', 'currency', 'payment_status')
        }),
        ('Payment Method', {
            'fields': ('payment_method', 'card_number_last4', 'card_type', 'mpesa_receipt_number', 'mpesa_phone_number')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'completed_at')
        }),
        ('Failure Information', {
            'fields': ('failure_reason',)
        }),
    )