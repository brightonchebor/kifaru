from django.conf import settings


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.csp = getattr(settings, 'CONTENT_SECURITY_POLICY', '')
        self.permissions_policy = getattr(settings, 'PERMISSIONS_POLICY', '')

    def __call__(self, request):
        response = self.get_response(request)

        if self.csp:
            response['Content-Security-Policy'] = self.csp
        if self.permissions_policy:
            response['Permissions-Policy'] = self.permissions_policy

        return response
