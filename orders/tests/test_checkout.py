from decimal import Decimal

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from cart.models import Cart, CartItem
from catalog.models import Book
from orders.models import Order, OrderItem

ADDRESS = "12 Reading Lane, Bengaluru 560001, India"
CARD = {"card_number": "4242 4242 4242 4242", "card_expiry": "12/34", "card_cvc": "123"}
DECLINED_CARD = "4000 0000 0000 0002"


class CheckoutTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user("seller@example.com", "Reading2026!")
        self.buyer = User.objects.create_user("buyer@example.com", "Reading2026!")
        self.other = User.objects.create_user("other@example.com", "Reading2026!")
        self.book = self.make_book("Clean Code", "9780132350884", "400.00", 5)
        self.second = self.make_book("The Hobbit", "9780261103344", "100.00", 2)
        self.client.force_login(self.buyer)

    def make_book(self, title, isbn, price, stock, **extra):
        values = {
            "title": title,
            "author": "Author",
            "isbn": isbn,
            "price": Decimal(price),
            "stock": stock,
            "seller": self.seller,
            "status": Book.Status.APPROVED,
        }
        values.update(extra)
        return Book.objects.create(**values)

    def add_to_cart(self, book=None, quantity=1, user=None):
        cart, _ = Cart.objects.get_or_create(user=user or self.buyer)
        return CartItem.objects.create(cart=cart, book=book or self.book, quantity=quantity)

    def payload(self, **overrides):
        data = {"shipping_address": ADDRESS, **CARD}
        data.update(overrides)
        return data

    def post(self, **overrides):
        return self.client.post(reverse("checkout"), self.payload(**overrides))

    # --- the checkout page ---
    def test_checkout_shows_items_quantities_address_and_total(self):
        self.add_to_cart(self.book, 1)
        self.add_to_cart(self.second, 2)
        response = self.client.get(reverse("checkout"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Clean Code")
        self.assertContains(response, "The Hobbit")
        self.assertContains(response, '<textarea name="shipping_address"')
        self.assertContains(response, "₹600.00")
        self.assertContains(response, "₹30.00")
        self.assertContains(response, "₹50.00")
        self.assertContains(response, "₹680.00")
        self.assertEqual(response.context["summary"]["total"], Decimal("680.00"))

    def test_cart_page_links_to_checkout(self):
        self.add_to_cart()
        self.assertContains(self.client.get(reverse("cart")), reverse("checkout"))

    def test_checkout_requires_login(self):
        self.client.logout()
        self.assertRedirects(
            self.client.get(reverse("checkout")), f"{reverse('login')}?next={reverse('checkout')}"
        )

    def test_empty_cart_cannot_be_checked_out(self):
        response = self.client.get(reverse("checkout"))
        self.assertRedirects(response, reverse("cart"))
        self.assertContains(self.client.get(reverse("cart")), "Your cart is empty")
        self.assertFalse(Order.objects.exists())

    def test_get_does_not_create_an_order(self):
        self.add_to_cart()
        self.client.get(reverse("checkout"))
        self.assertFalse(Order.objects.exists())

    def test_shipping_address_is_prefilled_from_the_last_order(self):
        self.add_to_cart()
        self.post()
        self.client.post(reverse("cart_add", args=[self.second.pk]))
        response = self.client.get(reverse("checkout"))
        self.assertContains(response, ADDRESS)

    # --- validation ---
    def test_address_is_required(self):
        self.add_to_cart()
        response = self.post(shipping_address="")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Shipping address is required.")
        self.assertFalse(Order.objects.exists())
        self.assertEqual(CartItem.objects.filter(cart__user=self.buyer).count(), 1)

    def test_whitespace_address_is_rejected(self):
        self.add_to_cart()
        response = self.post(shipping_address="   ")
        self.assertContains(response, "Shipping address is required.")
        self.assertFalse(Order.objects.exists())

    def test_invalid_card_number_is_rejected(self):
        self.add_to_cart()
        for bad in ("1234", "4242 4242 4242 4241", "abcd efgh", ""):
            with self.subTest(card_number=bad):
                response = self.post(card_number=bad)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Invalid card number.")
        self.assertFalse(Order.objects.exists())
        self.book.refresh_from_db()
        self.assertEqual(self.book.stock, 5)

    def test_card_details_are_not_echoed_back_after_a_failed_submission(self):
        self.add_to_cart()
        response = self.post(card_number="4242 4242 4242 4241", card_cvc="987")
        self.assertNotContains(response, "4242 4242 4242 4241")
        self.assertNotContains(response, "987")

    def test_invalid_expiry_is_rejected(self):
        self.add_to_cart()
        for bad in ("", "2030", "13/30", "12/20", "aa/bb"):
            with self.subTest(card_expiry=bad):
                self.assertContains(self.post(card_expiry=bad), "Invalid expiry date.")
        self.assertFalse(Order.objects.exists())

    def test_invalid_security_code_is_rejected(self):
        self.add_to_cart()
        for bad in ("", "12", "12345", "abc"):
            with self.subTest(card_cvc=bad):
                self.assertContains(self.post(card_cvc=bad), "Invalid security code.")
        self.assertFalse(Order.objects.exists())

    def test_checkout_requires_a_csrf_token(self):
        self.add_to_cart()
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.buyer)
        self.assertEqual(strict.post(reverse("checkout"), self.payload()).status_code, 403)
        self.assertFalse(Order.objects.exists())

    # --- totals (FR-5_UT03) ---
    @override_settings(CHECKOUT_TAX_RATE=Decimal("0.05"), CHECKOUT_SHIPPING_FLAT=Decimal("50.00"))
    def test_total_is_subtotal_plus_tax_and_shipping(self):
        book = self.make_book("Dune", "9780441013593", "500.00", 3)
        self.add_to_cart(book)
        response = self.client.get(reverse("checkout"))
        summary = response.context["summary"]
        self.assertEqual(summary["subtotal"], Decimal("500.00"))
        self.assertEqual(summary["tax"], Decimal("25.00"))
        self.assertEqual(summary["shipping"], Decimal("50.00"))
        self.assertEqual(summary["total"], Decimal("575.00"))
        self.post()
        self.assertEqual(Order.objects.get().total, Decimal("575.00"))

    # --- successful payment (FR-5_IT01, FR-5_IT03, FR-5_ST01) ---
    def test_successful_payment_creates_a_paid_order_and_clears_the_cart(self):
        self.add_to_cart(self.book, 2)
        self.add_to_cart(self.second, 1)
        response = self.post()
        order = Order.objects.get()
        self.assertRedirects(response, reverse("order_confirmation", args=[order.pk]))
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.user, self.buyer)
        self.assertEqual(order.total, Decimal("995.00"))
        self.assertEqual(order.shipping_address, ADDRESS)
        self.assertEqual(order.items.count(), 2)
        item = order.items.get(book=self.book)
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.unit_price, Decimal("400.00"))
        self.assertFalse(CartItem.objects.filter(cart__user=self.buyer).exists())

    def test_confirmation_page_shows_order_id_and_total(self):
        self.add_to_cart()
        self.post()
        order = Order.objects.get()
        response = self.client.get(reverse("order_confirmation", args=[order.pk]))
        self.assertContains(response, f"Order #{order.pk}")
        self.assertContains(response, "₹470.00")
        self.assertContains(response, "Clean Code")
        self.assertContains(response, ADDRESS)

    def test_stock_is_decremented_after_payment(self):
        book = self.make_book("Sapiens", "9780099590088", "300.00", 10)
        self.add_to_cart(book, 1)
        self.post()
        book.refresh_from_db()
        self.assertEqual(book.stock, 9)

    def test_card_details_are_never_stored(self):
        self.add_to_cart()
        response = self.post()
        order = Order.objects.get()
        stored = " ".join(str(value) for value in order.__dict__.values())
        stored += " ".join(str(value) for item in order.items.all() for value in item.__dict__.values())
        for sensitive in ("4242", CARD["card_cvc"], "12/34"):
            self.assertNotIn(sensitive, stored)
        confirmation = self.client.get(response["Location"])
        self.assertNotContains(confirmation, "4242")

    # --- declined payment (FR-5_IT02) ---
    def test_declined_card_creates_no_order_and_keeps_the_cart(self):
        self.add_to_cart()
        response = self.post(card_number=DECLINED_CARD)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "declined")
        self.assertFalse(Order.objects.exists())
        self.assertEqual(CartItem.objects.filter(cart__user=self.buyer).count(), 1)
        self.book.refresh_from_db()
        self.assertEqual(self.book.stock, 5)

    # --- availability (FR-5_ST02) ---
    def test_item_that_went_out_of_stock_blocks_checkout(self):
        self.add_to_cart()
        self.book.stock = 0
        self.book.save()
        response = self.client.post(reverse("checkout"), self.payload(), follow=True)
        self.assertContains(response, "need attention before you can check out")
        self.assertContains(response, "No longer available")
        self.assertFalse(Order.objects.exists())

    def test_quantity_above_stock_blocks_checkout(self):
        self.add_to_cart(quantity=3)
        self.book.stock = 2
        self.book.save()
        response = self.client.post(reverse("checkout"), self.payload(), follow=True)
        self.assertContains(response, "need attention before you can check out")
        self.assertContains(response, "Only 2 left")
        self.assertFalse(Order.objects.exists())

    def test_unavailable_listing_blocks_checkout(self):
        self.add_to_cart()
        self.book.status = Book.Status.SUSPENDED
        self.book.save()
        response = self.client.post(reverse("checkout"), self.payload(), follow=True)
        self.assertContains(response, "need attention before you can check out")
        self.assertFalse(Order.objects.exists())

    def test_second_buyer_of_the_last_copy_is_told_it_sold_out(self):
        last_copy = self.make_book("Rare Book", "9780000000011", "900.00", 1)
        self.add_to_cart(last_copy)
        self.post()
        another = User.objects.create_user("second@example.com", "Reading2026!")
        self.add_to_cart(last_copy, user=another)
        self.client.force_login(another)
        response = self.post()
        self.assertRedirects(response, reverse("cart"))
        self.assertFalse(Order.objects.filter(user=another).exists())
        self.assertEqual(Order.objects.count(), 1)
        last_copy.refresh_from_db()
        self.assertEqual(last_copy.stock, 0)

    # --- failures and privacy ---
    @override_settings(PAYMENT_GATEWAY="unconfigured")
    def test_misconfigured_gateway_shows_an_error_instead_of_crashing(self):
        self.add_to_cart()
        response = self.client.post(reverse("checkout"), self.payload(), follow=True)
        self.assertContains(response, "Payments are not configured")
        self.assertFalse(Order.objects.exists())

    def test_confirmation_is_private_to_the_buyer(self):
        self.add_to_cart()
        self.post()
        order = Order.objects.get()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("order_confirmation", args=[order.pk])).status_code, 404)

    def test_confirmation_requires_login(self):
        self.add_to_cart()
        self.post()
        order = Order.objects.get()
        self.client.logout()
        self.assertRedirects(
            self.client.get(reverse("order_confirmation", args=[order.pk])),
            f"{reverse('login')}?next={reverse('order_confirmation', args=[order.pk])}",
        )

    def test_order_items_are_immutable_snapshots_of_the_price(self):
        self.add_to_cart()
        self.post()
        self.book.price = Decimal("999.00")
        self.book.save()
        item = OrderItem.objects.get()
        self.assertEqual(item.unit_price, Decimal("400.00"))
        self.assertEqual(Order.objects.get().total, Decimal("470.00"))
