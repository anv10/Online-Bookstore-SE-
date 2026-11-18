from django.shortcuts import render

from . import events


def csrf_failure(request, reason=""):
    """A request without a valid CSRF token is refused (SEC-28) and logged (SEC-31)."""
    events.record(events.Kind.CSRF_FAILED, request, detail="csrf token missing or invalid")
    return render(request, "403.html", status=403)
