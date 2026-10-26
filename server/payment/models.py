from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from decimal import Decimal
from booking.models import Booking

User = get_user_model()


class Payment(models.Model):
    """
    Manual payment ledger — the owner records payment receipts here
    after the client transfers money (bank, M-Pesa, etc.).
    This is NOT an automated payment gateway.
    """
    PAYMENT_METHOD_CHOICES = [
        ('bank_transfer', 'Bank Transfer'),
        ('mpesa', 'M-Pesa'),
        ('cash', 'Cash'),
        ('other', 'Other'),
    ]

    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('partial', 'Partially Paid'),
        ('completed', 'Completed'),
        ('refunded', 'Refunded'),
    ]

    # Relationships
    booking = models.OneToOneField(
        Booking, on_delete=models.CASCADE, related_name='payment'
    )
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, related_name='payments',
        null=True, blank=True,
        help_text="User account if booking was made by authenticated user"
    )

    # Core payment details
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES,
        help_text="How the client paid"
    )
    amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Total amount received"
    )
    currency = models.CharField(max_length=3, default='EUR')

    # Deposit / split-payment tracking
    prepayment_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Initial deposit received (e.g. 50%)"
    )
    remaining_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Balance still owed after deposit"
    )

    # Payment proof / references
    transaction_id = models.CharField(
        max_length=100, unique=True, blank=True, null=True,
        help_text="Auto-generated internal reference (TXN-XXXXXXXX)"
    )
    bank_transfer_reference = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="IBAN / bank reference number provided by the client"
    )
    mpesa_receipt_number = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="M-Pesa confirmation code (e.g. QHX7234ABC)"
    )
    mpesa_phone_number = models.CharField(
        max_length=15, blank=True, null=True,
        help_text="Phone number that sent the M-Pesa payment"
    )

    # Status
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending'
    )
    notes = models.TextField(
        blank=True, null=True,
        help_text="Any extra notes about this payment (e.g. refund reason, special arrangement)"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(
        blank=True, null=True,
        help_text="When the full payment was confirmed"
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment for {self.booking.booking_reference} — {self.payment_status}"

    def save(self, *args, **kwargs):
        # Auto-generate an internal transaction ID
        if not self.transaction_id:
            import uuid
            self.transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"
        super().save(*args, **kwargs)