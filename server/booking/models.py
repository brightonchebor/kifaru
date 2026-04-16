from django.db import models
from django.contrib.auth import get_user_model
from properties.models import Property, PropertyPricing
from decimal import Decimal
from django.core.exceptions import ValidationError
import phonenumbers
from phonenumbers import geocoder

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
    
    # Booking reference (e.g., #BK-2025-1234)
    booking_reference = models.CharField(max_length=50, unique=True, blank=True)
    
    # Relationships
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings', null=True, blank=True, help_text="User account if booking was made by authenticated user")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='bookings')
    selected_pricing = models.ForeignKey(PropertyPricing, on_delete=models.PROTECT, null=True, blank=True, help_text="Selected pricing option")
    
    # Personal details (required for all bookings, whether guest or authenticated)
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    id_passport_number = models.CharField(max_length=50, blank=True, help_text="ID or Passport number for verification")
    
    # Booking details
    accommodation_type = models.CharField(max_length=20, choices=ACCOMMODATION_TYPE_CHOICES, default='full_apartment')
    guest_type = models.CharField(max_length=20, choices=GUEST_TYPE_CHOICES, default='international')
    stay_type = models.CharField(max_length=20, choices=STAY_TYPE_CHOICES, default='short_term')
    check_in = models.DateField()
    check_out = models.DateField()
    number_of_guests = models.PositiveIntegerField(default=2, help_text="Total number of guests")
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
        user_email = self.user.email if self.user else "No User"
        return f"{self.booking_reference} - {user_email}"
    
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
        
        # Determine stay type based on total_days if not set
        if not self.stay_type and self.total_days and self.property:
            # Check if property has weekly pricing and if nights is a multiple of 7
            has_weekly_pricing = PropertyPricing.objects.filter(
                property=self.property,
                accommodation_type=self.accommodation_type,
                stay_type='weekly'
            ).exists()
            
            if self.total_days % 7 == 0 and has_weekly_pricing:
                # Multiples of 7 (7, 14, 21, 28...) use weekly pricing if available
                self.stay_type = 'weekly'
            elif self.total_days >= 10:
                self.stay_type = 'long_term'
            elif self.total_days < 7:
                self.stay_type = 'short_term'
            else:
                # 8 or 9 nights - check what's available
                self.stay_type = 'short_term'
        elif not self.stay_type and self.total_days:
            # Fallback if no property context
            if self.total_days == 7:
                self.stay_type = 'weekly'
            elif self.total_days >= 10:
                self.stay_type = 'long_term'
            else:
                self.stay_type = 'short_term'
        
        # Auto-determine guest_type from user's country_of_residence and property location
        if not self.guest_type and self.user and self.user.country_of_residence and self.property:
            # User is local if their country matches the property's country
            user_country = self.user.country_of_residence.lower()
            property_country = self.property.country.lower()
            
            if user_country == property_country:
                self.guest_type = 'local'
            else:
                self.guest_type = 'international'
        elif not self.guest_type and self.phone and self.property:
            # For guest bookings, determine from phone number
            try:
                parsed = phonenumbers.parse(self.phone, None)
                if not phonenumbers.is_valid_number(parsed):
                    raise ValidationError({
                        'phone': 'Please provide a valid phone number with country code (e.g., +254712345678).'
                    })
                
                phone_country = geocoder.description_for_number(parsed, "en")
                if phone_country:
                    property_country = self.property.country.lower()
                    if phone_country.lower() == property_country:
                        self.guest_type = 'local'
                    else:
                        self.guest_type = 'international'
                else:
                    self.guest_type = 'international'
            except phonenumbers.NumberParseException:
                raise ValidationError({
                    'phone': 'Invalid phone number format. Please include country code (e.g., +254712345678).'
                })
        elif not self.guest_type:
            # Fallback default
            self.guest_type = 'international'
        
        # Find matching PropertyPricing if not already selected
        if not self.selected_pricing and self.property:
            # Try specific guest_type first
            pricing = PropertyPricing.objects.filter(
                property=self.property,
                accommodation_type=self.accommodation_type,
                guest_type=self.guest_type,
                stay_type=self.stay_type,
                min_nights__lte=self.total_days
            ).filter(
                models.Q(max_nights__isnull=True) | models.Q(max_nights__gte=self.total_days)
            )
            
            # If not found, try 'all'
            if not pricing.exists():
                pricing = PropertyPricing.objects.filter(
                    property=self.property,
                    accommodation_type=self.accommodation_type,
                    guest_type='all',
                    stay_type=self.stay_type,
                    min_nights__lte=self.total_days
                ).filter(
                    models.Q(max_nights__isnull=True) | models.Q(max_nights__gte=self.total_days)
                )
            
            # Filter by number_of_guests - find pricing where capacity >= requested guests
            pricing_with_capacity = pricing.filter(
                models.Q(number_of_guests__gte=self.number_of_guests) | 
                models.Q(number_of_guests__isnull=True)
            ).order_by('number_of_guests').first()  # Prefer smallest capacity that fits
            
            if pricing_with_capacity:
                self.selected_pricing = pricing_with_capacity
            else:
                # Use any available pricing as fallback
                self.selected_pricing = pricing.first()
        
        # Calculate total amount based on selected pricing
        if self.selected_pricing and self.total_days:
            # Use weekly_price for multiples of 7 if weekly price exists
            if self.selected_pricing.weekly_price and self.total_days % 7 == 0:
                num_weeks = self.total_days // 7
                self.total_amount = self.selected_pricing.weekly_price * num_weeks
            else:
                # Use per-night price
                self.total_amount = self.selected_pricing.price_per_night * Decimal(str(self.total_days))
            
            # Update meal inclusions from pricing
            self.includes_breakfast = self.selected_pricing.includes_breakfast
            self.includes_fullboard = self.selected_pricing.includes_fullboard
        elif self.property and self.total_days:
            # Fallback to base property price if no pricing found
            self.total_amount = Decimal(str(self.property.price)) * Decimal(str(self.total_days))
            
        super().save(*args, **kwargs)



class BlockedDate(models.Model):
    """
    Model to manually block dates for property maintenance, renovations, or personal use.
    Blocked dates will prevent new bookings from being created.
    """
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='blocked_dates')
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=200, help_text="Reason for blocking (e.g., Maintenance, Renovation)")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['start_date']
        verbose_name = 'Blocked Date'
        verbose_name_plural = 'Blocked Dates'
    
    def __str__(self):
        return f"{self.property.name} - {self.start_date} to {self.end_date} ({self.reason})"
    
    def clean(self):
        """Validate that end_date is after start_date"""
        if self.start_date and self.end_date:
            if self.end_date <= self.start_date:
                raise ValidationError("End date must be after start date.")
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
