from django.contrib import admin
from .models import NewsletterSubscriber

@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ['email', 'name', 'preferred_language', 'is_active', 'subscribed_at']
    list_filter = ['is_active', 'preferred_language', 'subscribed_at']
    search_fields = ['email', 'name']
    date_hierarchy = 'subscribed_at'
    readonly_fields = ['subscribed_at']
