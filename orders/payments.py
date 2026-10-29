"""Card payments for checkout (FR-5, NFR-12).

Checkout talks to the small gateway interface below instead of a provider SDK.
Issue #10 owns the real gateway integration, so the provider is selected by
``PAYMENT_GATEWAY`` and adding one only means implementing ``charge`` here.
The sandbox provider is the only one enabled for development, tests and demos.

No card number, expiry or security code is ever persisted, logged, put in the
session or written back into a rendered page (NFR-6).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.conf import settings

CARD_NUMBER_LENGTHS = range(13, 20)


class PaymentError(Exception):
    """A card problem the buyer has to fix before the gateway is contacted."""


@dataclass(frozen=True)
class CardDetails:
    number: str
    expiry: str
    cvc: str

    @property
    def last4(self):
        return self.number[-4:]


@dataclass(frozen=True)
class PaymentResult:
    success: bool
    reference: str = ""
    error: str = ""


def clean_number(raw):
    number = "".join(char for char in (raw or "") if char not in " -")
    if not number.isdigit() or len(number) not in CARD_NUMBER_LENGTHS:
        raise PaymentError("Invalid card number.")
    if not _luhn_valid(number):
        raise PaymentError("Invalid card number.")
    return number


def clean_expiry(raw):
    expiry = (raw or "").strip()
    month, separator, year = expiry.partition("/")
    if not separator or not (len(month) == 2 and month.isdigit()) or not (len(year) == 2 and year.isdigit()):
        raise PaymentError("Invalid expiry date.")
    month = int(month)
    if not 1 <= month <= 12:
        raise PaymentError("Invalid expiry date.")
    today = date.today()
    if (2000 + int(year), month) < (today.year, today.month):
        raise PaymentError("Invalid expiry date.")
    return f"{month:02d}/{year}"


def clean_cvc(raw):
    cvc = (raw or "").strip()
    if not cvc.isdigit() or len(cvc) not in (3, 4):
        raise PaymentError("Invalid security code.")
    return cvc


def _luhn_valid(number):
    total = 0
    for position, char in enumerate(reversed(number)):
        digit = int(char)
        if position % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


class SandboxGateway:
    """Deterministic test gateway with the decline-then-error contract of hosted gateways."""

    def charge(self, card, amount):
        decline_cards = settings.PAYMENT_SANDBOX_DECLINE_CARDS
        if card.number in decline_cards:
            return PaymentResult(False, error="Your card was declined. No money was taken.")
        return PaymentResult(True, reference=f"SBX-{uuid4().hex[:12].upper()}")


def get_gateway():
    if settings.PAYMENT_GATEWAY == "sandbox":
        return SandboxGateway()
    raise PaymentError("Payments are not configured. Contact the store.")
