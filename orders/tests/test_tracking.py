from decimal import Decimal

from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from catalog.models import Book
from orders.models import Order, OrderItem
from orders.tracking import tracking_steps
from reviews.services import has_delivered_purchase

PLACED, SHIPPED, OUT, DELIVERED = "Placed", "Shipped", "Out for delivery", "Delivered"


class OrderTrackingTests(TestCase):
    def setUp(self):
        permission = Permission.objects.get(codename="add_book", content_type__app_label="catalog")
        self.seller = User.objects.create_user("seller@example.com", "Reading2026!")
        self.rival = User.objects.create_user("rival@example.com", "Reading2026!")
        for user in (self.seller, self.rival):
            user.user_permissions.add(permission)
        self.buyer = User.objects.create_user("buyer@example.com", "Reading2026!")
        self.other = User.objects.create_user("other@example.com", "Reading2026!")
        self.mine = self.make_book("Clean Code", "9780132350884", self.seller)
        self.theirs = self.make_book("The Hobbit", "9780261103344", self.rival)

    def make_book(self, title, isbn, seller):
        return Book.objects.create(
            title=title, author="Author", isbn=isbn, price=Decimal("100"), stock=9,
            seller=seller, status=Book.Status.APPROVED,
        )

    def make_order(self, status=Order.Status.PAID, books=None, user=None):
        order = Order.objects.create(
            user=user or self.buyer, total=Decimal("100"), status=status, shipping_address="12 Main Road",
        )
        for book in books or [self.mine]:
            OrderItem.objects.create(order=order, book=book, quantity=1, unit_price=Decimal("100"))
        return order

    def states(self, order):
        return [(step["label"], step["state"]) for step in tracking_steps(order)]

    # --- the steps ---
    def test_a_placed_or_paid_order_is_at_the_first_step(self):
        for status in (Order.Status.PENDING, Order.Status.PAID):
            with self.subTest(status=status):
                self.assertEqual(
                    self.states(self.make_order(status)),
                    [(PLACED, "current"), (SHIPPED, "upcoming"), (OUT, "upcoming"), (DELIVERED, "upcoming")],
                )

    def test_a_shipped_order_has_placed_done(self):
        self.assertEqual(
            self.states(self.make_order(Order.Status.SHIPPED)),
            [(PLACED, "done"), (SHIPPED, "current"), (OUT, "upcoming"), (DELIVERED, "upcoming")],
        )

    def test_an_order_out_for_delivery(self):
        self.assertEqual(
            self.states(self.make_order(Order.Status.OUT_FOR_DELIVERY)),
            [(PLACED, "done"), (SHIPPED, "done"), (OUT, "current"), (DELIVERED, "upcoming")],
        )

    def test_a_delivered_order_has_every_step_done(self):
        self.assertEqual(
            self.states(self.make_order(Order.Status.DELIVERED)),
            [(PLACED, "done"), (SHIPPED, "done"), (OUT, "done"), (DELIVERED, "done")],
        )

    def test_a_cancelled_order_has_no_steps(self):
        self.assertEqual(tracking_steps(self.make_order(Order.Status.CANCELLED)), [])

    # --- the buyer's order page ---
    def test_the_order_page_shows_the_tracker_and_current_step(self):
        self.client.force_login(self.buyer)
        order = self.make_order(Order.Status.OUT_FOR_DELIVERY)
        response = self.client.get(reverse("order_detail", args=[order.pk]))
        for label in (PLACED, SHIPPED, OUT, DELIVERED):
            self.assertContains(response, label)
        self.assertContains(response, 'aria-current="step"', count=1)
        self.assertContains(response, "tracker-current")
        self.assertEqual(len(response.context["tracking"]), 4)

    def test_a_cancelled_order_page_says_so(self):
        self.client.force_login(self.buyer)
        order = self.make_order(Order.Status.CANCELLED)
        response = self.client.get(reverse("order_detail", args=[order.pk]))
        self.assertContains(response, "This order was cancelled")
        self.assertNotContains(response, "tracker")
        self.assertNotContains(response, "invoice is available once")

    def test_buyers_only_see_their_own_orders(self):
        order = self.make_order(Order.Status.SHIPPED)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("order_detail", args=[order.pk])).status_code, 404)

    def test_the_order_page_needs_login(self):
        order = self.make_order()
        url = reverse("order_detail", args=[order.pk])
        self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")

    def test_the_invoice_stays_available_out_for_delivery(self):
        self.client.force_login(self.buyer)
        order = self.make_order(Order.Status.OUT_FOR_DELIVERY)
        self.assertContains(self.client.get(reverse("order_detail", args=[order.pk])), "View invoice")
        self.assertEqual(self.client.get(reverse("invoice_view", args=[order.pk])).status_code, 200)

    # --- the seller moves the order along ---
    def seller_post(self, name, order, user=None, client=None):
        client = client or self.client
        client.force_login(user or self.seller)
        return client.post(reverse(name, args=[order.pk]))

    def test_the_seller_takes_an_order_through_every_step_and_the_buyer_sees_it(self):
        order = self.make_order(Order.Status.PAID)
        buyer = Client()
        buyer.force_login(self.buyer)
        page = reverse("order_detail", args=[order.pk])
        for action, label in (
            ("seller_order_ship", SHIPPED),
            ("seller_order_out_for_delivery", OUT),
            ("seller_order_deliver", DELIVERED),
        ):
            with self.subTest(action=action):
                self.seller_post(action, order)
                self.assertContains(buyer.get(page), f"<h1>{label}.</h1>", html=False)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DELIVERED)

    def test_out_for_delivery_only_follows_shipped(self):
        for status in (Order.Status.PAID, Order.Status.OUT_FOR_DELIVERY, Order.Status.DELIVERED, Order.Status.CANCELLED):
            with self.subTest(status=status):
                order = self.make_order(status)
                self.seller_post("seller_order_out_for_delivery", order)
                order.refresh_from_db()
                self.assertEqual(order.status, status)

    def test_delivered_follows_out_for_delivery_and_still_shipped(self):
        for status in (Order.Status.OUT_FOR_DELIVERY, Order.Status.SHIPPED):
            with self.subTest(status=status):
                order = self.make_order(status)
                self.seller_post("seller_order_deliver", order)
                order.refresh_from_db()
                self.assertEqual(order.status, Order.Status.DELIVERED)

    def test_other_states_cannot_be_marked_delivered(self):
        for status in (Order.Status.PAID, Order.Status.DELIVERED, Order.Status.CANCELLED):
            with self.subTest(status=status):
                order = self.make_order(status)
                self.seller_post("seller_order_deliver", order)
                order.refresh_from_db()
                self.assertEqual(order.status, status)

    def test_shared_orders_cannot_be_updated_by_one_seller(self):
        order = self.make_order(Order.Status.SHIPPED, books=[self.mine, self.theirs])
        self.seller_post("seller_order_out_for_delivery", order)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SHIPPED)

    def test_other_sellers_cannot_update_the_order(self):
        order = self.make_order(Order.Status.SHIPPED)
        self.assertEqual(self.seller_post("seller_order_out_for_delivery", order, user=self.rival).status_code, 404)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SHIPPED)

    def test_the_new_action_needs_post_csrf_and_the_seller_permission(self):
        order = self.make_order(Order.Status.SHIPPED)
        url = reverse("seller_order_out_for_delivery", args=[order.pk])
        self.client.force_login(self.seller)
        self.assertEqual(self.client.get(url).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.seller)
        self.assertEqual(strict.post(url).status_code, 403)
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.post(url).status_code, 403)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SHIPPED)

    def test_the_seller_page_offers_the_right_button_for_each_status(self):
        self.client.force_login(self.seller)
        expected = {
            Order.Status.PAID: ["Mark as shipped"],
            Order.Status.SHIPPED: ["Mark as out for delivery", "Mark as delivered"],
            Order.Status.OUT_FOR_DELIVERY: ["Mark as delivered"],
        }
        for status, buttons in expected.items():
            with self.subTest(status=status):
                order = self.make_order(status)
                page = self.client.get(reverse("seller_order_detail", args=[order.pk]))
                for button in buttons:
                    self.assertContains(page, button)
        order = self.make_order(Order.Status.OUT_FOR_DELIVERY)
        page = self.client.get(reverse("seller_order_detail", args=[order.pk]))
        self.assertNotContains(page, "Mark as out for delivery")
        self.assertNotContains(page, "Mark as shipped")

    def test_sellers_still_see_orders_that_are_out_for_delivery(self):
        order = self.make_order(Order.Status.OUT_FOR_DELIVERY)
        self.client.force_login(self.seller)
        self.assertContains(self.client.get(reverse("seller_orders")), f"#{order.pk}")

    def test_reviews_still_wait_for_delivery(self):
        self.make_order(Order.Status.OUT_FOR_DELIVERY)
        self.assertFalse(has_delivered_purchase(self.buyer, self.mine))
        self.make_order(Order.Status.DELIVERED)
        self.assertTrue(has_delivered_purchase(self.buyer, self.mine))
