"""Carrier integration for shipments (FR-9, NFR-11).

Only the standard library is used for HTTP, mirroring ``orders.stripe_gateway``.
The sandbox carrier is the default, so development, tests and the demo never
need real credentials. Set ``SHIPPING_PROVIDER=http`` together with
``SHIPPING_API_URL`` to talk to a documented carrier REST API instead.

A carrier outage must never break checkout or a seller's fulfilment: callers
catch ``ShipmentError`` and carry on with the last known status.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10

# Carrier statuses translated onto the order statuses the store understands.
CARRIER_STATUSES = {
    "shipped": "shipped",
    "in_transit": "shipped",
    "out_for_delivery": "out_for_delivery",
    "delivered": "delivered",
}


class ShipmentError(Exception):
    """The carrier could not be reached or refused the request. Safe to show."""


@dataclass(frozen=True)
class Shipment:
    reference: str
    carrier: str = ""


def normalise_status(raw):
    """Translate a carrier status into an order status, or ``None`` when unknown."""
    return CARRIER_STATUSES.get(str(raw or "").strip().lower())


class SandboxCarrier:
    """Deterministic carrier for development, tests and the demo."""

    name = "Sandbox Express"

    def create_shipment(self, order):
        return Shipment(reference=f"SBX-SHP-{order.pk:06d}", carrier=self.name)

    def fetch_status(self, reference):
        return {"reference": reference, "status": "shipped"}


class HttpCarrier:
    """A documented REST carrier: ``POST /shipments`` and ``GET /shipments/<ref>``."""

    def _request(self, method, path, payload=None):
        url = f"{settings.SHIPPING_API_URL.rstrip('/')}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if getattr(settings, "SHIPPING_API_KEY", ""):
            headers["Authorization"] = f"Bearer {settings.SHIPPING_API_KEY}"
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode() or "{}")
        except urllib.error.HTTPError as error:
            # Status only: never log the buyer's address or the API key.
            logger.warning("Carrier %s %s answered %s", method, path, error.code)
            raise ShipmentError("The carrier refused the request.") from error
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            logger.warning(
                "Carrier %s %s failed (%s)", method, path, type(error).__name__
            )
            raise ShipmentError("The carrier could not be reached.") from error

    def create_shipment(self, order):
        payload = self._request("POST", "/shipments", {"reference": f"ORDER-{order.pk}"})
        reference = payload.get("tracking_number") or payload.get("reference")
        if not reference:
            raise ShipmentError("The carrier sent an unexpected answer.")
        return Shipment(reference=reference, carrier=payload.get("carrier", ""))

    def fetch_status(self, reference):
        safe = urllib.parse.quote(str(reference), safe="")
        return self._request("GET", f"/shipments/{safe}")


def get_carrier():
    provider = getattr(settings, "SHIPPING_PROVIDER", "sandbox")
    if provider == "sandbox":
        return SandboxCarrier()
    if provider == "http" and getattr(settings, "SHIPPING_API_URL", ""):
        return HttpCarrier()
    raise ShipmentError("Shipping is not configured. Contact the store.")


def create_shipment(order):
    """Ask the carrier for a tracking reference for ``order``."""
    try:
        return get_carrier().create_shipment(order)
    except ShipmentError:
        raise
    except (TypeError, ValueError) as error:
        raise ShipmentError("The carrier could not be reached.") from error


def fetch_status(reference):
    """Ask the carrier for the live status of ``reference``."""
    try:
        return get_carrier().fetch_status(reference)
    except ShipmentError:
        raise
    except (TypeError, ValueError) as error:
        raise ShipmentError("The carrier could not be reached.") from error
