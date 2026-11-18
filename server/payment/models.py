from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from decimal import Decimal
import uuid
from django.utils import timezone
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
        ('refund_pending', 'Refund review pending'),
        ('partially_refunded', 'Partially refunded'),
    ]

    # Relationships
    booking = models.OneToOneField(
        Booking, on_delete=models.PROTECT, related_name='payment'
    )
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, related_name='payments',
        null=True, blank=True,
        help_text="User account if booking was made by authenticated user"
    )
    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='recorded_payments',
    )
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='updated_payments',
    )
    refunded_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Core payment details
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES,
        help_text="How the client paid"
    )
    amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
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

    @property
    def net_received(self):
        return self.amount - self.refunded_amount

    @property
    def refundable_amount(self):
        return self.net_received if self.booking.status == 'cancelled' else Decimal('0.00')


class PaymentTransaction(models.Model):
    """An immutable receipt, actual refund, or imported unverified legacy entry."""
    KIND_CHOICES = [('receipt', 'Receipt'), ('refund', 'Refund'), ('legacy', 'Legacy review')]
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='transactions')
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    currency = models.CharField(max_length=3)
    payment_method = models.CharField(max_length=20, choices=Payment.PAYMENT_METHOD_CHOICES)
    reference = models.CharField(max_length=100, blank=True)
    reference_key = models.CharField(max_length=160, unique=True, null=True, blank=True, editable=False)
    idempotency_key = models.UUIDField(unique=True, null=True, blank=True)
    transaction_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='recorded_payment_transactions')
    occurred_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['created_at', 'id']

    def save(self, *args, **kwargs):
        if self.pk:
            from django.core.exceptions import ValidationError
            raise ValidationError('Payment transactions cannot be edited. Record a refund or a new receipt.')
        self.reference = self.reference.strip()
        if self.reference:
            self.reference_key = f'{self.kind}:{self.payment_method}:{self.reference.upper()}'
        super().save(*args, **kwargs)
