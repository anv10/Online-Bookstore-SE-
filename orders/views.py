from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from cart.models import Cart

from . import checkout as checkout_service
from .forms import CheckoutForm
from .models import Order


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
