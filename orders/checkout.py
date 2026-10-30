"""Cart review and order placement for checkout (FR-5).

Totals are subtotal - coupon discount + tax + shipping, all in rupees, so the figure the buyer
approves on the checkout page is the figure stored on the order. Stock is
locked and re-checked inside the order transaction, and the order only exists
once the gateway accepts the card.
"""

import logging
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F

from cart.models import Cart
from catalog.models import Book

from . import coupons, payments, stripe_gateway
from .models import Coupon, Order, OrderItem, PendingPayment

logger = logging.getLogger(__name__)

MONEY = Decimal("0.01")


class CheckoutError(Exception):
    """Checkout cannot continue; the message is safe to show the buyer."""


class PaymentDeclined(CheckoutError):
    """The gateway refused the card, so no order was created and the cart is intact."""


def money(value):
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def is_buyable(book):
    return book.status == Book.Status.APPROVED and (book.seller is None or book.seller.is_active)


def totals_for(subtotal, discount=0):
    """Tax is charged on the discounted subtotal; shipping is a flat fee."""
    subtotal = money(subtotal)
    discount = min(money(discount), subtotal)
    tax = money((subtotal - discount) * Decimal(settings.CHECKOUT_TAX_RATE))
    shipping = money(settings.CHECKOUT_SHIPPING_FLAT) if subtotal else money(0)
    return {
        "subtotal": subtotal,
        "discount": discount,
        "tax": tax,
        "shipping": shipping,
        "total": money(subtotal - discount + tax + shipping),
    }


def build_summary(cart, coupon=None):
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
    return {
        **totals_for(subtotal, coupons.discount_for(coupon, subtotal)),
        "coupon": coupon,
        "lines": lines,
        "problems": problems,
    }


def place_order(user, shipping_address, card, gateway=None, coupon_code=""):
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
        coupon = coupons.find(coupon_code, for_update=True) if coupon_code else None
        totals = totals_for(subtotal, coupons.discount_for(coupon, subtotal))
        result = gateway.charge(card, totals["total"])
        if not result.success:
            raise PaymentDeclined(result.error or "Payment failed. No money was taken.")
        order = Order.objects.create(
            user=user,
            status=Order.Status.PAID,
            total=totals["total"],
            discount=totals["discount"],
            coupon_code=coupon.code if coupon else "",
            shipping_address=shipping_address,
        )
        if coupon:
            coupons.redeem(coupon)
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


# --- Hosted payment (Stripe Checkout, issue #10) -------------------------------------------
# The buyer pays on the gateway's own page. Nothing is charged by this server, no card data
# reaches it, and the order is only created once the gateway confirms the session was paid.


def start_hosted_payment(user, shipping_address, success_url, cancel_url, coupon_code=""):
    """Record the payment and return the gateway page the buyer must be sent to."""
    coupon = coupons.find(coupon_code) if coupon_code else None
    summary = build_summary(Cart.objects.filter(user=user).first(), coupon)
    if not summary["lines"]:
        raise CheckoutError("Your cart is empty. Add a book before checking out.")
    if summary["problems"]:
        raise CheckoutError("Some items in your cart need attention before you can check out.")
    lines = [
        {"book_id": line["book"].pk, "quantity": line["item"].quantity, "unit_price": str(line["book"].price)}
        for line in summary["lines"]
    ]
    pending = PendingPayment.objects.create(
        user=user,
        total=summary["total"],
        discount=summary["discount"],
        coupon_code=coupon.code if coupon else "",
        shipping_address=shipping_address,
        lines=lines,
    )
    items = [
        (line["book"].title, stripe_gateway.to_minor_units(line["book"].price), line["item"].quantity)
        for line in summary["lines"]
    ]
    if summary["tax"]:
        items.append(("Tax", stripe_gateway.to_minor_units(summary["tax"]), 1))
    if summary["shipping"]:
        items.append(("Shipping", stripe_gateway.to_minor_units(summary["shipping"]), 1))
    try:
        session = stripe_gateway.create_checkout_session(
            pending.pk,
            user.email,
            items,
            success_url,
            f"{cancel_url}?payment={pending.pk}",
            discount=(pending.coupon_code, stripe_gateway.to_minor_units(pending.discount)) if coupon else None,
        )
    except stripe_gateway.StripeError as error:
        pending.status = PendingPayment.Status.FAILED
        pending.save(update_fields=["status"])
        raise CheckoutError(f"{error} No money was taken. Please try again.") from error
    pending.session_id = session["id"]
    pending.save(update_fields=["session_id"])
    return session["url"]


def cancel_hosted_payment(user, payment_id):
    """The buyer backed out on the gateway page. Nothing was charged and no order exists."""
    if not str(payment_id).isdigit():
        return
    PendingPayment.objects.filter(
        pk=int(payment_id), user=user, status=PendingPayment.Status.STARTED, order__isnull=True
    ).update(status=PendingPayment.Status.CANCELLED)


def complete_hosted_payment(user, session_id):
    """Ask the gateway whether the session was paid, then create the paid order (once)."""
    pending = PendingPayment.objects.filter(user=user, session_id=session_id).first()
    if pending is None:
        raise CheckoutError("We could not find that payment.")
    if pending.order_id:
        return pending.order
    if pending.status != PendingPayment.Status.STARTED:
        raise CheckoutError("That payment was not completed, so no order was created. No money was taken.")
    try:
        session = stripe_gateway.retrieve_session(session_id)
    except stripe_gateway.StripeError as error:
        raise CheckoutError(
            f"We could not confirm your payment yet. If money was taken, quote payment #{pending.pk} to the store."
        ) from error
    paid = (
        session.get("payment_status") == "paid"
        and session.get("amount_total") == stripe_gateway.to_minor_units(pending.total)
        and session.get("currency") == stripe_gateway.CURRENCY
        and session.get("client_reference_id") == str(pending.pk)
    )
    if not paid:
        raise CheckoutError("Your payment was not completed, so no order was created. No money was taken.")
    sold_out = None
    with transaction.atomic():
        pending = PendingPayment.objects.select_for_update().get(pk=pending.pk)
        if pending.order_id:
            return pending.order
        lines = pending.lines
        locked = {
            book.pk: book
            for book in Book.objects.select_for_update().filter(pk__in=[line["book_id"] for line in lines])
        }
        for line in lines:
            book = locked.get(line["book_id"])
            if book is None or not is_buyable(book) or line["quantity"] > book.stock:
                sold_out = book.title if book else "A book"
                break
        if sold_out is None:
            order = Order.objects.create(
                user=user,
                status=Order.Status.PAID,
                total=pending.total,
                discount=pending.discount,
                coupon_code=pending.coupon_code,
                shipping_address=pending.shipping_address,
            )
            if pending.coupon_code:
                # Already validated and paid for when the payment started; count the use.
                Coupon.objects.filter(code=pending.coupon_code).update(times_used=F("times_used") + 1)
            OrderItem.objects.bulk_create(
                [
                    OrderItem(
                        order=order,
                        book=locked[line["book_id"]],
                        quantity=line["quantity"],
                        unit_price=Decimal(line["unit_price"]),
                    )
                    for line in lines
                ]
            )
            for line in lines:
                updated = Book.objects.filter(pk=line["book_id"], stock__gte=line["quantity"]).update(
                    stock=F("stock") - line["quantity"]
                )
                if not updated:
                    raise CheckoutError("A book sold out while you were paying. Please contact the store.")
            cart = Cart.objects.filter(user=user).first()
            if cart:
                cart.items.filter(book_id__in=[line["book_id"] for line in lines]).delete()
            pending.order = order
            pending.status = PendingPayment.Status.COMPLETED
            pending.save(update_fields=["order", "status"])
            return order
    # Paid, but a copy sold out in the meantime: give the money back instead of keeping it.
    try:
        stripe_gateway.refund(session.get("payment_intent"))
    except stripe_gateway.StripeError:
        logger.error("Refund failed for payment %s", pending.pk)
        PendingPayment.objects.filter(pk=pending.pk).update(status=PendingPayment.Status.FAILED)
        raise CheckoutError(
            f'"{sold_out}" sold out while you were paying and we could not refund you automatically. '
            f"Please contact the store and quote payment #{pending.pk}."
        )
    PendingPayment.objects.filter(pk=pending.pk).update(status=PendingPayment.Status.REFUNDED)
    raise CheckoutError(f'"{sold_out}" sold out while you were paying. Your payment has been refunded.')
