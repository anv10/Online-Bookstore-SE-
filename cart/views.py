from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from catalog.models import Book

from .models import Cart, CartItem


def _buyable_books():
    """Books a buyer can see on the details page, and therefore can put in a cart."""
    return Book.objects.filter(status=Book.Status.APPROVED).exclude(seller__is_active=False)


def _parse_quantity(raw):
    try:
        quantity = int(raw)
    except (TypeError, ValueError):
        return None
    return quantity if quantity >= 1 else None


@login_required
def cart_detail(request):
    cart, _ = Cart.objects.get_or_create(user=request.user)
    lines = []
    total = Decimal("0")
    for item in cart.items.select_related("book", "book__seller").order_by("pk"):
        book = item.book
        buyable = (
            book.status == Book.Status.APPROVED
            and (book.seller is None or book.seller.is_active)
            and book.stock > 0
        )
        subtotal = book.price * item.quantity
        if buyable:
            total += subtotal
        lines.append(
            {
                "item": item,
                "book": book,
                "subtotal": subtotal,
                "buyable": buyable,
                "over_stock": buyable and item.quantity > book.stock,
            }
        )
    return render(request, "cart/cart.html", {"lines": lines, "total": total})


@login_required
@require_POST
def cart_add(request, book_id):
    book = get_object_or_404(_buyable_books(), pk=book_id)
    quantity = _parse_quantity(request.POST.get("quantity", "1"))
    if quantity is None:
        messages.error(request, "Enter a whole number of copies, 1 or more.")
        return redirect("book_detail", pk=book.pk)
    if book.stock < 1:
        messages.error(request, f"\"{book.title}\" is out of stock.")
        return redirect("book_detail", pk=book.pk)
    cart, _ = Cart.objects.get_or_create(user=request.user)
    try:
        with transaction.atomic():
            item, created = CartItem.objects.select_for_update().get_or_create(
                cart=cart, book=book, defaults={"quantity": 0}
            )
            in_cart = 0 if created else item.quantity
            wanted = in_cart + quantity
            if wanted > book.stock:
                if created:
                    item.delete()
                message = f"Only {book.stock} available of \"{book.title}\""
                if in_cart:
                    message += f", and {in_cart} already in your cart"
                messages.error(request, message + ".")
                return redirect("book_detail", pk=book.pk)
            item.quantity = wanted
            item.save(update_fields=["quantity"])
    except IntegrityError:
        messages.error(request, "Could not update your cart. Please try again.")
        return redirect("book_detail", pk=book.pk)
    messages.success(request, f"\"{book.title}\" is in your cart.")
    return redirect("cart")


def _own_item_or_404(request, item_id):
    return get_object_or_404(CartItem.objects.select_related("book"), pk=item_id, cart__user=request.user)


@login_required
@require_POST
def cart_update(request, item_id):
    item = _own_item_or_404(request, item_id)
    quantity = _parse_quantity(request.POST.get("quantity"))
    if quantity is None:
        messages.error(request, "Enter a whole number of copies, 1 or more. Use Remove to take an item out.")
    elif quantity > item.book.stock:
        messages.error(request, f"Only {item.book.stock} available of \"{item.book.title}\".")
    else:
        item.quantity = quantity
        item.save(update_fields=["quantity"])
        messages.success(request, "Cart updated.")
    return redirect("cart")


@login_required
@require_POST
def cart_remove(request, item_id):
    item = _own_item_or_404(request, item_id)
    title = item.book.title
    item.delete()
    messages.success(request, f"\"{title}\" was removed from your cart.")
    return redirect("cart")
