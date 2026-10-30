"""Stripe Checkout, the hosted payment page, over Stripe's documented REST API (FR-5, NFR-11).

The buyer pays on Stripe's own page, so the card number, expiry and security
code never reach this server (NFR-6). We only create a Checkout Session, send
the buyer there, and afterwards ask Stripe whether the session was paid.

Only the standard library is used for HTTP. The secret key is read from
``STRIPE_SECRET_KEY`` and is never logged or written to the database. Use a
test-mode key (``sk_test_...``) for development and demos.
"""

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.stripe.com/v1"
TIMEOUT_SECONDS = 15
CURRENCY = "inr"
SESSION_ID = re.compile(r"^cs_[A-Za-z0-9_]+$")


class StripeError(Exception):
    """Stripe could not be reached or refused the request. The message is safe to show."""


def to_minor_units(amount):
    """Rupees as a Decimal to paise as an int, which is what Stripe expects."""
    return int((amount * 100).to_integral_value())


def _request(method, path, params=None):
    key = settings.STRIPE_SECRET_KEY
    if not key:
        raise StripeError("Payments are not configured. Contact the store.")
    body = urllib.parse.urlencode(params).encode() if params else None
    request = urllib.request.Request(
        f"{API_BASE}{path}",
        data=body,
        method=method,
        headers={"Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        # Status only: neither the key nor the buyer's details are written to the log.
        logger.warning("Stripe %s %s answered %s", method, path.split("/")[1], error.code)
        raise StripeError("The payment provider refused the request.") from error
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        logger.warning("Stripe %s %s could not be completed (%s)", method, path.split("/")[1], type(error).__name__)
        raise StripeError("The payment provider could not be reached.") from error


def create_checkout_session(pending_id, email, items, success_url, cancel_url, discount=None):
    """Start a hosted payment. ``items`` is a list of (name, amount in paise, quantity).

    ``discount`` is an optional (coupon code, amount in paise) taken off the whole
    payment, since a line item cannot be negative.
    """
    params = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(pending_id),
        "metadata[pending_payment_id]": str(pending_id),
    }
    if email:
        params["customer_email"] = email
    for index, (name, amount, quantity) in enumerate(items):
        prefix = f"line_items[{index}]"
        params[f"{prefix}[quantity]"] = str(quantity)
        params[f"{prefix}[price_data][currency]"] = CURRENCY
        params[f"{prefix}[price_data][unit_amount]"] = str(amount)
        params[f"{prefix}[price_data][product_data][name]"] = name
    if discount and discount[1] > 0:
        stripe_coupon = _request(
            "POST",
            "/coupons",
            {"amount_off": str(discount[1]), "currency": CURRENCY, "duration": "once", "name": discount[0][:40]},
        )
        if not stripe_coupon.get("id"):
            raise StripeError("The payment provider sent an unexpected answer.")
        params["discounts[0][coupon]"] = stripe_coupon["id"]
    session = _request("POST", "/checkout/sessions", params)
    if not session.get("id") or not session.get("url"):
        raise StripeError("The payment provider sent an unexpected answer.")
    return session


def retrieve_session(session_id):
    if not SESSION_ID.match(session_id or ""):
        raise StripeError("That payment reference is not valid.")
    return _request("GET", f"/checkout/sessions/{session_id}")


def refund(payment_intent):
    if not payment_intent:
        raise StripeError("There is no payment to refund.")
    return _request("POST", "/refunds", {"payment_intent": payment_intent})
