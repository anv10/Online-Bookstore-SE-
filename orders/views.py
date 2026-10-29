from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from cart.models import Cart

from . import checkout as checkout_service
from .forms import CheckoutForm
from .models import Order
from .tracking import tracking_steps

INVOICE_STATUSES = (
    Order.Status.PAID,
    Order.Status.SHIPPED,
    Order.Status.OUT_FOR_DELIVERY,
    Order.Status.DELIVERED,
)


def _last_address(user):
    return (
        Order.objects.filter(user=user)
        .order_by("-created_at", "-pk")
        .values_list("shipping_address", flat=True)
        .first()
        or ""
    )


@login_required
def checkout(request):
    summary = checkout_service.build_summary(Cart.objects.filter(user=request.user).first())
    if not summary["lines"]:
        messages.error(request, "Your cart is empty. Add a book before checking out.")
        return redirect("cart")
    if summary["problems"]:
        messages.error(request, "Some items in your cart need attention before you can check out.")
        return redirect("cart")
    form = CheckoutForm(
        request.POST if request.method == "POST" else None,
        initial={"shipping_address": _last_address(request.user)},
    )
    if request.method == "POST" and form.is_valid():
        try:
            order = checkout_service.place_order(
                request.user, form.cleaned_data["shipping_address"], form.card()
            )
        except checkout_service.PaymentDeclined as error:
            form.add_error(None, str(error))
        except checkout_service.CheckoutError as error:
            messages.error(request, str(error))
            return redirect("cart")
        else:
            messages.success(request, f"Payment received. Order #{order.pk} is confirmed.")
            return redirect("order_confirmation", pk=order.pk)
    return render(request, "orders/checkout.html", {"form": form, "summary": summary})


@login_required
def order_confirmation(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related("items__book"), pk=pk, user=request.user)
    return render(request, "orders/confirmation.html", {"order": order})


def _own_order_or_404(request, order_id):
    """The buyer's own order. Anyone else's order looks like it does not exist."""
    queryset = Order.objects.prefetch_related("items__book")
    return get_object_or_404(queryset, pk=order_id, user=request.user)


def build_invoice(order):
    """Invoice figures from what the order already stores.

    Orders keep the price of every item and one total. Anything the total is
    below the item subtotal counts as a discount, anything above it as taxes
    and charges, so the invoice always adds up to what the buyer paid.
    """
    lines = []
    subtotal = Decimal("0")
    for item in order.items.all():
        line_total = item.unit_price * item.quantity
        subtotal += line_total
        lines.append({"item": item, "title": item.book.title, "line_total": line_total})
    difference = order.total - subtotal
    return {
        "order": order,
        "number": f"INV-{order.pk:06d}",
        "lines": lines,
        "subtotal": subtotal,
        "discounts": max(-difference, Decimal("0")),
        "taxes": max(difference, Decimal("0")),
        "total": order.total,
    }


@login_required
def order_list(request):
    orders = Order.objects.filter(user=request.user).order_by("-created_at", "-pk")
    return render(request, "orders/order_list.html", {"orders": orders})


@login_required
def order_detail(request, order_id):
    order = _own_order_or_404(request, order_id)
    context = build_invoice(order)
    context["has_invoice"] = order.status in INVOICE_STATUSES
    context["tracking"] = tracking_steps(order)
    return render(request, "orders/order_detail.html", context)


def _paid_invoice_or_404(request, order_id):
    order = _own_order_or_404(request, order_id)
    if order.status not in INVOICE_STATUSES:
        raise Http404("No invoice for this order")
    return build_invoice(order)


@login_required
def invoice_view(request, order_id):
    return render(request, "orders/invoice.html", {"invoice": _paid_invoice_or_404(request, order_id)})


@login_required
def invoice_download(request, order_id):
    invoice = _paid_invoice_or_404(request, order_id)
    html = render_to_string("orders/invoice_document.html", {"invoice": invoice}, request=request)
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="invoice-{invoice["number"]}.html"'
    return response
