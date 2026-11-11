"""SMS order confirmations (FR-6).

Like card payments, SMS goes through a small gateway interface selected by
``SMS_GATEWAY`` so a provider can be added by implementing ``send`` here. Only
the ``console`` gateway ships: it logs a masked line instead of texting anyone
and keeps the message in ``outbox`` so tests and demos can read it. Set
``SMS_GATEWAY`` to an empty value to turn SMS off.

The text never contains the shipping address, and logs never contain the full
phone number or the message body.
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# Messages "sent" by the console gateway, newest last. Tests clear it.
outbox = []


class SmsError(Exception):
    """The message could not be handed to the SMS provider."""


class ConsoleGateway:
    def send(self, phone, body):
        outbox.append({"to": phone, "body": body})
        logger.info("SMS to ...%s (%s characters) accepted by the console gateway", phone[-4:], len(body))


def get_gateway():
    """The configured gateway, or None when SMS is switched off."""
    name = (settings.SMS_GATEWAY or "").strip()
    if not name:
        return None
    if name == "console":
        return ConsoleGateway()
    raise SmsError("SMS gateway is not configured.")


def confirmation_text(order):
    count = sum(item.quantity for item in order.items.all())
    copies = "copy" if count == 1 else "copies"
    return f"Chapter & Co: {order.reference} confirmed. {count} {copies}, total Rs {order.total}."
