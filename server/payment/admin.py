from django.contrib import admin
from django.utils import timezone
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        'transaction_id', 'booking', 'user', 'amount', 'currency',
        'payment_method', 'payment_status', 'created_at'
    ]
    list_filter = ['payment_status', 'payment_method', 'currency', 'created_at']
    search_fields = [
        'transaction_id', 'booking__booking_reference',
        'user__email', 'mpesa_receipt_number', 'bank_transfer_reference'
    ]
    readonly_fields = ['transaction_id', 'created_at', 'updated_at']

    fieldsets = (
        ('Payment Information', {
            'fields': (
                'transaction_id', 'booking', 'user',
                'amount', 'currency', 'payment_status', 'completed_at'
            )
        }),
        ('Payment Method & Proof', {
            'fields': (
                'payment_method',
                'bank_transfer_reference',
                'mpesa_receipt_number', 'mpesa_phone_number',
            )
        }),
        ('Deposit / Split Payment', {
            'fields': ('prepayment_amount', 'remaining_amount'),
            'classes': ('collapse',),
            'description': 'Fill these in if the client is paying in instalments.'
        }),
        ('Notes', {
            'fields': ('notes',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    actions = ['mark_completed', 'mark_refunded']

    def mark_completed(self, request, queryset):
        queryset.update(payment_status='completed', completed_at=timezone.now())
        self.message_user(request, f"{queryset.count()} payment(s) marked as completed.")
    mark_completed.short_description = "Mark selected payments as Completed"

    def mark_refunded(self, request, queryset):
        queryset.update(payment_status='refunded')
        self.message_user(request, f"{queryset.count()} payment(s) marked as refunded.")
    mark_refunded.short_description = "Mark selected payments as Refunded"