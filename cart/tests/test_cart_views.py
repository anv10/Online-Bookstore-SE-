from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from cart.models import Cart, CartItem
from catalog.models import Book


class CartViewTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user("seller@example.com", "Reading2026!")
        self.buyer = User.objects.create_user("buyer@example.com", "Reading2026!")
        self.other = User.objects.create_user("other@example.com", "Reading2026!")
        self.book = self.make_book("Clean Code", "9780132350884", "799.50", 5)
        self.second = self.make_book("The Hobbit", "9780261103344", "400", 2)
        self.client.force_login(self.buyer)

    def make_book(self, title, isbn, price, stock, **extra):
        values = dict(
            title=title,
            author="Author",
            isbn=isbn,
            price=Decimal(price),
            stock=stock,
            seller=self.seller,
            status=Book.Status.APPROVED,
        )
        values.update(extra)
        return Book.objects.create(**values)

    def add(self, book=None, quantity=None):
        data = {} if quantity is None else {"quantity": quantity}
        return self.client.post(reverse("cart_add", args=[(book or self.book).pk]), data)

    def quantity_of(self, book=None):
        item = CartItem.objects.filter(cart__user=self.buyer, book=book or self.book).first()
        return item.quantity if item else 0

    # --- add ---
    def test_add_from_details_page_defaults_to_one_copy(self):
        page = self.client.get(reverse("book_detail", args=[self.book.pk]))
        self.assertContains(page, reverse("cart_add", args=[self.book.pk]))
        self.assertRedirects(self.add(), reverse("cart"))
        self.assertEqual(self.quantity_of(), 1)

    def test_add_several_copies_and_adding_again_adds_up(self):
        self.add(quantity=2)
        self.add(quantity=1)
        self.assertEqual(self.quantity_of(), 3)
        self.assertEqual(CartItem.objects.filter(cart__user=self.buyer).count(), 1)

    def test_cannot_add_more_than_stock(self):
        response = self.add(quantity=6)
        self.assertRedirects(response, reverse("book_detail", args=[self.book.pk]))
        self.assertEqual(self.quantity_of(), 0)
        self.assertFalse(CartItem.objects.filter(cart__user=self.buyer).exists())
        self.add(quantity=4)
        response = self.add(quantity=2)
        self.assertEqual(self.quantity_of(), 4)
        self.assertContains(self.client.get(reverse("book_detail", args=[self.book.pk])), "already in your cart")

    def test_out_of_stock_book_cannot_be_added(self):
        self.book.stock = 0
        self.book.save()
        self.add()
        self.assertEqual(self.quantity_of(), 0)

    def test_invalid_quantities_are_rejected(self):
        for bad in ("0", "-1", "abc", "", "1.5"):
            with self.subTest(quantity=bad):
                self.add(quantity=bad)
        self.assertEqual(self.quantity_of(), 0)

    def test_hidden_listings_cannot_be_added(self):
        hidden = [
            self.make_book("Pending", "9780000000011", "10", 3, status=Book.Status.PENDING),
            self.make_book("Removed", "9780000000028", "10", 3, status=Book.Status.REMOVED),
            self.make_book("Suspended", "9780000000035", "10", 3, status=Book.Status.SUSPENDED),
        ]
        inactive = User.objects.create_user("gone@example.com", "Reading2026!", is_active=False)
        hidden.append(self.make_book("Inactive seller", "9780000000042", "10", 3, seller=inactive))
        for book in hidden:
            with self.subTest(title=book.title):
                self.assertEqual(self.add(book).status_code, 404)
        self.assertFalse(CartItem.objects.exists())

    def test_unknown_book_is_not_found(self):
        self.assertEqual(self.client.post(reverse("cart_add", args=[999999])).status_code, 404)

    def test_add_needs_login_post_and_csrf(self):
        add_url = reverse("cart_add", args=[self.book.pk])
        self.assertEqual(self.client.get(add_url).status_code, 405)
        self.client.logout()
        self.assertRedirects(self.client.post(add_url), f"{reverse('login')}?next={add_url}")
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.buyer)
        self.assertEqual(strict.post(add_url).status_code, 403)
        self.assertFalse(CartItem.objects.exists())

    # --- cart page ---
    def test_cart_page_lists_items_with_line_totals_and_total(self):
        self.add(quantity=2)
        self.add(self.second, quantity=1)
        response = self.client.get(reverse("cart"))
        self.assertContains(response, "Clean Code")
        self.assertContains(response, "₹1599.00")
        self.assertContains(response, "₹400.00")
        self.assertContains(response, "₹1999.00")
        self.assertEqual(response.context["total"], Decimal("1999.00"))

    def test_empty_cart_message(self):
        self.assertContains(self.client.get(reverse("cart")), "Your cart is empty")

    def test_cart_page_requires_login(self):
        self.client.logout()
        self.assertRedirects(self.client.get(reverse("cart")), f"{reverse('login')}?next={reverse('cart')}")

    def test_nav_links_to_cart_for_logged_in_users(self):
        self.assertContains(self.client.get(reverse("catalog")), reverse("cart"))

    def test_cart_persists_across_sessions(self):
        self.add(quantity=3)
        self.client.logout()
        fresh = Client()
        self.assertTrue(fresh.login(username="buyer@example.com", password="Reading2026!"))
        self.assertContains(fresh.get(reverse("cart")), "Clean Code")

    def test_carts_are_private_to_each_user(self):
        self.add()
        self.client.force_login(self.other)
        self.assertContains(self.client.get(reverse("cart")), "Your cart is empty")

    def test_unavailable_items_are_flagged_and_left_out_of_the_total(self):
        self.add(quantity=1)
        self.add(self.second, quantity=1)
        self.second.status = Book.Status.REMOVED
        self.second.save()
        response = self.client.get(reverse("cart"))
        self.assertContains(response, "No longer available")
        self.assertEqual(response.context["total"], Decimal("799.50"))

    def test_items_over_current_stock_are_flagged(self):
        self.add(quantity=4)
        self.book.stock = 2
        self.book.save()
        self.assertContains(self.client.get(reverse("cart")), "Only 2 left")

    # --- update and remove ---
    def item(self, book=None):
        return CartItem.objects.get(cart__user=self.buyer, book=book or self.book)

    def test_change_quantity(self):
        self.add()
        response = self.client.post(reverse("cart_update", args=[self.item().pk]), {"quantity": 4})
        self.assertRedirects(response, reverse("cart"))
        self.assertEqual(self.quantity_of(), 4)

    def test_quantity_cannot_exceed_stock_or_be_invalid(self):
        self.add(quantity=2)
        url = reverse("cart_update", args=[self.item().pk])
        for bad in ("6", "0", "-3", "x", ""):
            with self.subTest(quantity=bad):
                self.client.post(url, {"quantity": bad})
        self.assertEqual(self.quantity_of(), 2)

    def test_remove_item(self):
        self.add()
        response = self.client.post(reverse("cart_remove", args=[self.item().pk]))
        self.assertRedirects(response, reverse("cart"))
        self.assertEqual(self.quantity_of(), 0)
        self.assertTrue(Book.objects.filter(pk=self.book.pk).exists())

    def test_cannot_touch_someone_elses_cart_item(self):
        self.add()
        item = self.item()
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse("cart_update", args=[item.pk]), {"quantity": 1}).status_code, 404)
        self.assertEqual(self.client.post(reverse("cart_remove", args=[item.pk])).status_code, 404)
        self.assertEqual(CartItem.objects.get(pk=item.pk).quantity, 1)

    def test_update_and_remove_need_post_and_login(self):
        self.add()
        item = self.item()
        update_url = reverse("cart_update", args=[item.pk])
        remove_url = reverse("cart_remove", args=[item.pk])
        self.assertEqual(self.client.get(update_url).status_code, 405)
        self.assertEqual(self.client.get(remove_url).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.post(update_url, {"quantity": 2}).status_code, 302)
        self.assertEqual(self.client.post(remove_url).status_code, 302)
        self.assertEqual(CartItem.objects.get(pk=item.pk).quantity, 1)

    def test_a_cart_is_created_once_per_user(self):
        self.add()
        self.add(self.second)
        self.client.get(reverse("cart"))
        self.assertEqual(Cart.objects.filter(user=self.buyer).count(), 1)
