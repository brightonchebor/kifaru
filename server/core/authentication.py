from rest_framework_simplejwt.authentication import JWTAuthentication, AUTH_HEADER_TYPE_BYTES
from rest_framework.exceptions import AuthenticationFailed
from django.utils.translation import gettext_lazy as _
from typing import Optional


class FlexibleJWTAuthentication(JWTAuthentication):
    """
    Custom JWT Authentication that accepts both:
    1. Standard 'Bearer <token>' format
    2. Raw '<token>' format (e.g., when a user pastes the raw JWT token into Swagger UI)
    """
    def get_raw_token(self, header: bytes) -> Optional[bytes]:
        parts = header.split()

        if len(parts) == 0:
            return None

        # Case 1: Standard 'Bearer <token>'
        if parts[0] in AUTH_HEADER_TYPE_BYTES:
            if len(parts) != 2:
                raise AuthenticationFailed(
                    _("Authorization header must contain two space-delimited values"),
                    code="bad_authorization_header",
                )
            return parts[1]

        # Case 2: Raw JWT token (starts with 'ey...' header prefix)
        if len(parts) == 1 and parts[0].startswith(b"ey"):
            return parts[0]

        return None
