"""Temporary lockout after repeated failed sign-ins (FR-1).

Failures are counted per typed identifier (lower-cased email or phone), whether
or not an account exists for it, so the lock message never reveals which
identifiers are registered. A locked identifier is not authenticated at all,
so a correct password gives no hint while the lock lasts. A successful sign-in
clears the count.
"""

import math
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import LoginThrottle


def key_for(identifier):
    return (identifier or "").strip().lower()[:254]


def lock_message(minutes):
    unit = "minute" if minutes == 1 else "minutes"
    return f"Too many failed sign-in attempts. Please try again in {minutes} {unit}."


def minutes_locked(key):
    """Whole minutes left on the lock, or 0 when the identifier may try to sign in."""
    row = LoginThrottle.objects.filter(identifier=key).first()
    if row is None or row.locked_until is None or row.locked_until <= timezone.now():
        return 0
    return max(1, math.ceil((row.locked_until - timezone.now()).total_seconds() / 60))


def record_failure(key):
    """Count one failed sign-in. Returns the lock length in minutes if this failure locked it, else 0."""
    with transaction.atomic():
        row, _ = LoginThrottle.objects.select_for_update().get_or_create(identifier=key)
        now = timezone.now()
        if row.locked_until is not None and row.locked_until <= now:
            row.failures, row.locked_until = 0, None  # an expired lock starts a fresh count
        row.failures += 1
        minutes = 0
        if row.failures >= settings.LOGIN_MAX_FAILURES:
            minutes = settings.LOGIN_LOCKOUT_MINUTES
            row.locked_until = now + timedelta(minutes=minutes)
        row.save()
    return minutes


def reset(key):
    LoginThrottle.objects.filter(identifier=key).delete()
