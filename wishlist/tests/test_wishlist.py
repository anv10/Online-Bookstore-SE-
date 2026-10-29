from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from cart.models import Cart, CartItem
from catalog.models import Book
from wishlist.models import WishlistItem


class WishlistTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user("seller@example.com", "pw", full_name="Seller")
        self.user = User.objects.create_user("buyer@example.com", "pw")
        self.other = User.objects.create_user("other@example.com", "pw")
        self.book = Book.objects.create(
            title="Clean Code", author="Robert C. Martin", isbn="9780132350884",
            price=Decimal("799.00"), stock=3, seller=self.seller, status=Book.Status.APPROVED,
        )
        self.client.force_login(self.user)

    def add(self, book=None):
        return self.client.post(reverse("wishlist_add", args=[(book or self.book).pk]))

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("wishlist")).status_code, 302)
        self.assertEqual(self.add().status_code, 302)
        self.assertEqual(WishlistItem.objects.count(), 0)

    def test_add_book(self):
        response = self.add()
        self.assertRedirects(response, reverse("book_detail", args=[self.book.pk]))
        self.assertTrue(WishlistItem.objects.filter(user=self.user, book=self.book).exists())

    def test_add_twice_keeps_one_row(self):
        self.add()
        self.add()
        self.assertEqual(WishlistItem.objects.count(), 1)

    def test_cannot_add_unapproved_book(self):
        self.book.status = Book.Status.PENDING
        self.book.save()
        self.assertEqual(self.add().status_code, 404)
        self.assertEqual(WishlistItem.objects.count(), 0)

    def test_page_shows_price_and_availability(self):
        self.add()
        response = self.client.get(reverse("wishlist"))
        self.assertContains(response, "Clean Code")
        self.assertContains(response, "799.00")
        self.assertContains(response, "In stock (3 available)")

    def test_page_shows_out_of_stock(self):
        self.add()
        self.book.stock = 0
        self.book.save()
        response = self.client.get(reverse("wishlist"))
        self.assertContains(response, "Not available")
        self.assertNotContains(response, "Move to cart")

    def test_empty_page(self):
        self.assertContains(self.client.get(reverse("wishlist")), "Your wishlist is empty.")

    def test_only_own_items_listed(self):
        WishlistItem.objects.create(user=self.other, book=self.book)
        self.assertContains(self.client.get(reverse("wishlist")), "Your wishlist is empty.")

    def test_remove(self):
        self.add()
        item = WishlistItem.objects.get()
        self.client.post(reverse("wishlist_remove", args=[item.pk]))
        self.assertEqual(WishlistItem.objects.count(), 0)

    def test_cannot_remove_someone_elses_item(self):
        item = WishlistItem.objects.create(user=self.other, book=self.book)
        self.assertEqual(self.client.post(reverse("wishlist_remove", args=[item.pk])).status_code, 404)
        self.assertEqual(WishlistItem.objects.count(), 1)

    def test_move_to_cart(self):
        self.add()
        item = WishlistItem.objects.get()
        response = self.client.post(reverse("wishlist_to_cart", args=[item.pk]))
        self.assertRedirects(response, reverse("cart"))
        self.assertEqual(CartItem.objects.get(cart__user=self.user, book=self.book).quantity, 1)
        self.assertEqual(WishlistItem.objects.count(), 0)

    def test_move_to_cart_adds_to_existing_line(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, book=self.book, quantity=1)
        item = WishlistItem.objects.create(user=self.user, book=self.book)
        self.client.post(reverse("wishlist_to_cart", args=[item.pk]))
        self.assertEqual(CartItem.objects.get(cart=cart).quantity, 2)

    def test_move_to_cart_does_not_pass_stock(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, book=self.book, quantity=3)
        item = WishlistItem.objects.create(user=self.user, book=self.book)
        response = self.client.post(reverse("wishlist_to_cart", args=[item.pk]))
        self.assertRedirects(response, reverse("wishlist"))
        self.assertEqual(CartItem.objects.get(cart=cart).quantity, 3)
        self.assertEqual(WishlistItem.objects.count(), 1)

    def test_cannot_move_out_of_stock_book(self):
        item = WishlistItem.objects.create(user=self.user, book=self.book)
        self.book.stock = 0
        self.book.save()
        self.client.post(reverse("wishlist_to_cart", args=[item.pk]))
        self.assertEqual(CartItem.objects.count(), 0)
        self.assertEqual(WishlistItem.objects.count(), 1)

    def test_cannot_move_someone_elses_item(self):
        item = WishlistItem.objects.create(user=self.other, book=self.book)
        self.assertEqual(self.client.post(reverse("wishlist_to_cart", args=[item.pk])).status_code, 404)

    def test_detail_page_has_wishlist_button(self):
        self.assertContains(self.client.get(reverse("book_detail", args=[self.book.pk])), "Add to wishlist")

    def test_detail_page_shows_saved_state(self):
        self.add()
        response = self.client.get(reverse("book_detail", args=[self.book.pk]))
        self.assertContains(response, "In your wishlist")
        self.assertNotContains(response, "Add to wishlist")

    def test_str(self):
        item = WishlistItem.objects.create(user=self.user, book=self.book)
        self.assertEqual(str(item), f"{self.user.pk}: {self.book.pk}")
