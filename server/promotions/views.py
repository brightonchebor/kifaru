from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from .models import PromoCode, PromoUsage, generate_promo_code
from .serializers import (
    PromoCodeSerializer,
    PromoCodeGenerateResponseSerializer,
    PromoValidateSerializer,
    PromoUsageSerializer,
)


# ── Permission helper ────────────────────────────────────────────────────────

def require_admin(user):
    if not user.is_authenticated or getattr(user, 'role', None) != 'admin':
        raise PermissionDenied("Only admins can perform this action.")


# ── Admin: List + Manual Create ───────────────────────────────────────────────

class PromoCodeListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/promos/  — List all promo codes (admin only)
    POST /api/promos/  — Create a promo code with a custom code string (admin only)

    POST body example (percentage):
    {
        "code": "SARAH50",
        "discount_type": "percentage",
        "discount_value": 50,
        "max_uses": 3,
        "valid_until": "2026-12-31",
        "description": "For Sarah and friends"
    }

    POST body example (full / free):
    {
        "code": "JOHN-FREE",
        "discount_type": "full",
        "description": "For John - owner's friend"
    }
    """
    serializer_class = PromoCodeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        require_admin(self.request.user)
        queryset = PromoCode.objects.all()

        # Optional filters
        discount_type = self.request.query_params.get('discount_type')
        is_active = self.request.query_params.get('is_active')

        if discount_type:
            queryset = queryset.filter(discount_type=discount_type)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        return queryset

    def create(self, request, *args, **kwargs):
        require_admin(request.user)
        return super().create(request, *args, **kwargs)


# ── Admin: Retrieve + Update + Delete ────────────────────────────────────────

class PromoCodeDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/promos/{id}/   — Retrieve a promo code (admin only)
    PATCH  /api/promos/{id}/   — Edit code (toggle active, extend expiry, etc.)
    DELETE /api/promos/{id}/   — Delete code

    Note: You cannot delete a code that has been used (PromoUsage records exist).
    Deactivate it instead with PATCH {is_active: false}.
    """
    serializer_class = PromoCodeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        require_admin(self.request.user)
        return PromoCode.objects.all()

    def destroy(self, request, *args, **kwargs):
        require_admin(request.user)
        promo = self.get_object()
        if promo.usages.exists():
            return Response(
                {
                    'error': 'Cannot delete a promo code that has been used.',
                    'suggestion': 'Deactivate it instead with PATCH {"is_active": false}',
                    'times_used': promo.times_used,
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        promo.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def update(self, request, *args, **kwargs):
        require_admin(request.user)
        return super().update(request, *args, **kwargs)


# ── Admin: Auto-Generate ──────────────────────────────────────────────────────

class PromoCodeGenerateView(APIView):
    """
    GET /api/promos/generate/  — Auto-generate a unique code string (admin only)

    Generates a unique, cryptographically secure promo code suggestion without
    creating or saving anything in the database. The frontend calls this to
    fill the "code" field when an admin is manually creating a promo code.

    Optional query parameter:
      ?prefix=XYZ (str): Prefix for the code (e.g. "KIF", "VIP", "none"). Default: "KIF"

    Response:
    {
        "code": "KIF-A3NQ7RWZ"
    }
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Auto-generate a unique promo code string without saving to database.",
        manual_parameters=[
            openapi.Parameter(
                'prefix',
                openapi.IN_QUERY,
                description="Optional code prefix (default: KIF, or 'none' for no prefix)",
                type=openapi.TYPE_STRING,
                default='KIF',
                required=False
            )
        ],
        responses={200: PromoCodeGenerateResponseSerializer}
    )
    def get(self, request):
        require_admin(request.user)

        raw_prefix = request.query_params.get('prefix')

        if raw_prefix is None:
            # Default prefix if not provided at all
            prefix = 'KIF'
        elif raw_prefix.strip().lower() in ('', 'none', 'false', 'null'):
            # Explicitly requested without any prefix (e.g. ?prefix=none)
            prefix = ''
        else:
            # Custom prefix provided (keep alphanumeric only)
            prefix = ''.join(c for c in raw_prefix.upper().strip() if c.isalnum()) or 'KIF'

        for _ in range(25):
            code = generate_promo_code(prefix=prefix)
            if not PromoCode.objects.filter(code=code).exists():
                return Response({'code': code}, status=status.HTTP_200_OK)

        import uuid
        code = f"{prefix}-{uuid.uuid4().hex[:8].upper()}" if prefix else uuid.uuid4().hex[:8].upper()
        return Response({'code': code}, status=status.HTTP_200_OK)


# ── Admin: Usage History ──────────────────────────────────────────────────────

class PromoCodeUsageView(generics.ListAPIView):
    """
    GET /api/promos/{id}/usage/  — See which bookings used this code (admin only)
    """
    serializer_class = PromoUsageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        require_admin(self.request.user)
        promo = get_object_or_404(PromoCode, pk=self.kwargs['pk'])
        return PromoUsage.objects.filter(promo_code=promo).select_related(
            'booking', 'booking__property'
        )


# ── Public: Validate ──────────────────────────────────────────────────────────

class PromoValidateView(APIView):
    """
    POST /api/promos/validate/  — Check if a promo code is valid (public endpoint)

    This is a PREVIEW only — it does NOT mark the code as used.
    The code is actually applied + marked used when the booking is created.

    POST body:
    {
        "code": "SARAH50",
        "booking_amount": 500.00   ← optional
    }

    Response (valid code):
    {
        "valid": true,
        "code": "SARAH50",
        "discount_type": "percentage",
        "discount_value": 50,
        "discount_amount": 250.00,   ← only if booking_amount was provided
        "final_amount": 250.00,      ← only if booking_amount was provided
        "message": "50% discount applied!"
    }

    Response (invalid code):
    {
        "valid": false,
        "code": "BADCODE",
        "error": "This promo code has expired."
    }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PromoValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code = serializer.validated_data['code']
        booking_amount = serializer.validated_data.get('booking_amount')

        try:
            promo = PromoCode.objects.get(code=code)
        except PromoCode.DoesNotExist:
            return Response({
                'valid': False,
                'code': code,
                'error': 'This promo code does not exist.',
            }, status=status.HTTP_404_NOT_FOUND)

        # Check validity
        if not promo.is_active:
            return Response({
                'valid': False,
                'code': code,
                'error': 'This promo code has been deactivated.',
            }, status=status.HTTP_400_BAD_REQUEST)

        if promo.is_expired:
            return Response({
                'valid': False,
                'code': code,
                'error': 'This promo code has expired.',
            }, status=status.HTTP_400_BAD_REQUEST)

        if promo.is_exhausted:
            return Response({
                'valid': False,
                'code': code,
                'error': 'This promo code has already been fully redeemed.',
            }, status=status.HTTP_400_BAD_REQUEST)

        # Build response
        response_data = {
            'valid': True,
            'code': promo.code,
            'discount_type': promo.discount_type,
            'discount_value': promo.discount_value,
        }

        if promo.discount_type == 'full':
            response_data['message'] = '🎉 This code gives you a 100% discount — completely free!'
            if booking_amount:
                response_data['discount_amount'] = str(booking_amount)
                response_data['final_amount'] = '0.00'
        else:
            response_data['message'] = f'{promo.discount_value}% discount applied!'
            if booking_amount:
                discount, final = promo.calculate_discount(booking_amount)
                response_data['discount_amount'] = str(discount)
                response_data['final_amount'] = str(final)

        return Response(response_data, status=status.HTTP_200_OK)
