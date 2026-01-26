from django.db import models
from django.contrib.auth import get_user_model
from cloudinary.models import CloudinaryField
from django.utils.text import slugify
from decimal import Decimal

User = get_user_model()


class Property(models.Model):
    CATEGORY_CHOICES = [
        ('retreat', 'Retreat'),
        ('coworking', 'Coworking'),
        ('beachfront', 'Beachfront'),
        ('urban', 'Urban'),
    ]
    
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=250, unique=True, blank=True)
    location = models.CharField(max_length=200)
    country = models.CharField(max_length=100)
    property_category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='retreat')
    
    # Pricing - base price, complex pricing in PropertyPricing model
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Base price per night (EUR)")
    
    # Property details
    description = models.TextField()
    bedrooms = models.PositiveIntegerField(default=1)
    bathrooms = models.PositiveIntegerField(default=1)
    square_meters = models.PositiveIntegerField(null=True, blank=True)
    terrace_size = models.PositiveIntegerField(null=True, blank=True, help_text="Terrace size in square meters")
    max_guests = models.PositiveIntegerField(null=True, blank=True)
    
    # Booking policies
    min_nights = models.PositiveIntegerField(default=1)
    check_in_time = models.TimeField(default='15:00:00', help_text="Check-in time (e.g., 15:00 for 3 PM)")
    check_out_time = models.TimeField(default='10:30:00', help_text="Check-out time (e.g., 10:30 for 10:30 AM)")
    prepayment_percentage = models.PositiveIntegerField(default=50, help_text="Prepayment percentage required")
    cancellation_days = models.PositiveIntegerField(default=30, help_text="Free cancellation within X days")
    
    # Media
    background_image = CloudinaryField("image", blank=True, null=True)
    
    # Additional
    wifi_password = models.CharField(max_length=100, blank=True, help_text="Universal WiFi password")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        if not self. slug:
            self.slug = slugify(self.name)
            # Ensure uniqueness
            original_slug = self.slug
            counter = 1
            while Property.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.name


class Amenity(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='amenities')
    image = CloudinaryField("image")
    label = models.CharField(max_length=100)
    
    class Meta:
        verbose_name_plural = 'Amenities'
    
    def __str__(self):
        return f"{self.property.name} - {self.label}"


class Highlight(models.Model):
    property = models.ForeignKey(Property, on_delete=models. CASCADE, related_name='highlights')
    text = models.CharField(max_length=100)


class PropertyImage(models.Model):
    property = models.ForeignKey(Property, on_delete=models. CASCADE, related_name='images')
    image = CloudinaryField("image")
    order = models. PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.property.name} - {self.order}"


class Review(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.email} - {self.property.name} ({self.rating}/5)"


class PropertyPricing(models.Model):
    """Complex pricing structure for different accommodation types and guest types"""
    ACCOMMODATION_TYPE_CHOICES = [
        ('master_bedroom', 'Master Bedroom'),
        ('full_apartment', 'Full Apartment'),
    ]
    
    GUEST_TYPE_CHOICES = [
        ('international', 'International'),
        ('local', 'Local'),
    ]
    
    STAY_TYPE_CHOICES = [
        ('short_term', 'Short Term'),
        ('long_term', 'Long Term'),
        ('weekly', 'Weekly'),
    ]
    
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='pricing_options')
    accommodation_type = models.CharField(max_length=20, choices=ACCOMMODATION_TYPE_CHOICES)
    guest_type = models.CharField(max_length=20, choices=GUEST_TYPE_CHOICES, default='international')
    stay_type = models.CharField(max_length=20, choices=STAY_TYPE_CHOICES)
    number_of_guests = models.PositiveIntegerField(null=True, blank=True, help_text="Number of guests (if pricing varies by occupancy)")
    min_nights = models.PositiveIntegerField(default=1)
    max_nights = models.PositiveIntegerField(null=True, blank=True)
    price_per_night = models.DecimalField(max_digits=10, decimal_places=2, help_text="Price in EUR")
    weekly_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Price for full week (if applicable)")
    includes_breakfast = models.BooleanField(default=False)
    includes_fullboard = models.BooleanField(default=False)
    
    class Meta:
        verbose_name_plural = 'Property Pricing Options'
        ordering = ['property', 'accommodation_type', 'stay_type']
    
    def __str__(self):
        return f"{self.property.name} - {self.accommodation_type} ({self.stay_type})"


class PropertyFeature(models.Model):
    """Property-specific unique features"""
    FEATURE_TYPE_CHOICES = [
        ('outdoor', 'Outdoor'),
        ('indoor', 'Indoor'),
        ('service', 'Service'),
        ('unique', 'Unique'),
    ]
    
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='features')
    feature_type = models.CharField(max_length=20, choices=FEATURE_TYPE_CHOICES)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order', 'name']
    
    def __str__(self):
        return f"{self.property.name} - {self.name}"


class PropertyContact(models.Model):
    """On-site contact persons for each property"""
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='contacts')
    name = models.CharField(max_length=200)
    role = models.CharField(max_length=100, help_text="e.g., Friendly Concierge, Host, Butler")
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    whatsapp = models.CharField(max_length=20, blank=True)
    
    class Meta:
        verbose_name_plural = 'Property Contacts'
    
    def __str__(self):
        return f"{self.name} - {self.property.name}"


class PropertyNetwork(models.Model):
    """Links related properties in the Kifaru network"""
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='network_from')
    related_property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='network_to')
    travel_time_minutes = models.PositiveIntegerField(help_text="Travel time between properties in minutes")
    transport_available = models.BooleanField(default=False)
    description = models.TextField(blank=True, help_text="How properties are connected")
    
    class Meta:
        unique_together = ['property', 'related_property']
    
    def __str__(self):
        return f"{self.property.name} ↔ {self.related_property.name}"