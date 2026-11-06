from decimal import Decimal

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from catalog.models import Book
from orders.models import Order, OrderItem

ADDRESS = "12 Reading Lane, Bengaluru 560001, India"


class BulkShipTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        add_book = Permission.objects.get(
            codename="add_book", content_type__app_label="catalog"
        )
        cls.seller = User.objects.create_user("seller@example.com", "Reading2026!")
        cls.seller.user_permissions.add(add_book)
        cls.rival = User.objects.create_user("rival@example.com", "Reading2026!")
        cls.rival.user_permissions.add(add_book)
        cls.buyer = User.objects.create_user("buyer@example.com", "Reading2026!")
        cls.bystander = User.objects.create_user("bystander@example.com", "Reading2026!")

    def setUp(self):
        self.mine = Book.objects.create(
            title="Mine",
            author="A",
            isbn="9780132350884",
            price=Decimal("100.00"),
            stock=10,
            seller=self.seller,
            status=Book.Status.APPROVED,
        )
        self.theirs = Book.objects.create(
            title="Theirs",
            author="B",
            isbn="9780261103344",
            price=Decimal("100.00"),
            stock=10,
            seller=self.rival,
            status=Book.Status.APPROVED,
        )
        self.client.force_login(self.seller)

    def make_order(self, books=None, status=Order.Status.PAID, user=None):
        order = Order.objects.create(
            user=user or self.buyer,
            status=status,
            total=Decimal("0.00"),
            shipping_address=ADDRESS,
        )
        for book in books if books is not None else [self.mine]:
            OrderItem.objects.create(
                order=order, book=book, quantity=1, unit_price=book.price
            )
        return order

    def bulk(self, orders):
        return self.client.post(
            reverse("seller_orders_bulk_ship"),
            {"orders": [order.pk for order in orders]},
            follow=True,
        )

    def test_several_paid_orders_are_shipped_together(self):
        orders = [self.make_order() for _ in range(5)]
        response = self.bulk(orders)
        self.assertContains(response, "5 order(s) marked as shipped.")
        for order in orders:
            order.refresh_from_db()
            self.assertEqual(order.status, Order.Status.SHIPPED)

    def test_one_unshippable_order_leaves_the_batch_untouched(self):
        ready = [self.make_order() for _ in range(4)]
        pending = self.make_order(status=Order.Status.PENDING)
        response = self.bulk(ready + [pending])
        self.assertContains(response, "Nothing was shipped.")
        for order in ready:
            order.refresh_from_db()
            self.assertEqual(order.status, Order.Status.PAID)
        pending.refresh_from_db()
        self.assertEqual(pending.status, Order.Status.PENDING)

    def test_an_order_shared_with_another_seller_blocks_the_batch(self):
        ready = self.make_order()
        shared = self.make_order(books=[self.mine, self.theirs])
        response = self.bulk([ready, shared])
        self.assertContains(response, "Nothing was shipped.")
        ready.refresh_from_db()
        self.assertEqual(ready.status, Order.Status.PAID)

    def test_another_sellers_order_cannot_be_shipped(self):
        theirs = self.make_order(books=[self.theirs])
        response = self.bulk([theirs])
        self.assertContains(response, "not yours")
        theirs.refresh_from_db()
        self.assertEqual(theirs.status, Order.Status.PAID)

    def test_empty_selection_reports_an_error(self):
        response = self.client.post(reverse("seller_orders_bulk_ship"), follow=True)
        self.assertContains(response, "Select at least one order")

    def test_get_is_not_allowed(self):
        self.assertEqual(
            self.client.get(reverse("seller_orders_bulk_ship")).status_code, 405
        )

    def test_needs_csrf(self):
        from django.test import Client

        order = self.make_order()
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.seller)
        response = strict.post(
            reverse("seller_orders_bulk_ship"), {"orders": [order.pk]}
        )
        self.assertEqual(response.status_code, 403)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    def test_a_buyer_is_refused(self):
        order = self.make_order()
        self.client.force_login(self.bystander)
        response = self.client.post(
            reverse("seller_orders_bulk_ship"), {"orders": [order.pk]}
        )
        self.assertEqual(response.status_code, 403)

    def test_only_shippable_orders_get_a_checkbox(self):
        self.make_order()
        self.make_order(status=Order.Status.PENDING)
        page = self.client.get(reverse("seller_orders")).content.decode()
        self.assertEqual(page.count('name="orders"'), 1)
