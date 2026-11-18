"""Write security events to the protected table and to the ``bookstore.security`` logger (SEC-31).

Only identifiers go in: never passwords, OTPs, tokens, card data or message
bodies (SEC-18). ``detail`` is truncated and callers pass short, fixed text.
"""

import logging

from .models import SecurityEvent

logger = logging.getLogger("bookstore.security")

Kind = SecurityEvent.Kind


def client_ip(request):
    if request is None:
        return None
    return request.META.get("REMOTE_ADDR") or None


def record(kind, request=None, user=None, detail=""):
    if user is None and request is not None:
        user = getattr(request, "user", None)
    user_id = getattr(user, "pk", None) if user is not None and getattr(user, "is_authenticated", False) else None
    if user_id is None and isinstance(user, int):
        user_id = user
    event = SecurityEvent.objects.create(
        kind=kind,
        user_id_ref=user_id,
        ip_address=client_ip(request),
        path=(request.path[:255] if request is not None else ""),
        detail=(detail or "")[:500],
    )
    logger.info(
        "security_event kind=%s user=%s ip=%s path=%s detail=%s",
        kind, user_id, event.ip_address, event.path, event.detail,
    )
    return event
