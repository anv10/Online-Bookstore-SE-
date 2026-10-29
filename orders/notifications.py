"""Order confirmation emails (FR-6).

The email goes out after the order has been committed, so it can never hold up
or undo an order. If sending fails the reason is logged and the confirmation
stays pending, and ``manage.py retry_order_confirmations`` sends it again.
"""

import logging

from django.core.mail import send_mail
from django.utils import timezone

from .models import Order, OrderConfirmation

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5


def confirmation_message(order):
    """Subject and plain text body: order id, items and total. The shipping address is not emailed."""
    lines = [
        f"{item.book.title} x {item.quantity} at Rs {item.unit_price} = Rs {item.unit_price * item.quantity}"
        for item in order.items.select_related("book").order_by("pk")
    ]
    body = "\n".join(
        [
            "Thank you for your order at Chapter & Co.",
            "",
            f"Order number: {order.pk}",
            f"Placed on: {order.created_at:%d %b %Y}",
            "",
            "Items:",
            *lines,
            "",
            f"Total: Rs {order.total}",
            "",
            "You can see this order, and its invoice once it is paid, under Orders in your account.",
        ]
    )
    return f"Your order #{order.pk} is confirmed", body


def send_confirmation(confirmation):
    """Try to send one pending confirmation. Returns True once it has been sent."""
    if confirmation.state != OrderConfirmation.State.PENDING:
        return confirmation.state == OrderConfirmation.State.SENT
    order = Order.objects.select_related("user").get(pk=confirmation.order_id)
    if not order.user.email:
        confirmation.state = OrderConfirmation.State.SKIPPED
        confirmation.last_error = "no email address"
        confirmation.save(update_fields=["state", "last_error"])
        return False
    subject, body = confirmation_message(order)
    try:
        if send_mail(subject, body, None, [order.user.email]) != 1:
            raise RuntimeError("the mail backend did not accept the message")
    except Exception as error:
        confirmation.attempts += 1
        confirmation.last_error = type(error).__name__[:100]
        if confirmation.attempts >= MAX_ATTEMPTS:
            confirmation.state = OrderConfirmation.State.FAILED
        confirmation.save(update_fields=["attempts", "last_error", "state"])
        # Only the error type is logged: never the message text or the address.
        logger.warning(
            "Confirmation email for order %s failed (attempt %s of %s): %s",
            order.pk,
            confirmation.attempts,
            MAX_ATTEMPTS,
            confirmation.last_error,
        )
        return False
    confirmation.state = OrderConfirmation.State.SENT
    confirmation.attempts += 1
    confirmation.last_error = ""
    confirmation.sent_at = timezone.now()
    confirmation.save(update_fields=["state", "attempts", "last_error", "sent_at"])
    return True


def queue_confirmation(order_id):
    """Record and send the confirmation for a new order. Never raises."""
    try:
        confirmation, _ = OrderConfirmation.objects.get_or_create(order_id=order_id)
        send_confirmation(confirmation)
    except Exception as error:
        logger.warning("Could not queue the confirmation email for order %s: %s", order_id, type(error).__name__)
