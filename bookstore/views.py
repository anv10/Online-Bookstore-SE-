from django.conf import settings
from django.shortcuts import render


def support(request):
    """A support channel reachable from every page (NFR-12)."""
    return render(request, "support.html", {"support_email": settings.SUPPORT_EMAIL})
