"""Cart review and order placement for checkout (FR-5).

Totals are subtotal + tax + shipping, all in rupees, so the figure the buyer
approves on the checkout page is the figure stored on the order. Stock is
locked and re-checked inside the order transaction, and the order only exists
once the gateway accepts the card.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F

from cart.models import Cart
from catalog.models import Book

from . import payments
from .models import Order, OrderItem

MONEY = Decimal("0.01")


class CheckoutError(Exception):
    """Checkout cannot continue; the message is safe to show the buyer."""


class PaymentDeclined(CheckoutError):
    """The gateway refused the card, so no order was created and the cart is intact."""


def money(value):
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def is_buyable(book):
    return book.status == Book.Status.APPROVED and (book.seller is None or book.seller.is_active)


def totals_for(subtotal):
    subtotal = money(subtotal)
    tax = money(subtotal * Decimal(settings.CHECKOUT_TAX_RATE))
    shipping = money(settings.CHECKOUT_SHIPPING_FLAT) if subtotal else money(0)
    return {"subtotal": subtotal, "tax": tax, "shipping": shipping, "total": money(subtotal + tax + shipping)}


def build_summary(cart):
    """Lines and totals for the checkout page, using the same availability rules as the cart."""
    items = cart.items.select_related("book", "book__seller").order_by("pk") if cart else []
    lines = []
    problems = []
    subtotal = Decimal("0")
    for item in items:
        book = item.book
        line_total = money(book.price * item.quantity)
        problem = ""
        if not is_buyable(book):
            problem = f'"{book.title}" is no longer available.'
        elif item.quantity > book.stock:
            problem = f'Only {book.stock} left of "{book.title}".'
        if problem:
            problems.append(problem)
        else:
            subtotal += line_total
        lines.append({"item": item, "book": book, "line_total": line_total, "problem": problem})
    return {**totals_for(subtotal), "lines": lines, "problems": problems}


def place_order(user, shipping_address, card, gateway=None):
    """Charge the card and create the paid order, or raise without changing anything."""
    try:
        gateway = gateway or payments.get_gateway()
    except payments.PaymentError as error:
        raise CheckoutError(str(error)) from error
    with transaction.atomic():
        cart = Cart.objects.filter(user=user).first()
        items = list(cart.items.select_related("book", "book__seller").order_by("pk")) if cart else []
        if not items:
            raise CheckoutError("Your cart is empty. Add a book before checking out.")
        locked = {
            book.pk: book
            for book in Book.objects.select_for_update().filter(pk__in=[item.book_id for item in items])
        }
        subtotal = Decimal("0")
        for item in items:
            book = locked[item.book_id]
            if not is_buyable(book):
                raise CheckoutError(f'"{book.title}" is no longer available. Remove it from your cart.')
            if item.quantity > book.stock:
                raise CheckoutError(f'Only {book.stock} left of "{book.title}". Lower the copies in your cart.')
            subtotal += money(book.price * item.quantity)
        totals = totals_for(subtotal)
        result = gateway.charge(card, totals["total"])
        if not result.success:
            raise PaymentDeclined(result.error or "Payment failed. No money was taken.")
        order = Order.objects.create(
            user=user,
            status=Order.Status.PAID,
            total=totals["total"],
            shipping_address=shipping_address,
        )
        OrderItem.objects.bulk_create(
            [
                OrderItem(
                    order=order,
                    book=locked[item.book_id],
                    quantity=item.quantity,
                    unit_price=locked[item.book_id].price,
                )
                for item in items
            ]
        )
        for item in items:
            updated = Book.objects.filter(pk=item.book_id, stock__gte=item.quantity).update(
                stock=F("stock") - item.quantity
            )
            if not updated:
                raise CheckoutError(f'"{locked[item.book_id].title}" sold out while you were paying. Please try again.')
        cart.items.all().delete()
        return order
