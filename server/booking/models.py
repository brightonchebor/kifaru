from django.db import models
from django.contrib.auth import get_user_model
from properties.models import Property
from decimal import Decimal

User = get_user_model()


class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]
    
    ACCOMMODATION_TYPE_CHOICES = [
        ('master_bedroom', 'Master Bedroom'),
        ('single_bedroom', 'Single Bedroom'),
        ('full_apartment', 'Full Apartment'),
    ]
    
    GUEST_TYPE_CHOICES = [
        ('international', 'International'),
        ('local', 'Local'),
    ]
    
    # Booking reference (e.g., #BK-2025-1234)
    booking_reference = models.CharField(max_length=50, unique=True, blank=True)
    
    # Relationships
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='bookings')
    
    # Personal details
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    
    # Booking details
    accommodation_type = models.CharField(max_length=20, choices=ACCOMMODATION_TYPE_CHOICES, default='full_apartment')
    guest_type = models.CharField(max_length=20, choices=GUEST_TYPE_CHOICES, default='international')
    check_in = models.DateField()
    check_out = models.DateField()
    guests = models.PositiveIntegerField(default=1)
    number_of_adults = models.PositiveIntegerField(default=1)
    number_of_children = models.PositiveIntegerField(default=0)
    total_days = models.PositiveIntegerField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Meal inclusions
    includes_breakfast = models.BooleanField(default=False)
    includes_fullboard = models.BooleanField(default=False)
    
    # Special options
    dog_included = models.BooleanField(default=False, help_text="Small dog (up to 15kg) - only for Ocean Kifaru North-Sea")
    jacuzzi_reservation = models.BooleanField(default=False, help_text="Additional jacuzzi reservation fee")
    
    # Status and timestamps
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Special requests
    special_requests = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.booking_reference} - {self.user.email}"
    
    def save(self, *args, **kwargs):
        # Generate booking reference if not exists
        if not self.booking_reference:
            # Format: #BK-YEAR-ID
            last_booking = Booking.objects.order_by('-id').first()
            next_id = (last_booking.id + 1) if last_booking else 1
            from datetime import datetime
            year = datetime.now().year
            self.booking_reference = f"#BK-{year}-{next_id:04d}"
        
        # Calculate total days if not provided
        if not self.total_days and self.check_in and self.check_out:
            delta = self.check_out - self.check_in
            self.total_days = delta.days
            
        # Calculate total amount
        if self.property and self.total_days:
            self.total_amount = Decimal(str(self.property.price)) * Decimal(str(self.total_days))
            
        super().save(*args, **kwargs)


