from django.db import models
from cloudinary.models import CloudinaryField
from properties.models import Property


class NewsletterSubscriber(models.Model):
    """Newsletter subscription management"""
    LANGUAGE_CHOICES = [
        ('english', 'English'),
        ('french', 'French'),
        ('dutch', 'Dutch'),
        ('swahili', 'Swahili'),
    ]
    
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=200, blank=True)
    preferred_language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, default='english')
    interests = models.JSONField(default=list, blank=True, help_text="List of interests")
    subscribed_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-subscribed_at']
    
    def __str__(self):
        return self.email
