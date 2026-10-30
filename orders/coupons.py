"""Discount codes for checkout (FR-11).

A coupon is a percentage or a fixed rupee amount taken off the book subtotal.
Tax is then worked out on the discounted subtotal, so the figure the buyer sees
on the checkout page is the figure charged and stored on the order. One coupon
applies per order: the buyer's session holds a single code.
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Coupon

SESSION_KEY = "coupon_code"


class CouponError(Exception):
    """The coupon cannot be used; the message is safe to show the buyer."""


def normalise(code):
    return (code or "").strip().upper()


def _check(coupon, now=None):
    now = now or timezone.now()
    if not coupon.active:
        raise CouponError("That coupon code is not valid.")
    if coupon.expires_at and coupon.expires_at <= now:
        raise CouponError("That coupon has expired.")
    if coupon.max_uses is not None and coupon.times_used >= coupon.max_uses:
        raise CouponError("That coupon has reached its usage limit.")
    return coupon


def find(code, for_update=False):
    """The usable coupon for ``code``, or CouponError saying why not."""
    code = normalise(code)
    if not code:
        raise CouponError("Enter a coupon code.")
    queryset = Coupon.objects.select_for_update() if for_update else Coupon.objects
    coupon = queryset.filter(code=code).first()
    if coupon is None:
        raise CouponError("That coupon code is not valid.")
    return _check(coupon)


def discount_for(coupon, subtotal):
    """Rupees off ``subtotal``, never more than the subtotal itself."""
    from .checkout import money

    if coupon is None:
        return money(0)
    if coupon.kind == Coupon.Kind.PERCENT:
        amount = money(subtotal * coupon.value / Decimal(100))
    else:
        amount = money(coupon.value)
    return min(amount, money(subtotal))


def redeem(coupon):
    """Count one use. Call inside the order transaction, on a row locked by ``find``."""
    Coupon.objects.filter(pk=coupon.pk).update(times_used=F("times_used") + 1)


def remembered(session):
    """The coupon held in the session, or None. A coupon that stopped being valid is dropped."""
    code = session.get(SESSION_KEY)
    if not code:
        return None, ""
    try:
        return find(code), ""
    except CouponError as error:
        session.pop(SESSION_KEY, None)
        return None, str(error)
