from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import logistics, tracking
from .models import Order

# Unpaid orders have nothing to fulfil yet, so sellers never see them.
SELLER_VISIBLE = (
    Order.Status.PAID,
    Order.Status.SHIPPED,
    Order.Status.OUT_FOR_DELIVERY,
    Order.Status.DELIVERED,
    Order.Status.CANCELLED,
)

# Orders move Paid -> Shipped -> Out for delivery -> Delivered. A shipped order may also be
# marked delivered directly, for sellers who hand the books over without a courier step.
DELIVERABLE = (Order.Status.SHIPPED, Order.Status.OUT_FOR_DELIVERY)


def _require_seller(request):
    if not request.user.has_perm("catalog.add_book"):
        raise PermissionDenied


def _orders_with_my_books(user):
    return Order.objects.filter(items__book__seller=user, status__in=SELLER_VISIBLE).distinct()


def _seller_order(order, user):
    """The seller's slice of an order: only their own items and what those add up to."""
    items = list(order.items.all())
    mine = [item for item in items if item.book.seller_id == user.pk]
    return {
        "order": order,
        "items": [{"item": item, "line_total": item.unit_price * item.quantity} for item in mine],
        "total": sum((item.unit_price * item.quantity for item in mine), Decimal("0")),
        "shared": len(mine) != len(items),
        "can_ship": order.status == Order.Status.PAID and len(mine) == len(items),
        "can_out_for_delivery": order.status == Order.Status.SHIPPED and len(mine) == len(items),
        "can_deliver": order.status in DELIVERABLE and len(mine) == len(items),
    }


@login_required
def seller_orders(request):
    _require_seller(request)
    orders = (
        _orders_with_my_books(request.user)
        .prefetch_related("items__book")
        .order_by("-created_at", "-pk")
    )
    return render(request, "orders/seller_orders.html", {"rows": [_seller_order(o, request.user) for o in orders]})


@login_required
def seller_order_detail(request, order_id):
    _require_seller(request)
    order = get_object_or_404(
        _orders_with_my_books(request.user).select_related("user").prefetch_related("items__book"), pk=order_id
    )
    return render(request, "orders/seller_order_detail.html", _seller_order(order, request.user))


@login_required
@require_POST
def seller_order_ship(request, order_id):
    _require_seller(request)
    get_object_or_404(_orders_with_my_books(request.user), pk=order_id)
    with transaction.atomic():
        order = Order.objects.select_for_update().prefetch_related("items__book").get(pk=order_id)
        row = _seller_order(order, request.user)
        if order.status != Order.Status.PAID:
            messages.error(request, "Only paid orders can be marked as shipped.")
        elif row["shared"]:
            messages.error(
                request,
                "This order also contains books from other sellers, so it cannot be marked as shipped here.",
            )
        else:
            order.status = Order.Status.SHIPPED
            fields = ["status"]
            if not order.tracking_reference:
                try:
                    order.tracking_reference = logistics.create_shipment(order).reference
                except logistics.ShipmentError:
                    # A carrier hiccup must never block the seller from fulfilling.
                    order.tracking_reference = ""
                else:
                    fields.append("tracking_reference")
            order.save(update_fields=fields)
            tracking.log_status(
                order, Order.Status.SHIPPED, note="Shipped by the seller", by=request.user
            )
            messages.success(request, f"Order #{order.pk} marked as shipped.")
    return redirect("seller_order_detail", order_id=order_id)


@login_required
@require_POST
def seller_order_out_for_delivery(request, order_id):
    _require_seller(request)
    get_object_or_404(_orders_with_my_books(request.user), pk=order_id)
    with transaction.atomic():
        order = Order.objects.select_for_update().prefetch_related("items__book").get(pk=order_id)
        row = _seller_order(order, request.user)
        if order.status != Order.Status.SHIPPED:
            messages.error(request, "Only shipped orders can be marked as out for delivery.")
        elif row["shared"]:
            messages.error(
                request,
                "This order also contains books from other sellers, so it cannot be updated here.",
            )
        else:
            order.status = Order.Status.OUT_FOR_DELIVERY
            order.save(update_fields=["status"])
            tracking.log_status(order, Order.Status.OUT_FOR_DELIVERY, by=request.user)
            messages.success(request, f"Order #{order.pk} marked as out for delivery.")
    return redirect("seller_order_detail", order_id=order_id)


@login_required
@require_POST
def seller_order_deliver(request, order_id):
    """Record delivery, which also lets the buyer review the books."""
    _require_seller(request)
    get_object_or_404(_orders_with_my_books(request.user), pk=order_id)
    with transaction.atomic():
        order = Order.objects.select_for_update().prefetch_related("items__book").get(pk=order_id)
        row = _seller_order(order, request.user)
        if order.status not in DELIVERABLE:
            messages.error(request, "Only shipped or out-for-delivery orders can be marked delivered.")
        elif row["shared"]:
            messages.error(
                request,
                "This order also contains books from other sellers, so it cannot be marked as delivered here.",
            )
        else:
            order.status = Order.Status.DELIVERED
            order.save(update_fields=["status"])
            tracking.log_status(order, Order.Status.DELIVERED, by=request.user)
            messages.success(request, f"Order #{order.pk} marked as delivered.")
    return redirect("seller_order_detail", order_id=order_id)


# --- Bulk fulfilment (FR-8, Test Plan FR-8_ST02) -----------------------------------------
# A seller may ship a batch of paid orders at once. The batch is all or nothing: if any
# selected order cannot be shipped, nothing is written, so a partial update can never
# leave some orders shipped and others silently skipped.

BULK_LIMIT = 100


def _ship_blocker(order, user):
    """Why ``order`` cannot be marked as shipped by ``user``, or "" when it can."""
    row = _seller_order(order, user)
    if not row["items"]:
        return f"Order #{order.pk} is not yours or does not exist."
    if order.status != Order.Status.PAID:
        return f"Order #{order.pk} is not paid, so it cannot be shipped."
    if row["shared"]:
        return f"Order #{order.pk} also contains books from other sellers."
    return ""


@login_required
@require_POST
def seller_orders_bulk_ship(request):
    _require_seller(request)
    ids = [int(value) for value in request.POST.getlist("orders") if str(value).isdigit()]
    ids = list(dict.fromkeys(ids))
    if not ids:
        messages.error(request, "Select at least one order to mark as shipped.")
        return redirect("seller_orders")
    if len(ids) > BULK_LIMIT:
        messages.error(request, f"Select at most {BULK_LIMIT} orders at a time.")
        return redirect("seller_orders")
    with transaction.atomic():
        orders = list(
            Order.objects.select_for_update()
            .filter(pk__in=ids)
            .prefetch_related("items__book")
        )
        found = {order.pk: order for order in orders}
        problems = []
        for pk in ids:
            order = found.get(pk)
            if order is None:
                problems.append(f"Order #{pk} is not yours or does not exist.")
                continue
            blocker = _ship_blocker(order, request.user)
            if blocker:
                problems.append(blocker)
        if problems:
            # Deliberately before any write: the batch is rejected as a whole.
            messages.error(request, "Nothing was shipped. " + " ".join(problems))
            return redirect("seller_orders")
        for order in found.values():
            order.status = Order.Status.SHIPPED
            fields = ["status"]
            if not order.tracking_reference:
                try:
                    order.tracking_reference = logistics.create_shipment(order).reference
                except logistics.ShipmentError:
                    order.tracking_reference = ""
                else:
                    fields.append("tracking_reference")
            order.save(update_fields=fields)
            tracking.log_status(
                order, Order.Status.SHIPPED, note="Shipped in a batch", by=request.user
            )
        shipped = len(found)
    messages.success(request, f"{shipped} order(s) marked as shipped.")
    return redirect("seller_orders")
