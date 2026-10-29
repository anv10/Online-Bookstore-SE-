from decimal import Decimal

from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from catalog.models import Book
from orders.models import Order, OrderItem


class SellerOrderTests(TestCase):
    def setUp(self):
        permission = Permission.objects.get(codename="add_book", content_type__app_label="catalog")
        self.seller = User.objects.create_user("seller@example.com", "Reading2026!")
        self.rival = User.objects.create_user("rival@example.com", "Reading2026!")
        for user in (self.seller, self.rival):
            user.user_permissions.add(permission)
        self.buyer = User.objects.create_user("buyer@example.com", "Reading2026!", full_name="Asha Rao")
        self.mine = self.make_book("Clean Code", "9780132350884", self.seller)
        self.mine_too = self.make_book("Refactoring", "9780201485677", self.seller)
        self.theirs = self.make_book("The Hobbit", "9780261103344", self.rival)
        self.order = self.make_order([(self.mine, 2), (self.mine_too, 1)])
        self.client.force_login(self.seller)

    def make_book(self, title, isbn, seller):
        return Book.objects.create(
            title=title, author="Author", isbn=isbn, price=Decimal("100"), stock=9,
            seller=seller, status=Book.Status.APPROVED,
        )

    def make_order(self, lines, status=Order.Status.PAID, address="12 Main Road\nBengaluru"):
        order = Order.objects.create(user=self.buyer, total=Decimal("0"), status=status, shipping_address=address)
        for book, quantity in lines:
            OrderItem.objects.create(order=order, book=book, quantity=quantity, unit_price=Decimal("100"))
        order.total = sum(Decimal("100") * quantity for _, quantity in lines)
        order.save()
        return order

    def detail_url(self, order=None):
        return reverse("seller_order_detail", args=[(order or self.order).pk])

    def ship_url(self, order=None):
        return reverse("seller_order_ship", args=[(order or self.order).pk])

    # --- list ---
    def test_seller_sees_orders_with_their_books(self):
        response = self.client.get(reverse("seller_orders"))
        self.assertContains(response, f"#{self.order.pk}")
        self.assertContains(response, "Clean Code × 2")
        self.assertContains(response, "₹300")

    def test_seller_does_not_see_other_sellers_orders(self):
        other = self.make_order([(self.theirs, 1)])
        response = self.client.get(reverse("seller_orders"))
        self.assertNotContains(response, f"#{other.pk}")
        self.assertNotContains(response, "The Hobbit")
        self.assertEqual([row["order"] for row in response.context["rows"]], [self.order])

    def test_shared_orders_only_show_the_sellers_own_items_and_total(self):
        shared = self.make_order([(self.mine, 1), (self.theirs, 3)])
        response = self.client.get(reverse("seller_orders"))
        self.assertNotContains(response, "The Hobbit")
        row = next(r for r in response.context["rows"] if r["order"] == shared)
        self.assertEqual(row["total"], Decimal("100"))
        self.assertTrue(row["shared"])

    def test_orders_are_listed_once_even_with_several_of_their_books(self):
        self.assertEqual(len(self.client.get(reverse("seller_orders")).context["rows"]), 1)

    def test_unpaid_orders_are_hidden(self):
        pending = self.make_order([(self.mine, 1)], status=Order.Status.PENDING)
        response = self.client.get(reverse("seller_orders"))
        self.assertNotContains(response, f"#{pending.pk}")
        self.assertEqual(self.client.get(self.detail_url(pending)).status_code, 404)

    def test_paid_shipped_and_cancelled_orders_are_listed(self):
        for status in (Order.Status.SHIPPED, Order.Status.CANCELLED):
            self.make_order([(self.mine, 1)], status=status)
        self.assertEqual(len(self.client.get(reverse("seller_orders")).context["rows"]), 3)

    def test_empty_list_message(self):
        self.client.force_login(self.rival)
        self.assertContains(self.client.get(reverse("seller_orders")), "No orders yet")

    def test_orders_still_show_after_a_listing_was_removed(self):
        self.mine.status = Book.Status.REMOVED
        self.mine.save()
        self.assertContains(self.client.get(reverse("seller_orders")), "Clean Code")

    def test_seller_listings_page_links_to_orders(self):
        self.assertContains(self.client.get(reverse("seller_listings")), reverse("seller_orders"))

    # --- detail ---
    def test_detail_shows_items_and_shipping_address(self):
        response = self.client.get(self.detail_url())
        for text in ("Clean Code", "Refactoring", "12 Main Road", "Bengaluru", "Asha Rao", "Mark as shipped"):
            self.assertContains(response, text)

    def test_detail_does_not_reveal_buyer_contact_details(self):
        response = self.client.get(self.detail_url())
        self.assertNotContains(response, "buyer@example.com")

    def test_other_sellers_cannot_open_the_order(self):
        self.client.force_login(self.rival)
        self.assertEqual(self.client.get(self.detail_url()).status_code, 404)

    def test_detail_escapes_content(self):
        self.order.shipping_address = "<script>alert(1)</script>"
        self.order.save()
        response = self.client.get(self.detail_url())
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")

    def test_unknown_order_is_not_found(self):
        self.assertEqual(self.client.get(reverse("seller_order_detail", args=[999999])).status_code, 404)

    # --- shipping ---
    def test_seller_can_mark_a_paid_order_as_shipped(self):
        response = self.client.post(self.ship_url())
        self.assertRedirects(response, self.detail_url())
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.SHIPPED)
        self.assertNotContains(self.client.get(self.detail_url()), "Mark as shipped")

    def test_shipped_order_cannot_be_shipped_again_or_a_cancelled_one_shipped(self):
        for status in (Order.Status.SHIPPED, Order.Status.CANCELLED):
            with self.subTest(status=status):
                order = self.make_order([(self.mine, 1)], status=status)
                self.client.post(self.ship_url(order))
                order.refresh_from_db()
                self.assertEqual(order.status, status)

    def test_orders_with_other_sellers_books_cannot_be_shipped_here(self):
        shared = self.make_order([(self.mine, 1), (self.theirs, 1)])
        self.client.post(self.ship_url(shared))
        shared.refresh_from_db()
        self.assertEqual(shared.status, Order.Status.PAID)
        page = self.client.get(self.detail_url(shared))
        self.assertContains(page, "other sellers")
        self.assertNotContains(page, "Mark as shipped")

    def test_other_sellers_cannot_ship_the_order(self):
        self.client.force_login(self.rival)
        self.assertEqual(self.client.post(self.ship_url()).status_code, 404)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)

    def test_ship_needs_post_and_csrf(self):
        self.assertEqual(self.client.get(self.ship_url()).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.seller)
        self.assertEqual(strict.post(self.ship_url()).status_code, 403)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)

    def test_shipping_changes_nothing_but_the_status(self):
        total = self.order.total
        self.client.post(self.ship_url())
        self.order.refresh_from_db()
        self.assertEqual((self.order.total, self.order.items.count()), (total, 2))

    # --- delivery ---
    def deliver_url(self, order=None):
        return reverse("seller_order_deliver", args=[(order or self.order).pk])

    def test_seller_can_mark_a_shipped_order_as_delivered(self):
        self.client.post(self.ship_url())
        response = self.client.post(self.deliver_url())
        self.assertRedirects(response, self.detail_url())
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.DELIVERED)
        self.assertContains(self.client.get(self.detail_url()), "Delivered")

    def test_only_shipped_orders_can_be_marked_delivered(self):
        for status in (Order.Status.PAID, Order.Status.DELIVERED, Order.Status.CANCELLED):
            with self.subTest(status=status):
                order = self.make_order([(self.mine, 1)], status=status)
                self.client.post(self.deliver_url(order))
                order.refresh_from_db()
                self.assertEqual(order.status, status)

    def test_other_sellers_cannot_mark_an_order_delivered(self):
        self.client.post(self.ship_url())
        self.client.force_login(self.rival)
        self.assertEqual(self.client.post(self.deliver_url()).status_code, 404)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.SHIPPED)

    def test_deliver_needs_post_and_csrf(self):
        self.client.post(self.ship_url())
        self.assertEqual(self.client.get(self.deliver_url()).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.seller)
        self.assertEqual(strict.post(self.deliver_url()).status_code, 403)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.SHIPPED)

    # --- access ---
    def test_buyers_without_the_seller_permission_get_403(self):
        self.client.force_login(self.buyer)
        for url in (reverse("seller_orders"), self.detail_url()):
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(self.ship_url()).status_code, 403)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)

    def test_anonymous_users_are_sent_to_login(self):
        self.client.logout()
        for url in (reverse("seller_orders"), self.detail_url()):
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")
        self.assertRedirects(self.client.post(self.ship_url()), f"{reverse('login')}?next={self.ship_url()}")
