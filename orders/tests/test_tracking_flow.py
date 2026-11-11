import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from catalog.models import Book
from orders import logistics, tracking
from orders.models import Order, OrderItem, OrderStatusLog

ADDRESS = "12 Reading Lane, Bengaluru 560001, India"


class TrackingFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.seller = User.objects.create_user("seller@example.com", "Reading2026!")
        cls.seller.user_permissions.add(
            Permission.objects.get(codename="add_book", content_type__app_label="catalog")
        )
        cls.buyer = User.objects.create_user("buyer@example.com", "Reading2026!")

    def setUp(self):
        self.book = Book.objects.create(
            title="Tracked",
            author="A",
            isbn="9780132350884",
            price=Decimal("100.00"),
            stock=10,
            seller=self.seller,
            status=Book.Status.APPROVED,
        )

    def make_order(self, status=Order.Status.PAID, reference=""):
        order = Order.objects.create(
            user=self.buyer,
            status=status,
            total=Decimal("100.00"),
            shipping_address=ADDRESS,
            tracking_reference=reference,
        )
        OrderItem.objects.create(
            order=order, book=self.book, quantity=1, unit_price=self.book.price
        )
        tracking.log_status(order, status, note="Test setup")
        return order

    # --- estimated delivery (FR-9_UT03) ---
    @override_settings(SHIPPING_TRANSIT_DAYS=5)
    def test_estimated_delivery_is_ship_date_plus_transit(self):
        order = self.make_order(status=Order.Status.SHIPPED)
        shipped_at = timezone.now() - timedelta(days=2)
        OrderStatusLog.objects.filter(
            order=order, status=Order.Status.SHIPPED
        ).update(created_at=shipped_at)
        expected = timezone.localtime(shipped_at).date() + timedelta(days=5)
        self.assertEqual(order.estimated_delivery, expected)

    def test_delivered_orders_have_no_estimate(self):
        order = self.make_order(status=Order.Status.DELIVERED)
        self.assertIsNone(order.estimated_delivery)

    # --- live carrier status (FR-9_IT01) ---
    @patch("orders.tracking.logistics.fetch_status")
    def test_tracking_page_applies_the_carrier_status(self, fetch):
        fetch.return_value = {"reference": "SBX-SHP-000001", "status": "out_for_delivery"}
        order = self.make_order(status=Order.Status.SHIPPED, reference="SBX-SHP-000001")
        self.client.force_login(self.buyer)
        response = self.client.get(reverse("order_detail", args=[order.pk]))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.OUT_FOR_DELIVERY)
        self.assertContains(response, "Out for delivery")
        fetch.assert_called_once_with("SBX-SHP-000001")

    # --- carrier webhook (FR-9_IT02) ---
    @override_settings(LOGISTICS_WEBHOOK_SECRET="test-secret")
    def test_webhook_updates_the_order(self):
        order = self.make_order(status=Order.Status.SHIPPED, reference="SBX-SHP-000002")
        body = json.dumps({"reference": "SBX-SHP-000002", "status": "delivered"}).encode()
        signature = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
        response = self.client.post(
            reverse("tracking_webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_CARRIER_SIGNATURE=signature,
        )
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DELIVERED)

    @override_settings(LOGISTICS_WEBHOOK_SECRET="test-secret")
    def test_webhook_rejects_a_bad_signature(self):
        order = self.make_order(reference="SBX-SHP-000003")
        body = json.dumps({"reference": "SBX-SHP-000003", "status": "delivered"}).encode()
        response = self.client.post(
            reverse("tracking_webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_CARRIER_SIGNATURE="not-the-signature",
        )
        self.assertEqual(response.status_code, 403)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    @override_settings(LOGISTICS_WEBHOOK_SECRET="test-secret")
    def test_webhook_rejects_an_unknown_status(self):
        order = self.make_order(reference="SBX-SHP-000004")
        body = json.dumps({"reference": "SBX-SHP-000004", "status": "lost_in_space"}).encode()
        signature = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
        response = self.client.post(
            reverse("tracking_webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_CARRIER_SIGNATURE=signature,
        )
        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    @override_settings(LOGISTICS_WEBHOOK_SECRET="test-secret")
    def test_webhook_unknown_reference_is_not_found(self):
        body = json.dumps({"reference": "NOPE", "status": "delivered"}).encode()
        signature = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
        response = self.client.post(
            reverse("tracking_webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_CARRIER_SIGNATURE=signature,
        )
        self.assertEqual(response.status_code, 404)

    def test_webhook_is_disabled_without_a_secret(self):
        body = json.dumps({"reference": "X", "status": "delivered"}).encode()
        response = self.client.post(
            reverse("tracking_webhook"), data=body, content_type="application/json"
        )
        self.assertEqual(response.status_code, 503)

    # --- timeline from the status log (FR-9_IT03) ---
    def test_timeline_follows_the_status_log_in_order(self):
        order = self.make_order(status=Order.Status.PAID)
        tracking.advance(order, Order.Status.SHIPPED)
        tracking.advance(order, Order.Status.OUT_FOR_DELIVERY)
        tracking.advance(order, Order.Status.DELIVERED)
        order.refresh_from_db()
        labels = [entry["label"] for entry in tracking.status_timeline(order)]
        self.assertEqual(labels, ["Paid", "Shipped", "Out for delivery", "Delivered"])
        self.assertEqual(OrderStatusLog.objects.filter(order=order).count(), 4)

    def test_advance_never_moves_backwards(self):
        order = self.make_order(status=Order.Status.OUT_FOR_DELIVERY)
        self.assertFalse(tracking.advance(order, Order.Status.SHIPPED))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.OUT_FOR_DELIVERY)

    def test_the_page_shows_the_history(self):
        order = self.make_order(status=Order.Status.PAID)
        tracking.advance(order, Order.Status.SHIPPED)
        self.client.force_login(self.buyer)
        response = self.client.get(reverse("order_detail", args=[order.pk]))
        self.assertContains(response, "Order history")
        self.assertContains(response, "Shipped")

    # --- graceful degradation (FR-9_ST02) ---
    @patch(
        "orders.tracking.logistics.fetch_status",
        side_effect=logistics.ShipmentError("down"),
    )
    def test_page_degrades_when_the_carrier_is_down(self, _):
        order = self.make_order(status=Order.Status.SHIPPED, reference="SBX-SHP-000005")
        self.client.force_login(self.buyer)
        response = self.client.get(reverse("order_detail", args=[order.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Live tracking is unavailable")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SHIPPED)

    # --- shipment creation ---
    def test_shipping_records_a_carrier_reference(self):
        order = self.make_order(status=Order.Status.PAID)
        self.client.force_login(self.seller)
        self.client.post(reverse("seller_order_ship", args=[order.pk]))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SHIPPED)
        self.assertTrue(order.tracking_reference.startswith("SBX-SHP-"))
        self.assertTrue(
            OrderStatusLog.objects.filter(
                order=order, status=Order.Status.SHIPPED
            ).exists()
        )

    @patch(
        "orders.seller_views.logistics.create_shipment",
        side_effect=logistics.ShipmentError("down"),
    )
    def test_a_carrier_outage_does_not_block_shipping(self, _):
        order = self.make_order(status=Order.Status.PAID)
        self.client.force_login(self.seller)
        self.client.post(reverse("seller_order_ship", args=[order.pk]))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SHIPPED)
        self.assertEqual(order.tracking_reference, "")
