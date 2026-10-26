import secrets
import string
from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone

User = get_user_model()


def generate_promo_code(prefix="KIF"):
    """
    Generate a cryptographically secure random promo code.
    Format: KIF-XXXXXXXX  (8 uppercase alphanumeric chars)
    Or XXXXXXXX if prefix is empty.
    """
    alphabet = string.ascii_uppercase + string.digits
    random_part = ''.join(secrets.choice(alphabet) for _ in range(8))
    return f"{prefix}-{random_part}" if prefix else random_part


class PromoCode(models.Model):
    DISCOUNT_TYPE_CHOICES = [
        ('full', 'Full (100% Free)'),
        ('percentage', 'Percentage Discount'),
    ]

    # Core fields
    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Unique promo code (e.g. JOHN-FREE or KIF-A3NQ7RWZ)"
    )
    discount_type = models.CharField(
        max_length=20,
        choices=DISCOUNT_TYPE_CHOICES,
        default='percentage',
        help_text="'full' = 100% free. 'percentage' = percentage off."
    )
    discount_value = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(99)],
        help_text="Percentage off (1–99). Only used when discount_type is 'percentage'."
    )

    # Control fields
    is_active = models.BooleanField(default=True)
    max_uses = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum number of times this code can be used. Leave blank for unlimited."
    )
    times_used = models.PositiveIntegerField(default=0, editable=False)

    # Validity window
    valid_from = models.DateField(
        null=True,
        blank=True,
        help_text="Code is valid from this date (inclusive). Leave blank to start immediately."
    )
    valid_until = models.DateField(
        null=True,
        blank=True,
        help_text="Code expires after this date (inclusive). Leave blank for no expiry."
    )

    # Metadata
    description = models.TextField(
        blank=True,
        help_text="Admin notes (e.g. 'For John — owner\\'s friend visiting Nov 2026')"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_promo_codes'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Promo Code'
        verbose_name_plural = 'Promo Codes'

    def __str__(self):
        if self.discount_type == 'full':
            label = '100% Free'
        else:
            label = f'{self.discount_value}% off'
        return f"{self.code} ({label})"

    def clean(self):
        """Model-level validation."""
        if self.discount_type == 'percentage' and not self.discount_value:
            raise ValidationError({
                'discount_value': 'Discount value is required when discount type is percentage.'
            })
        if self.discount_type == 'full' and self.discount_value:
            raise ValidationError({
                'discount_value': 'Discount value should be empty for full (100%) discount type.'
            })
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            raise ValidationError({
                'valid_until': 'valid_until must be after valid_from.'
            })

    def save(self, *args, **kwargs):
        # Always store code in uppercase
        self.code = self.code.upper().strip()
        # Clear discount_value for full type
        if self.discount_type == 'full':
            self.discount_value = None
        self.full_clean()
        super().save(*args, **kwargs)

    # ── Validation helpers ──────────────────────────────────────────────────

    @property
    def is_expired(self):
        today = timezone.now().date()
        if self.valid_until and today > self.valid_until:
            return True
        if self.valid_from and today < self.valid_from:
            return True
        return False

    @property
    def is_exhausted(self):
        if self.max_uses is None:
            return False
        return self.times_used >= self.max_uses

    @property
    def is_valid(self):
        return self.is_active and not self.is_expired and not self.is_exhausted

    def calculate_discount(self, original_amount):
        """
        Returns (discount_amount, final_amount) as Decimals.
        """
        from decimal import Decimal
        original = Decimal(str(original_amount))
        if self.discount_type == 'full':
            return original, Decimal('0.00')
        pct = Decimal(str(self.discount_value)) / Decimal('100')
        discount = (original * pct).quantize(Decimal('0.01'))
        final = original - discount
        return discount, final


class PromoUsage(models.Model):
    """
    Audit trail: records exactly which booking used which promo code and when.
    """
    promo_code = models.ForeignKey(
        PromoCode,
        on_delete=models.PROTECT,
        related_name='usages'
    )
    booking = models.OneToOneField(
        'booking.Booking',
        on_delete=models.CASCADE,
        related_name='promo_usage'
    )
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Promo Usage'
        verbose_name_plural = 'Promo Usages'

    def __str__(self):
        return f"{self.promo_code.code} → {self.booking.booking_reference}"
