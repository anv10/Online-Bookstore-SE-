"""Fixed-window request limits (SEC-6, SEC-24, SEC-30).

``hit(scope, key)`` counts one request and says whether it is still inside the
limit configured in ``settings.RATE_LIMITS[scope] = (max_requests, seconds)``.
"""

from datetime import datetime, timedelta, timezone as dt_timezone
from functools import wraps

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.shortcuts import render
from django.utils import timezone

from . import events
from .models import RateLimitBucket


def _limit(scope):
    return settings.RATE_LIMITS[scope]


def _window_start(seconds, now):
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - epoch % seconds, tz=dt_timezone.utc)


def _bucket(scope, key, seconds):
    return dict(scope=scope, key=str(key)[:128], window_start=_window_start(seconds, timezone.now()))


def count(scope, key):
    _, seconds = _limit(scope)
    row = RateLimitBucket.objects.filter(**_bucket(scope, key, seconds)).first()
    return row.count if row else 0


def is_limited(scope, key):
    """True when ``key`` has already used up the scope's allowance (does not count a request)."""
    limit, _ = _limit(scope)
    return count(scope, key) >= limit


def hit(scope, key):
    """Count one request. Returns True if it is allowed, False once the limit is exceeded."""
    limit, seconds = _limit(scope)
    where = _bucket(scope, key, seconds)
    with transaction.atomic():
        updated = RateLimitBucket.objects.filter(**where).update(count=F("count") + 1)
        if not updated:
            try:
                with transaction.atomic():
                    RateLimitBucket.objects.create(count=1, **where)
            except IntegrityError:
                RateLimitBucket.objects.filter(**where).update(count=F("count") + 1)
    return RateLimitBucket.objects.get(**where).count <= limit


def too_many(request, scope):
    events.record(events.Kind.RATE_LIMITED, request, detail=scope)
    return render(request, "429.html", status=429)


def limit_by_ip(scope, methods=("POST",), when=None):
    """View decorator: answer 429 once one client address exceeds the scope's limit."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            applies = request.method in methods and (when is None or when(request))
            if applies and not hit(scope, events.client_ip(request) or "unknown"):
                return too_many(request, scope)
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


def purge_expired(older_than_seconds=86400):
    cutoff = timezone.now() - timedelta(seconds=older_than_seconds)
    return RateLimitBucket.objects.filter(window_start__lt=cutoff).delete()[0]
