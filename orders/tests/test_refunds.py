from decimal import Decimal

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from catalog.models import Book
from orders.models import Order, OrderItem
from orders.refunds import RefundError, record_refund
from orders.views import build_invoice

ADDRESS = "12 Reading Lane, Bengaluru 560001, India"


class RefundInvoiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.seller = User.objects.create_user(
            "seller@example.com", "Reading2026!", full_name="Asha Books"
        )
        cls.seller.user_permissions.add(
            Permission.objects.get(codename="add_book", content_type__app_label="catalog")
        )
        cls.rival = User.objects.create_user(
            "rival@example.com", "Reading2026!", full_name="Ravi Reads"
        )
        cls.rival.user_permissions.add(
            Permission.objects.get(codename="add_book", content_type__app_label="catalog")
        )
        cls.buyer = User.objects.create_user("buyer@example.com", "Reading2026!")
        cls.admin = User.objects.create_superuser("admin@example.com", "pw")

    def setUp(self):
        self.book = Book.objects.create(
            title="Clean Code",
            author="Robert Martin",
            isbn="9780132350884",
            price=Decimal("500.00"),
            stock=10,
            seller=self.seller,
            status=Book.Status.APPROVED,
        )
        self.other = Book.objects.create(
            title="Refactoring",
            author="Martin Fowler",
            isbn="9780261103344",
            price=Decimal("250.00"),
            stock=10,
            seller=self.rival,
            status=Book.Status.APPROVED,
        )
        self.client.force_login(self.buyer)

    def make_order(self, items, total=None):
        order = Order.objects.create(
            user=self.buyer,
            status=Order.Status.DELIVERED,
            total=Decimal("0.00"),
            shipping_address=ADDRESS,
        )
        for book, quantity in items:
            OrderItem.objects.create(
                order=order, book=book, quantity=quantity, unit_price=book.price
            )
        if total is None:
            total = sum((book.price * qty for book, qty in items), Decimal("0.00"))
        order.total = total
        order.save(update_fields=["total"])
        return order

    # --- partial refunds (FR-13_IT03) ---
    def test_partial_refund_reduces_the_invoice_net_total(self):
        order = self.make_order([(self.book, 2)], total=Decimal("1000.00"))
        record_refund(order, Decimal("200.00"), reason="One copy damaged", by=self.admin)

        invoice = build_invoice(order)
        self.assertEqual(invoice["total"], Decimal("1000.00"))
        self.assertEqual(invoice["refunded_total"], Decimal("200.00"))
        self.assertEqual(invoice["net_total"], Decimal("800.00"))

    def test_invoice_page_shows_the_net_payable_amount(self):
        order = self.make_order([(self.book, 2)], total=Decimal("1000.00"))
        record_refund(order, Decimal("200.00"), reason="One copy damaged")
        response = self.client.get(reverse("invoice_view", args=[order.pk]))
        self.assertContains(response, "Net payable")
        self.assertContains(response, "800.00")

    def test_refund_cannot_exceed_the_order_total(self):
        order = self.make_order([(self.book, 1)], total=Decimal("500.00"))
        with self.assertRaisesMessage(RefundError, "cannot exceed the order total"):
            record_refund(order, Decimal("600.00"))
        self.assertEqual(build_invoice(order)["refunded_total"], Decimal("0.00"))

    def test_refunds_accumulate_until_the_total_is_reached(self):
        order = self.make_order([(self.book, 1)], total=Decimal("500.00"))
        record_refund(order, Decimal("100.00"))
        record_refund(order, Decimal("400.00"))
        self.assertEqual(build_invoice(order)["net_total"], Decimal("0.00"))
        with self.assertRaises(RefundError):
            record_refund(order, Decimal("0.01"))

    def test_refund_must_be_positive(self):
        order = self.make_order([(self.book, 1)], total=Decimal("500.00"))
        with self.assertRaisesMessage(RefundError, "more than zero"):
            record_refund(order, Decimal("0"))

    # --- per-seller itemisation (FR-13_ST02) ---
    def test_multi_seller_order_is_itemised_per_seller(self):
        order = self.make_order([(self.book, 1), (self.other, 2)])
        invoice = build_invoice(order)
        self.assertEqual(len(invoice["sellers"]), 2)
        totals = {group["name"]: group["subtotal"] for group in invoice["sellers"]}
        self.assertEqual(totals["Asha Books"], Decimal("500.00"))
        self.assertEqual(totals["Ravi Reads"], Decimal("500.00"))
        self.assertEqual(sum(totals.values()), invoice["subtotal"])

    def test_single_seller_order_has_one_group(self):
        order = self.make_order([(self.book, 3)])
        invoice = build_invoice(order)
        self.assertEqual(len(invoice["sellers"]), 1)
        self.assertEqual(invoice["sellers"][0]["subtotal"], Decimal("1500.00"))

    def test_invoice_page_lists_both_sellers(self):
        order = self.make_order([(self.book, 1), (self.other, 1)])
        response = self.client.get(reverse("invoice_view", args=[order.pk]))
        self.assertContains(response, "Asha Books")
        self.assertContains(response, "Ravi Reads")
