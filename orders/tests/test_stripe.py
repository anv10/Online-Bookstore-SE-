import io
import json
import urllib.error
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from cart.models import Cart, CartItem
from catalog.models import Book
from orders import stripe_gateway
from orders.models import Order, PendingPayment

ADDRESS = "12 Reading Lane, Bengaluru 560001, India"
STRIPE = {"PAYMENT_GATEWAY": "stripe", "STRIPE_SECRET_KEY": "sk_test_example"}


def fake_response(payload):
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode()
    response.__enter__.return_value = response
    return response


@override_settings(**STRIPE)
class StripeClientTests(SimpleTestCase):
    def test_amounts_are_sent_in_paise(self):
        self.assertEqual(stripe_gateway.to_minor_units(Decimal("575.00")), 57500)
        self.assertEqual(stripe_gateway.to_minor_units(Decimal("0.05")), 5)

    def test_create_session_posts_line_items_with_the_secret_key(self):
        with patch("urllib.request.urlopen", return_value=fake_response({"id": "cs_test_1", "url": "https://pay.example/1"})) as opened:
            session = stripe_gateway.create_checkout_session(
                7, "buyer@example.com", [("Clean Code", 40000, 2), ("Shipping", 5000, 1)], "https://shop/ok", "https://shop/no"
            )
        request = opened.call_args.args[0]
        body = request.data.decode()
        self.assertEqual(session["url"], "https://pay.example/1")
        self.assertEqual(request.full_url, "https://api.stripe.com/v1/checkout/sessions")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer sk_test_example")
        self.assertIn("line_items%5B0%5D%5Bprice_data%5D%5Bunit_amount%5D=40000", body)
        self.assertIn("line_items%5B1%5D%5Bprice_data%5D%5Bunit_amount%5D=5000", body)
        self.assertIn("client_reference_id=7", body)
        self.assertNotIn("card", body.lower())

    @override_settings(STRIPE_SECRET_KEY="")
    def test_missing_key_means_payments_are_not_configured(self):
        with patch("urllib.request.urlopen") as opened:
            with self.assertRaisesMessage(stripe_gateway.StripeError, "not configured"):
                stripe_gateway.retrieve_session("cs_test_1")
        opened.assert_not_called()

    def test_http_error_becomes_a_safe_message_without_the_key(self):
        error = urllib.error.HTTPError("https://api.stripe.com", 401, "Unauthorized", {}, io.BytesIO(b"{}"))
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(stripe_gateway.StripeError) as caught:
                stripe_gateway.retrieve_session("cs_test_1")
        self.assertNotIn("sk_test", str(caught.exception))

    def test_network_failure_becomes_a_safe_message(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            with self.assertRaisesMessage(stripe_gateway.StripeError, "could not be reached"):
                stripe_gateway.retrieve_session("cs_test_1")

    def test_session_id_is_validated_before_a_request_is_made(self):
        with patch("urllib.request.urlopen") as opened:
            for bad in ("", "../refunds", "cs_test_1/../x", "pi_123"):
                with self.assertRaises(stripe_gateway.StripeError):
                    stripe_gateway.retrieve_session(bad)
        opened.assert_not_called()

    def test_unexpected_session_answer_is_rejected(self):
        with patch("urllib.request.urlopen", return_value=fake_response({"id": "cs_test_1"})):
            with self.assertRaises(stripe_gateway.StripeError):
                stripe_gateway.create_checkout_session(1, "", [("Book", 100, 1)], "https://a", "https://b")

    def test_refund_needs_a_payment_intent(self):
        with self.assertRaises(stripe_gateway.StripeError):
            stripe_gateway.refund("")


@override_settings(**STRIPE)
class HostedCheckoutTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user("seller@example.com", "Reading2026!")
        self.buyer = User.objects.create_user("buyer@example.com", "Reading2026!")
        self.other = User.objects.create_user("other@example.com", "Reading2026!")
        self.book = self.make_book("Clean Code", "9780132350884", "400.00", 5)
        self.second = self.make_book("The Hobbit", "9780261103344", "100.00", 2)
        self.client.force_login(self.buyer)

    def make_book(self, title, isbn, price, stock):
        return Book.objects.create(
            title=title, author="Author", isbn=isbn, price=Decimal(price), stock=stock,
            seller=self.seller, status=Book.Status.APPROVED,
        )

    def add_to_cart(self, book=None, quantity=1, user=None):
        cart, _ = Cart.objects.get_or_create(user=user or self.buyer)
        return CartItem.objects.create(cart=cart, book=book or self.book, quantity=quantity)

    def start(self):
        with patch("orders.stripe_gateway.create_checkout_session", return_value={"id": "cs_test_abc", "url": "https://pay.example/abc"}) as created:
            response = self.client.post(reverse("checkout"), {"shipping_address": ADDRESS})
        return response, created

    def paid_session(self, pending=None, **overrides):
        pending = pending or PendingPayment.objects.get()
        session = {
            "id": pending.session_id,
            "payment_status": "paid",
            "amount_total": int(pending.total * 100),
            "currency": "inr",
            "client_reference_id": str(pending.pk),
            "payment_intent": "pi_test_1",
        }
        session.update(overrides)
        return session

    def complete(self, session, session_id="cs_test_abc"):
        with patch("orders.stripe_gateway.retrieve_session", return_value=session):
            return self.client.get(reverse("checkout_complete"), {"session_id": session_id})

    # --- starting the payment ---
    def test_page_asks_for_the_address_only_and_names_stripe(self):
        self.add_to_cart()
        response = self.client.get(reverse("checkout"))
        self.assertContains(response, '<textarea name="shipping_address"')
        self.assertContains(response, "Stripe")
        for field in ("card_number", "card_expiry", "card_cvc"):
            self.assertNotContains(response, field)

    def test_posting_the_address_sends_the_buyer_to_stripe_without_creating_an_order(self):
        self.add_to_cart(self.book, 1)
        self.add_to_cart(self.second, 2)
        response, created = self.start()
        self.assertRedirects(response, "https://pay.example/abc", fetch_redirect_response=False)
        pending = PendingPayment.objects.get()
        self.assertEqual(pending.session_id, "cs_test_abc")
        self.assertEqual(pending.status, PendingPayment.Status.STARTED)
        self.assertEqual(pending.total, Decimal("680.00"))
        self.assertEqual(pending.shipping_address, ADDRESS)
        self.assertEqual(Order.objects.count(), 0)
        self.book.refresh_from_db()
        self.assertEqual(self.book.stock, 5)
        self.assertEqual(CartItem.objects.count(), 2)
        items = created.call_args.args[2]
        self.assertEqual(sum(amount * quantity for _, amount, quantity in items), 68000)
        self.assertIn(("Tax", 3000, 1), items)
        self.assertIn(("Shipping", 5000, 1), items)
        urls = created.call_args.args[3:]
        self.assertTrue(urls[0].endswith("/checkout/complete/?session_id={CHECKOUT_SESSION_ID}"))
        self.assertTrue(urls[1].endswith(f"/checkout/cancel/?payment={pending.pk}"))

    def test_stripe_being_down_leaves_nothing_behind_and_shows_an_error(self):
        self.add_to_cart()
        with patch("orders.stripe_gateway.create_checkout_session", side_effect=stripe_gateway.StripeError("The payment provider could not be reached.")):
            response = self.client.post(reverse("checkout"), {"shipping_address": ADDRESS})
        self.assertEqual(response.status_code, 502)
        self.assertContains(response, "No money was taken", status_code=502)
        self.assertEqual(PendingPayment.objects.get().status, PendingPayment.Status.FAILED)
        self.assertEqual(Order.objects.count(), 0)

    def test_address_is_still_required(self):
        self.add_to_cart()
        response = self.client.post(reverse("checkout"), {"shipping_address": "  "})
        self.assertContains(response, "Shipping address is required.")
        self.assertEqual(PendingPayment.objects.count(), 0)

    def test_empty_cart_cannot_start_a_payment(self):
        response = self.client.post(reverse("checkout"), {"shipping_address": ADDRESS})
        self.assertRedirects(response, reverse("cart"))
        self.assertEqual(PendingPayment.objects.count(), 0)

    def test_no_card_data_is_kept_anywhere_on_the_payment_record(self):
        names = {field.name for field in PendingPayment._meta.get_fields()}
        self.assertFalse({name for name in names if "card" in name or "cvc" in name or "expiry" in name})

    # --- a successful payment ---
    def test_paid_session_creates_a_paid_order_and_updates_stock_and_cart(self):
        self.add_to_cart(self.book, 2)
        self.start()
        response = self.complete(self.paid_session())
        order = Order.objects.get()
        self.assertRedirects(response, reverse("order_confirmation", args=[order.pk]))
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.total, Decimal("890.00"))
        self.assertEqual(order.shipping_address, ADDRESS)
        item = order.items.get()
        self.assertEqual((item.book, item.quantity, item.unit_price), (self.book, 2, Decimal("400.00")))
        self.book.refresh_from_db()
        self.assertEqual(self.book.stock, 3)
        self.assertEqual(CartItem.objects.count(), 0)
        pending = PendingPayment.objects.get()
        self.assertEqual((pending.status, pending.order), (PendingPayment.Status.COMPLETED, order))

    def test_opening_the_return_link_twice_does_not_create_a_second_order(self):
        self.add_to_cart(self.book, 1)
        self.start()
        session = self.paid_session()
        self.complete(session)
        self.complete(session)
        self.assertEqual(Order.objects.count(), 1)
        self.book.refresh_from_db()
        self.assertEqual(self.book.stock, 4)

    # --- payments that did not go through ---
    def test_unpaid_session_creates_no_order(self):
        self.add_to_cart()
        self.start()
        response = self.complete(self.paid_session(payment_status="unpaid"))
        self.assertRedirects(response, reverse("cart"), fetch_redirect_response=False)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(PendingPayment.objects.get().status, PendingPayment.Status.STARTED)
        self.assertContains(self.client.get(reverse("cart")), "not completed")

    def test_session_for_a_different_amount_is_not_accepted(self):
        self.add_to_cart()
        self.start()
        self.complete(self.paid_session(amount_total=100))
        self.assertEqual(Order.objects.count(), 0)

    def test_session_for_a_different_payment_is_not_accepted(self):
        self.add_to_cart()
        self.start()
        self.complete(self.paid_session(client_reference_id="9999"))
        self.assertEqual(Order.objects.count(), 0)

    def test_someone_elses_session_cannot_be_completed(self):
        self.add_to_cart()
        self.start()
        pending = PendingPayment.objects.get()
        self.client.force_login(self.other)
        response = self.complete(self.paid_session(pending))
        self.assertRedirects(response, reverse("cart"))
        self.assertEqual(Order.objects.count(), 0)

    def test_unknown_session_is_rejected(self):
        response = self.complete({"payment_status": "paid"}, session_id="cs_test_nope")
        self.assertRedirects(response, reverse("cart"))
        self.assertEqual(Order.objects.count(), 0)

    def test_gateway_failure_while_confirming_keeps_the_payment_open_for_a_retry(self):
        self.add_to_cart()
        self.start()
        with patch("orders.stripe_gateway.retrieve_session", side_effect=stripe_gateway.StripeError("down")):
            response = self.client.get(reverse("checkout_complete"), {"session_id": "cs_test_abc"})
        self.assertRedirects(response, reverse("cart"))
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(PendingPayment.objects.get().status, PendingPayment.Status.STARTED)
        self.complete(self.paid_session())
        self.assertEqual(Order.objects.count(), 1)

    # --- cancelling ---
    def test_cancelling_leaves_the_order_unpaid_and_shows_an_error(self):
        self.add_to_cart(self.book, 1)
        self.start()
        pending = PendingPayment.objects.get()
        response = self.client.get(reverse("checkout_cancel"), {"payment": pending.pk}, follow=True)
        self.assertRedirects(response, reverse("checkout"))
        self.assertContains(response, "Payment cancelled")
        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingPayment.Status.CANCELLED)
        self.assertEqual(Order.objects.count(), 0)
        self.book.refresh_from_db()
        self.assertEqual(self.book.stock, 5)
        self.assertEqual(CartItem.objects.count(), 1)

    def test_a_cancelled_payment_cannot_be_completed_later(self):
        self.add_to_cart()
        self.start()
        pending = PendingPayment.objects.get()
        self.client.get(reverse("checkout_cancel"), {"payment": pending.pk})
        self.complete(self.paid_session(pending))
        self.assertEqual(Order.objects.count(), 0)

    def test_nobody_can_cancel_someone_elses_payment(self):
        self.add_to_cart()
        self.start()
        pending = PendingPayment.objects.get()
        self.client.force_login(self.other)
        self.client.get(reverse("checkout_cancel"), {"payment": pending.pk})
        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingPayment.Status.STARTED)

    def test_cancel_ignores_a_bad_payment_id(self):
        response = self.client.get(reverse("checkout_cancel"), {"payment": "abc"})
        self.assertRedirects(response, reverse("checkout"), fetch_redirect_response=False)

    # --- the last copy sells out while the buyer is paying ---
    def test_sold_out_while_paying_refunds_the_buyer_and_creates_no_order(self):
        self.add_to_cart(self.second, 2)
        self.start()
        Book.objects.filter(pk=self.second.pk).update(stock=1)
        with patch("orders.stripe_gateway.refund") as refund:
            response = self.complete(self.paid_session())
        refund.assert_called_once_with("pi_test_1")
        self.assertRedirects(response, reverse("cart"))
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(PendingPayment.objects.get().status, PendingPayment.Status.REFUNDED)
        self.second.refresh_from_db()
        self.assertEqual(self.second.stock, 1)

    def test_failed_refund_is_reported_with_a_reference(self):
        self.add_to_cart(self.second, 2)
        self.start()
        Book.objects.filter(pk=self.second.pk).update(stock=0)
        with patch("orders.stripe_gateway.refund", side_effect=stripe_gateway.StripeError("down")):
            self.complete(self.paid_session())
        pending = PendingPayment.objects.get()
        self.assertEqual(pending.status, PendingPayment.Status.FAILED)
        self.assertContains(self.client.get(reverse("cart")), f"payment #{pending.pk}")
        self.assertEqual(Order.objects.count(), 0)

    # --- access and the default gateway ---
    def test_return_pages_need_a_login(self):
        self.client.logout()
        for name in ("checkout_complete", "checkout_cancel"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 302)

    @override_settings(PAYMENT_GATEWAY="sandbox")
    def test_sandbox_mode_still_shows_the_card_form(self):
        self.add_to_cart()
        response = self.client.get(reverse("checkout"))
        self.assertContains(response, "card_number")
        self.assertNotContains(response, "Stripe")
