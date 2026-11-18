from django.core.exceptions import PermissionDenied

from . import events, second_factor


class AdminSecondFactorMiddleware:
    """Every admin page (Django admin, user moderation, listing moderation) needs the email code (SEC-14)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if second_factor.needs_second_factor(request):
            return second_factor.redirect_to_verify(request)
        return self.get_response(request)


class SecurityEventMiddleware:
    """Record server-side authorisation failures (SEC-31)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if isinstance(exception, PermissionDenied):
            events.record(events.Kind.AUTHZ_DENIED, request, detail="permission denied")
        return None
