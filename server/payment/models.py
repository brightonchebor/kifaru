from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from decimal import Decimal
from booking.models import Booking

User = get_user_model()

class Payment(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('card', 'Card'),
        ('bank_transfer', 'Bank Transfer'),
        ('mpesa', 'M-Pesa'),
        ('paypal', 'PayPal'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    # Relationships
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='payment')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments', null=True, blank=True, help_text="User account if payment was made by authenticated user")
    
    # Payment details
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    currency = models.CharField(max_length=3, default='EUR')
    
    # Prepayment handling
    prepayment_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Initial prepayment (usually 50%)")
    remaining_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Remaining balance")
    
    # Card details (encrypted in production)
    card_number_last4 = models.CharField(max_length=4, blank=True, null=True)
    card_type = models.CharField(max_length=20, blank=True, null=True)
    
    # Transaction details
    transaction_id = models.CharField(max_length=100, unique=True, blank=True, null=True)
    bank_transfer_reference = models.CharField(max_length=100, blank=True, null=True, help_text="IBAN transfer reference")
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    
    # M-Pesa specific fields
    mpesa_receipt_number = models.CharField(max_length=100, blank=True, null=True)
    mpesa_phone_number = models.CharField(max_length=15, blank=True, null=True)
    
    # Paystack specific fields
    paystack_reference = models.CharField(max_length=100, blank=True, null=True, unique=True, help_text="Paystack transaction reference")
    paystack_access_code = models.CharField(max_length=100, blank=True, null=True, help_text="Paystack access code")
    authorization_url = models.URLField(blank=True, null=True, help_text="Paystack payment URL")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    
    # Failure reason
    failure_reason = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"Payment for {self.booking.booking_reference} - {self.payment_status}"
    
    def save(self, *args, **kwargs):
        # Generate transaction ID if not exists
        if not self.transaction_id:
            import uuid
            self.transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"
        super().save(*args, **kwargs)