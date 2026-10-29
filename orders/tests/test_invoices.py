from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from catalog.models import Book
from orders.models import Order, OrderItem


class InvoiceTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user("seller@example.com", "Reading2026!")
        self.buyer = User.objects.create_user("buyer@example.com", "Reading2026!", full_name="Asha Rao")
        self.other = User.objects.create_user("other@example.com", "Reading2026!")
        self.book = self.make_book("Clean Code", "9780132350884", "799.50")
        self.second = self.make_book("The Hobbit", "9780261103344", "400")
        self.order = self.make_order(total="1999.00", status=Order.Status.PAID)
        self.client.force_login(self.buyer)

    def make_book(self, title, isbn, price):
        return Book.objects.create(
            title=title, author="Author", isbn=isbn, price=Decimal(price), stock=5,
            seller=self.seller, status=Book.Status.APPROVED,
        )

    def make_order(self, total, status, user=None, address="12 Main Road\nBengaluru"):
        order = Order.objects.create(user=user or self.buyer, total=Decimal(total), status=status, shipping_address=address)
        OrderItem.objects.create(order=order, book=self.book, quantity=2, unit_price=Decimal("799.50"))
        OrderItem.objects.create(order=order, book=self.second, quantity=1, unit_price=Decimal("400"))
        return order

    def invoice_url(self, order=None):
        return reverse("invoice_view", args=[(order or self.order).pk])

    # --- order pages ---
    def test_order_list_shows_only_own_orders(self):
        self.make_order("10.00", Order.Status.PENDING, user=self.other)
        response = self.client.get(reverse("order_list"))
        self.assertContains(response, f"#{self.order.pk}")
        self.assertEqual(len(response.context["orders"]), 1)

    def test_empty_order_list_message(self):
        self.client.force_login(self.other)
        self.assertContains(self.client.get(reverse("order_list")), "No orders yet")

    def test_order_page_links_to_invoice_when_paid(self):
        response = self.client.get(reverse("order_detail", args=[self.order.pk]))
        self.assertContains(response, "Clean Code")
        self.assertContains(response, self.invoice_url())

    def test_order_page_has_no_invoice_link_before_payment(self):
        pending = self.make_order("1999.00", Order.Status.PENDING)
        response = self.client.get(reverse("order_detail", args=[pending.pk]))
        self.assertNotContains(response, self.invoice_url(pending))
        self.assertContains(response, "available once the order is paid")

    def test_orders_are_private(self):
        theirs = self.make_order("1999.00", Order.Status.PAID, user=self.other)
        self.assertEqual(self.client.get(reverse("order_detail", args=[theirs.pk])).status_code, 404)

    def test_nav_links_to_orders(self):
        self.assertContains(self.client.get(reverse("catalog")), reverse("order_list"))

    # --- invoice content ---
    def test_invoice_lists_order_date_items_prices_and_total(self):
        response = self.client.get(self.invoice_url())
        self.assertEqual(response.status_code, 200)
        for text in (
            f"INV-{self.order.pk:06d}", f"#{self.order.pk}", self.order.created_at.strftime("%-d %b %Y"),
            "Asha Rao", "Clean Code", "The Hobbit", "₹799.50", "₹1599.00", "₹400.00", "₹1999.00",
            "12 Main Road", "Bengaluru", "Discounts", "Taxes and charges",
        ):
            self.assertContains(response, text)

    def test_invoice_adds_up_when_total_matches_items(self):
        invoice = self.client.get(self.invoice_url()).context["invoice"]
        self.assertEqual(invoice["subtotal"], Decimal("1999.00"))
        self.assertEqual(invoice["discounts"], Decimal("0"))
        self.assertEqual(invoice["taxes"], Decimal("0"))

    def test_total_below_items_is_a_discount(self):
        self.order.total = Decimal("1799.00")
        self.order.save()
        invoice = self.client.get(self.invoice_url()).context["invoice"]
        self.assertEqual((invoice["discounts"], invoice["taxes"]), (Decimal("200.00"), Decimal("0")))
        self.assertEqual(invoice["subtotal"] - invoice["discounts"] + invoice["taxes"], invoice["total"])

    def test_total_above_items_is_taxes_and_charges(self):
        self.order.total = Decimal("2099.00")
        self.order.save()
        invoice = self.client.get(self.invoice_url()).context["invoice"]
        self.assertEqual((invoice["discounts"], invoice["taxes"]), (Decimal("0"), Decimal("100.00")))
        self.assertEqual(invoice["subtotal"] - invoice["discounts"] + invoice["taxes"], invoice["total"])

    def test_invoice_keeps_the_price_paid_after_the_book_price_changes(self):
        self.book.price = Decimal("1.00")
        self.book.save()
        self.assertContains(self.client.get(self.invoice_url()), "₹799.50")

    def test_invoice_still_available_after_the_listing_is_removed(self):
        self.book.status = Book.Status.REMOVED
        self.book.save()
        self.assertContains(self.client.get(self.invoice_url()), "Clean Code")

    def test_shipped_orders_have_an_invoice(self):
        self.order.status = Order.Status.SHIPPED
        self.order.save()
        self.assertEqual(self.client.get(self.invoice_url()).status_code, 200)

    def test_no_invoice_before_payment_or_after_cancellation(self):
        for status in (Order.Status.PENDING, Order.Status.CANCELLED):
            with self.subTest(status=status):
                order = self.make_order("1999.00", status)
                self.assertEqual(self.client.get(self.invoice_url(order)).status_code, 404)
                self.assertEqual(self.client.get(reverse("invoice_download", args=[order.pk])).status_code, 404)

    def test_invoice_content_is_escaped(self):
        self.order.shipping_address = "<script>alert(1)</script>"
        self.order.save()
        response = self.client.get(self.invoice_url())
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")

    # --- download ---
    def test_invoice_can_be_downloaded(self):
        response = self.client.get(reverse("invoice_download", args=[self.order.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(f"invoice-INV-{self.order.pk:06d}.html", response["Content-Disposition"])
        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
        for text in ("Clean Code", "₹1999.00", "<!doctype html>"):
            self.assertContains(response, text)

    def test_invoice_page_offers_the_download(self):
        self.assertContains(self.client.get(self.invoice_url()), reverse("invoice_download", args=[self.order.pk]))

    # --- access ---
    def test_other_buyers_cannot_see_or_download_the_invoice(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.invoice_url()).status_code, 404)
        self.assertEqual(self.client.get(reverse("invoice_download", args=[self.order.pk])).status_code, 404)

    def test_login_is_required(self):
        self.client.logout()
        for name, args in (
            ("order_list", []),
            ("order_detail", [self.order.pk]),
            ("invoice_view", [self.order.pk]),
            ("invoice_download", [self.order.pk]),
        ):
            with self.subTest(name=name):
                url = reverse(name, args=args)
                self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")

    def test_unknown_order_is_not_found(self):
        self.assertEqual(self.client.get(reverse("order_detail", args=[999999])).status_code, 404)
