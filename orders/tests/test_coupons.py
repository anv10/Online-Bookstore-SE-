from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from cart.models import Cart, CartItem
from catalog.models import Book
from orders import checkout as checkout_service
from orders import coupons, stripe_gateway
from orders.models import Coupon, Order, PendingPayment

ADDRESS = "12 Reading Lane, Bengaluru 560001, India"
CARD = {"card_number": "4242 4242 4242 4242", "card_expiry": "12/34", "card_cvc": "123"}


class CouponTests(TestCase):
    """A 400.00 book: tax 5% and flat shipping 50.00, so the total without a coupon is 470.00."""

    def setUp(self):
        self.seller = User.objects.create_user("seller@example.com", "Reading2026!")
        self.buyer = User.objects.create_user("buyer@example.com", "Reading2026!")
        self.book = Book.objects.create(
            title="Clean Code",
            author="Author",
            isbn="9780132350884",
            price=Decimal("400.00"),
            stock=5,
            seller=self.seller,
            status=Book.Status.APPROVED,
        )
        cart = Cart.objects.create(user=self.buyer)
        CartItem.objects.create(cart=cart, book=self.book, quantity=1)
        self.client.force_login(self.buyer)

    def make_coupon(self, code="SAVE10", kind=Coupon.Kind.PERCENT, value="10", **extra):
        return Coupon.objects.create(code=code, kind=kind, value=Decimal(value), **extra)

    def apply(self, code):
        return self.client.post(reverse("apply_coupon"), {"code": code}, follow=True)

    def pay(self):
        return self.client.post(reverse("checkout"), {"shipping_address": ADDRESS, **CARD})

    # --- model and rules ---
    def test_code_is_stored_upper_case_and_trimmed(self):
        self.assertEqual(self.make_coupon(code="  welcome10 ").code, "WELCOME10")
        self.assertEqual(str(Coupon.objects.get()), "WELCOME10")

    def test_percentage_over_100_is_rejected(self):
        coupon = Coupon(code="BAD", kind=Coupon.Kind.PERCENT, value=Decimal("150"))
        with self.assertRaises(ValidationError):
            coupon.full_clean()

    def test_discount_never_exceeds_subtotal(self):
        coupon = self.make_coupon(code="BIG", kind=Coupon.Kind.FIXED, value="1000")
        self.assertEqual(coupons.discount_for(coupon, Decimal("400.00")), Decimal("400.00"))
        self.assertEqual(coupons.discount_for(None, Decimal("400.00")), Decimal("0.00"))

    def test_totals_are_taxed_on_the_discounted_subtotal(self):
        totals = checkout_service.totals_for(Decimal("400.00"), Decimal("100.00"))
        self.assertEqual(totals["tax"], Decimal("15.00"))
        self.assertEqual(totals["total"], Decimal("365.00"))

    # --- applying a coupon ---
    def test_valid_percent_coupon_reduces_the_total(self):
        self.make_coupon()
        response = self.apply("save10")
        self.assertContains(response, "Coupon SAVE10 applied.")
        summary = response.context["summary"]
        self.assertEqual(summary["discount"], Decimal("40.00"))
        self.assertEqual(summary["total"], Decimal("428.00"))
        self.assertContains(response, "−₹40.00")

    def test_valid_fixed_coupon_reduces_the_total(self):
        self.make_coupon(code="FLAT100", kind=Coupon.Kind.FIXED, value="100")
        summary = self.apply("FLAT100").context["summary"]
        self.assertEqual(summary["discount"], Decimal("100.00"))
        self.assertEqual(summary["total"], Decimal("365.00"))

    def test_discount_larger_than_subtotal_cannot_make_total_negative(self):
        self.make_coupon(code="HUGE", kind=Coupon.Kind.FIXED, value="5000")
        summary = self.apply("HUGE").context["summary"]
        self.assertEqual(summary["discount"], Decimal("400.00"))
        self.assertEqual(summary["total"], Decimal("50.00"))

    def test_unknown_code_shows_an_error_and_changes_nothing(self):
        response = self.apply("NOPE")
        self.assertContains(response, "That coupon code is not valid.")
        self.assertEqual(response.context["summary"]["total"], Decimal("470.00"))
        self.assertNotIn(coupons.SESSION_KEY, self.client.session)

    def test_blank_code_shows_an_error(self):
        self.assertContains(self.apply("   "), "Enter a coupon code.")

    def test_expired_coupon_is_rejected(self):
        self.make_coupon(code="OLD", expires_at=timezone.now() - timedelta(days=1))
        response = self.apply("OLD")
        self.assertContains(response, "That coupon has expired.")
        self.assertEqual(response.context["summary"]["total"], Decimal("470.00"))

    def test_inactive_coupon_is_rejected(self):
        self.make_coupon(code="OFF", active=False)
        self.assertContains(self.apply("OFF"), "That coupon code is not valid.")

    def test_coupon_at_its_usage_limit_is_rejected(self):
        self.make_coupon(code="ONCE", max_uses=1, times_used=1)
        self.assertContains(self.apply("ONCE"), "reached its usage limit")

    def test_applying_a_second_coupon_replaces_the_first(self):
        self.make_coupon()
        self.make_coupon(code="FLAT100", kind=Coupon.Kind.FIXED, value="100")
        self.apply("SAVE10")
        summary = self.apply("FLAT100").context["summary"]
        self.assertEqual(summary["coupon"].code, "FLAT100")
        self.assertEqual(summary["discount"], Decimal("100.00"))

    def test_remove_coupon_restores_the_full_total(self):
        self.make_coupon()
        self.apply("SAVE10")
        response = self.client.post(reverse("remove_coupon"), follow=True)
        self.assertEqual(response.context["summary"]["total"], Decimal("470.00"))
        self.assertNotIn(coupons.SESSION_KEY, self.client.session)

    def test_coupon_that_goes_bad_after_applying_is_dropped_with_a_message(self):
        coupon = self.make_coupon()
        self.apply("SAVE10")
        Coupon.objects.filter(pk=coupon.pk).update(active=False)
        response = self.client.get(reverse("checkout"))
        self.assertContains(response, "That coupon code is not valid.")
        self.assertEqual(response.context["summary"]["total"], Decimal("470.00"))

    def test_coupon_endpoints_need_login_and_post(self):
        self.assertEqual(self.client.get(reverse("apply_coupon")).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.post(reverse("apply_coupon"), {"code": "X"}).status_code, 302)

    # --- placing the order ---
    def test_paid_order_stores_the_discount_and_counts_one_use(self):
        coupon = self.make_coupon(max_uses=3)
        self.apply("SAVE10")
        response = self.pay()
        order = Order.objects.get()
        self.assertRedirects(response, reverse("order_confirmation", kwargs={"pk": order.pk}))
        self.assertEqual(order.total, Decimal("428.00"))
        self.assertEqual(order.discount, Decimal("40.00"))
        self.assertEqual(order.coupon_code, "SAVE10")
        coupon.refresh_from_db()
        self.assertEqual(coupon.times_used, 1)
        self.assertNotIn(coupons.SESSION_KEY, self.client.session)

    def test_order_without_a_coupon_has_no_discount(self):
        self.pay()
        order = Order.objects.get()
        self.assertEqual(order.total, Decimal("470.00"))
        self.assertEqual(order.discount, Decimal("0.00"))
        self.assertEqual(order.coupon_code, "")

    def test_declined_card_does_not_use_up_the_coupon(self):
        coupon = self.make_coupon()
        self.apply("SAVE10")
        self.client.post(
            reverse("checkout"), {"shipping_address": ADDRESS, **CARD, "card_number": "4000 0000 0000 0002"}
        )
        coupon.refresh_from_db()
        self.assertEqual(coupon.times_used, 0)
        self.assertFalse(Order.objects.exists())

    def test_coupon_used_up_before_payment_blocks_the_order(self):
        coupon = self.make_coupon(max_uses=1)
        self.apply("SAVE10")
        Coupon.objects.filter(pk=coupon.pk).update(times_used=1)
        response = self.pay()
        self.assertRedirects(response, reverse("checkout"))
        self.assertFalse(Order.objects.exists())

    def test_confirmation_order_detail_and_invoice_show_the_discount(self):
        self.make_coupon()
        self.apply("SAVE10")
        self.pay()
        order = Order.objects.get()
        for name in ("order_confirmation", "order_detail", "invoice_view"):
            key = "pk" if name == "order_confirmation" else "order_id"
            page = self.client.get(reverse(name, kwargs={key: order.pk}))
            self.assertContains(page, "−₹40.00", msg_prefix=name)
            self.assertContains(page, "₹428.00", msg_prefix=name)

    # --- hosted (Stripe) payment ---
    def test_hosted_payment_records_the_discount_and_sends_it_to_stripe(self):
        self.make_coupon()
        self.apply("SAVE10")
        sent = {}

        def fake_session(pending_id, email, items, success_url, cancel_url, discount=None):
            sent["discount"] = discount
            return {"id": "cs_test_1", "url": "https://pay.example/1"}

        with patch.object(stripe_gateway, "create_checkout_session", side_effect=fake_session):
            url = checkout_service.start_hosted_payment(
                self.buyer, ADDRESS, "https://x/ok", "https://x/cancel", coupon_code="SAVE10"
            )
        self.assertEqual(url, "https://pay.example/1")
        self.assertEqual(sent["discount"], ("SAVE10", 4000))
        pending = PendingPayment.objects.get()
        self.assertEqual(pending.discount, Decimal("40.00"))
        self.assertEqual(pending.coupon_code, "SAVE10")
        self.assertEqual(pending.total, Decimal("428.00"))

    def test_stripe_session_gets_a_coupon_for_the_discount(self):
        calls = []

        def fake_request(method, path, params=None):
            calls.append((path, params))
            if path == "/coupons":
                return {"id": "co_1"}
            return {"id": "cs_1", "url": "https://pay.example/1"}

        with patch.object(stripe_gateway, "_request", side_effect=fake_request):
            stripe_gateway.create_checkout_session(
                1, "a@b.c", [("Book", 40000, 1)], "https://x/ok", "https://x/cancel", discount=("SAVE10", 4000)
            )
        self.assertEqual(calls[0][0], "/coupons")
        self.assertEqual(calls[0][1]["amount_off"], "4000")
        self.assertEqual(calls[1][1]["discounts[0][coupon]"], "co_1")

    def test_stripe_session_without_a_discount_makes_no_coupon(self):
        calls = []

        def fake_request(method, path, params=None):
            calls.append(path)
            return {"id": "cs_1", "url": "https://pay.example/1"}

        with patch.object(stripe_gateway, "_request", side_effect=fake_request):
            stripe_gateway.create_checkout_session(1, "a@b.c", [("Book", 40000, 1)], "https://x/ok", "https://x/cancel")
        self.assertEqual(calls, ["/checkout/sessions"])

    def test_stripe_coupon_without_an_id_is_an_error(self):
        with patch.object(stripe_gateway, "_request", return_value={}):
            with self.assertRaises(stripe_gateway.StripeError):
                stripe_gateway.create_checkout_session(
                    1, "a@b.c", [("Book", 40000, 1)], "https://x/ok", "https://x/cancel", discount=("SAVE10", 4000)
                )
