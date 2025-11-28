from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Property(models.Model):
    STATUS_CHOICES = [
        ('free', 'Free'),
        ('booked', 'Booked'),
        ('maintenance', 'Maintenance'),
    ]
    
    name = models.CharField(max_length=200)
    location = models.CharField(max_length=200)
    country = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='free')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField()
    long_description = models.TextField()
    latitude = models.FloatField()
    longitude = models.FloatField()
    link = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name


class Amenity(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='amenities')
    icon = models.CharField(max_length=50)
    label = models.CharField(max_length=100)
    
    class Meta:
        verbose_name_plural = 'Amenities'


class Highlight(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='highlights')
    text = models.CharField(max_length=100)


class PropertyImage(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='images')
    image_url = models.URLField(max_length=500)
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order']


class Review(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
