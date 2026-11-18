from django.contrib import admin
from .models import Payment, PaymentTransaction


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['transaction_id', 'booking', 'user', 'amount', 'currency',
                    'refunded_amount', 'remaining_amount', 'payment_status', 'recorded_by']
    list_filter = ['payment_status', 'payment_method', 'currency']
    search_fields = ['transaction_id', 'booking__booking_reference', 'booking__full_name', 'booking__email']
    readonly_fields = [field.name for field in Payment._meta.fields]
    actions = None

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        # Record receipts/refunds through the dashboard APIs so the same validation applies.
        return False


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction_id', 'payment', 'kind', 'amount', 'currency',
                    'payment_method', 'reference', 'recorded_by', 'occurred_at']
    list_filter = ['kind', 'currency', 'payment_method']
    search_fields = ['reference', 'payment__booking__booking_reference', 'payment__booking__email']
    readonly_fields = [field.name for field in PaymentTransaction._meta.fields]
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
