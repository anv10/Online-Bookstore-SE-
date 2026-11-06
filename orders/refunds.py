"""Partial refunds on an order (FR-13).

A refund is recorded as its own row so the invoice can show what was actually
kept. The order total never changes: the invoice reports ``total`` and then
deducts the refunded amount, which keeps the original charge auditable.

Moving the money is the payment provider's job (see ``stripe_gateway.refund``);
this module only records the decision and enforces the limits.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from .models import Refund

MONEY = Decimal("0.01")


class RefundError(Exception):
    """The refund cannot be recorded; the message is safe to show to staff."""


def money(value):
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def record_refund(order, amount, reason="", by=None):
    """Record a refund of ``amount`` rupees against ``order``."""
    try:
        amount = money(amount)
    except (ArithmeticError, ValueError, TypeError) as error:
        raise RefundError("Enter a valid refund amount.") from error
    if amount <= 0:
        raise RefundError("A refund must be more than zero.")
    with transaction.atomic():
        locked = order.__class__.objects.select_for_update().get(pk=order.pk)
        if locked.refunded_total + amount > locked.total:
            raise RefundError("A refund cannot exceed the order total.")
        return Refund.objects.create(
            order=locked, amount=amount, reason=reason, created_by=by
        )
