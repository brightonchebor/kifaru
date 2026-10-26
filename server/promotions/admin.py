from django.contrib import admin
from .models import PromoCode, PromoUsage


class PromoUsageInline(admin.TabularInline):
    model = PromoUsage
    extra = 0
    readonly_fields = ['booking', 'used_at']
    can_delete = False


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = [
        'code', 'discount_type', 'discount_value', 'is_active',
        'times_used', 'max_uses', 'valid_until', 'created_by', 'created_at'
    ]
    list_filter = ['discount_type', 'is_active', 'created_at']
    search_fields = ['code', 'description']
    readonly_fields = ['times_used', 'created_at', 'updated_at']
    inlines = [PromoUsageInline]

    fieldsets = (
        ('Code', {
            'fields': ('code', 'discount_type', 'discount_value', 'is_active')
        }),
        ('Usage Limits', {
            'fields': ('max_uses', 'times_used', 'valid_from', 'valid_until')
        }),
        ('Notes', {
            'fields': ('description', 'created_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(PromoUsage)
class PromoUsageAdmin(admin.ModelAdmin):
    list_display = ['promo_code', 'booking', 'used_at']
    list_filter = ['promo_code', 'used_at']
    readonly_fields = ['promo_code', 'booking', 'used_at']
