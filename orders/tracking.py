"""Order progress and shipment tracking (FR-9).

The timeline comes from ``OrderStatusLog``, one row per status change, so a
buyer sees the history rather than only the current status. The carrier
integration lives in ``orders.logistics``; this module decides what the order
should show and never lets a carrier problem break the page.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from . import logistics
from .models import Order, OrderStatusLog

# Label and how far along the order is when it reaches that step.
STEPS = ("Placed", "Shipped", "Out for delivery", "Delivered")
PROGRESS = {
    Order.Status.PENDING: 0,
    Order.Status.PAID: 0,
    Order.Status.SHIPPED: 1,
    Order.Status.OUT_FOR_DELIVERY: 2,
    Order.Status.DELIVERED: 3,
}
# Used to refuse a carrier update that would move an order backwards.
RANK = dict(PROGRESS)


def tracking_steps(order):
    """Steps with a state of done, current or upcoming. Cancelled orders have no tracker."""
    if order.status not in PROGRESS:
        return []
    reached = PROGRESS[order.status]
    delivered = order.status == Order.Status.DELIVERED
    steps = []
    for index, label in enumerate(STEPS):
        if index < reached or (delivered and index == reached):
            state = "done"
        elif index == reached:
            state = "current"
        else:
            state = "upcoming"
        steps.append({"label": label, "state": state})
    return steps


def log_status(order, status, note="", by=None):
    """Record a status change once, so the timeline never repeats a step."""
    last = order.status_log.order_by("-created_at", "-pk").first()
    if last is not None and last.status == status:
        return None
    return OrderStatusLog.objects.create(
        order=order, status=status, note=note, changed_by=by
    )


def advance(order, status, note="", by=None):
    """Move the order forward. Backwards or unknown moves are ignored."""
    if status not in RANK or order.status not in RANK:
        return False
    if RANK[status] <= RANK[order.status]:
        return False
    order.status = status
    order.save(update_fields=["status"])
    log_status(order, status, note=note, by=by)
    return True


def status_timeline(order):
    """The recorded history, oldest first."""
    return [
        {
            "status": entry.status,
            "label": entry.get_status_display(),
            "note": entry.note,
            "at": entry.created_at,
        }
        for entry in order.status_log.all()
    ]


def estimated_delivery(order):
    """Ship date plus the configured transit time (FR-9, Test Plan FR-9_UT03)."""
    if order.status in (Order.Status.DELIVERED, Order.Status.CANCELLED):
        return None
    shipped = order.status_log.filter(status=Order.Status.SHIPPED).first()
    start = shipped.created_at if shipped else order.created_at
    days = getattr(settings, "SHIPPING_TRANSIT_DAYS", 5)
    return timezone.localtime(start).date() + timedelta(days=days)


def refresh_from_carrier(order):
    """Ask the carrier for the live status.

    Returns ``(status, problem)``. On any carrier problem the status is empty and
    ``problem`` holds a message for the page, so the buyer keeps seeing the last
    known state instead of an error (FR-9_ST02).
    """
    if not order.tracking_reference:
        return "", ""
    fallback = "Live tracking is unavailable right now. Showing the last known status."
    try:
        payload = logistics.fetch_status(order.tracking_reference)
    except logistics.ShipmentError:
        return "", fallback
    status = logistics.normalise_status((payload or {}).get("status"))
    if not status:
        return "", fallback
    return status, ""
