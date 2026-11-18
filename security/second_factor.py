"""Shared state for the admin second authentication step (SEC-14).

An administrator proves possession of their account email with a one-time
code (see ``catalog.moderation.verify``); the session then stays verified for
30 minutes. Every admin surface checks the same flag.
"""

from django.utils import timezone

SESSION_KEY = "moderation_verified_until"
# Django's own admin is guarded by AdminSecondFactorMiddleware. The app's moderation
# views (listings and user accounts) check permissions first and then call
# ``require_verified`` themselves, so an unauthorised user still gets a 403.
PROTECTED_PREFIXES = ("/admin/",)
EXEMPT_PATHS = ("/admin/logout/",)


def is_verified(request):
    return request.session.get(SESSION_KEY, 0) > timezone.now().timestamp()


def needs_second_factor(request):
    path = request.path
    if not path.startswith(PROTECTED_PREFIXES) or path.startswith(EXEMPT_PATHS):
        return False
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and user.is_staff and not is_verified(request))


def redirect_to_verify(request):
    from urllib.parse import urlencode

    from django.shortcuts import redirect
    from django.urls import reverse

    return redirect(f"{reverse('moderation_verify')}?{urlencode({'next': request.get_full_path()})}")
