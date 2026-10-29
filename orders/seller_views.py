from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Order

# Unpaid orders have nothing to fulfil yet, so sellers never see them.
SELLER_VISIBLE = (Order.Status.PAID, Order.Status.SHIPPED, Order.Status.DELIVERED, Order.Status.CANCELLED)


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
        "can_deliver": order.status == Order.Status.SHIPPED and len(mine) == len(items),
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
            order.save(update_fields=["status"])
            messages.success(request, f"Order #{order.pk} marked as shipped.")
    return redirect("seller_order_detail", order_id=order_id)


@login_required
@require_POST
def seller_order_deliver(request, order_id):
    """Record delivery so the buyer can review the books. Order tracking (#14) owns the full lifecycle UI."""
    _require_seller(request)
    get_object_or_404(_orders_with_my_books(request.user), pk=order_id)
    with transaction.atomic():
        order = Order.objects.select_for_update().prefetch_related("items__book").get(pk=order_id)
        row = _seller_order(order, request.user)
        if order.status != Order.Status.SHIPPED:
            messages.error(request, "Only shipped orders can be marked as delivered.")
        elif row["shared"]:
            messages.error(
                request,
                "This order also contains books from other sellers, so it cannot be marked as delivered here.",
            )
        else:
            order.status = Order.Status.DELIVERED
            order.save(update_fields=["status"])
            messages.success(request, f"Order #{order.pk} marked as delivered.")
    return redirect("seller_order_detail", order_id=order_id)
