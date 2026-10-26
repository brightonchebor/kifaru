from rest_framework import serializers
from django.utils import timezone
from .models import PromoCode, PromoUsage
from .models import generate_promo_code


# ── Admin serializers ────────────────────────────────────────────────────────

class PromoCodeSerializer(serializers.ModelSerializer):
    """Full serializer for admin CRUD operations."""
    created_by_email = serializers.SerializerMethodField(read_only=True)
    is_valid = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    is_exhausted = serializers.BooleanField(read_only=True)
    uses_remaining = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = PromoCode
        fields = [
            'id', 'code', 'discount_type', 'discount_value',
            'is_active', 'max_uses', 'times_used', 'uses_remaining',
            'valid_from', 'valid_until',
            'description', 'created_by_email',
            'is_valid', 'is_expired', 'is_exhausted',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['times_used', 'created_at', 'updated_at']

    def get_created_by_email(self, obj):
        return obj.created_by.email if obj.created_by else None

    def get_uses_remaining(self, obj):
        if obj.max_uses is None:
            return None  # Unlimited
        return max(0, obj.max_uses - obj.times_used)

    def validate(self, attrs):
        discount_type = attrs.get('discount_type', getattr(self.instance, 'discount_type', None))
        discount_value = attrs.get('discount_value', getattr(self.instance, 'discount_value', None))

        if discount_type == 'percentage' and not discount_value:
            raise serializers.ValidationError({
                'discount_value': 'discount_value is required when discount_type is percentage.'
            })
        if discount_type == 'full' and discount_value:
            raise serializers.ValidationError({
                'discount_value': 'discount_value must be empty for full (100%) discount.'
            })

        valid_from = attrs.get('valid_from')
        valid_until = attrs.get('valid_until')
        if valid_from and valid_until and valid_from > valid_until:
            raise serializers.ValidationError({
                'valid_until': 'valid_until must be after valid_from.'
            })
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        return super().create(validated_data)


class PromoCodeGenerateResponseSerializer(serializers.Serializer):
    """
    Response serializer returning only the unique promo code string.
    """
    code = serializers.CharField(
        help_text="Unique auto-generated promo code string"
    )


# ── Public serializer ────────────────────────────────────────────────────────

class PromoValidateSerializer(serializers.Serializer):
    """
    Public endpoint: client enters a code to preview their discount.
    Returns discount info without marking the code as used.
    """
    code = serializers.CharField(max_length=50)
    booking_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        allow_null=True,
        help_text="Optional: pass the booking total to get back exact discount amounts"
    )

    def validate_code(self, value):
        return value.upper().strip()


class PromoUsageSerializer(serializers.ModelSerializer):
    """Shows usage history for a promo code."""
    booking_reference = serializers.CharField(source='booking.booking_reference', read_only=True)
    guest_name = serializers.CharField(source='booking.full_name', read_only=True)
    property_name = serializers.CharField(source='booking.property.name', read_only=True)

    class Meta:
        model = PromoUsage
        fields = ['id', 'booking_reference', 'guest_name', 'property_name', 'used_at']
