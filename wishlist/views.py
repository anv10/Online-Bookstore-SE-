from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from cart.models import Cart, CartItem
from cart.views import _buyable_books
from catalog.models import Book

from .models import WishlistItem


def _is_available(book):
    return (
        book.status == Book.Status.APPROVED
        and (book.seller is None or book.seller.is_active)
        and book.stock > 0
    )


@login_required
def wishlist_detail(request):
    items = WishlistItem.objects.filter(user=request.user).select_related("book", "book__seller")
    lines = [{"item": item, "book": item.book, "available": _is_available(item.book)} for item in items]
    return render(request, "wishlist/wishlist.html", {"lines": lines})


@login_required
@require_POST
def wishlist_add(request, book_id):
    book = get_object_or_404(_buyable_books(), pk=book_id)
    _, created = WishlistItem.objects.get_or_create(user=request.user, book=book)
    if created:
        messages.success(request, f"\"{book.title}\" was added to your wishlist.")
    else:
        messages.info(request, f"\"{book.title}\" is already in your wishlist.")
    return redirect("book_detail", pk=book.pk)


@login_required
@require_POST
def wishlist_remove(request, item_id):
    item = get_object_or_404(WishlistItem.objects.select_related("book"), pk=item_id, user=request.user)
    title = item.book.title
    item.delete()
    messages.success(request, f"\"{title}\" was removed from your wishlist.")
    return redirect("wishlist")


@login_required
@require_POST
def wishlist_to_cart(request, item_id):
    item = get_object_or_404(WishlistItem.objects.select_related("book", "book__seller"), pk=item_id, user=request.user)
    book = item.book
    if not _is_available(book):
        messages.error(request, f"\"{book.title}\" is not available right now.")
        return redirect("wishlist")
    cart, _ = Cart.objects.get_or_create(user=request.user)
    cart_item, created = CartItem.objects.get_or_create(cart=cart, book=book, defaults={"quantity": 1})
    if not created:
        if cart_item.quantity >= book.stock:
            messages.error(request, f"Your cart already has every available copy of \"{book.title}\".")
            return redirect("wishlist")
        cart_item.quantity += 1
        cart_item.save(update_fields=["quantity"])
    item.delete()
    messages.success(request, f"\"{book.title}\" was moved to your cart.")
    return redirect("cart")
