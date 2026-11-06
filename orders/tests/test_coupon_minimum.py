from decimal import Decimal

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from cart.models import Cart, CartItem
from catalog.models import Book
from orders import coupons, payments
from orders.checkout import place_order
from orders.models import Coupon, Order

ADDRESS = "12 Reading Lane, Bengaluru 560001, India"
CARD = payments.CardDetails("4242424242424242", "12/34", "123")


class CouponMinimumTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.seller = User.objects.create_user("seller@example.com", "Reading2026!")
        cls.seller.user_permissions.add(
            Permission.objects.get(codename="add_book", content_type__app_label="catalog")
        )
        cls.buyer = User.objects.create_user("buyer@example.com", "Reading2026!")

    def setUp(self):
        self.book = Book.objects.create(
            title="Cheap",
            author="A",
            isbn="9780132350884",
            price=Decimal("300.00"),
            stock=10,
            seller=self.seller,
            status=Book.Status.APPROVED,
        )
        cart, _ = Cart.objects.get_or_create(user=self.buyer)
        CartItem.objects.create(cart=cart, book=self.book, quantity=1)
        self.client.force_login(self.buyer)

    def make_coupon(self, minimum="500.00", code="SAVE10"):
        return Coupon.objects.create(
            code=code,
            kind=Coupon.Kind.PERCENT,
            value=Decimal("10.00"),
            min_order_total=None if minimum is None else Decimal(minimum),
        )

    def summary(self):
        return self.client.get(reverse("checkout")).context["summary"]

    def test_coupon_below_the_minimum_is_refused(self):
        self.make_coupon()  # cart is 300.00, minimum 500.00
        response = self.client.post(reverse("apply_coupon"), {"code": "SAVE10"}, follow=True)
        self.assertContains(response, "Minimum order value of ₹500.00 required.")
        self.assertEqual(self.summary()["discount"], Decimal("0"))

    def test_coupon_at_or_above_the_minimum_is_applied(self):
        self.make_coupon(minimum="300.00")
        self.client.post(reverse("apply_coupon"), {"code": "SAVE10"})
        self.assertEqual(self.summary()["discount"], Decimal("30.00"))

    def test_summary_reports_the_minimum_problem(self):
        self.make_coupon()
        session = self.client.session
        session["coupon_code"] = "SAVE10"
        session.save()
        summary = self.summary()
        self.assertEqual(summary["coupon_problem"], "Minimum order value of ₹500.00 required.")
        self.assertEqual(summary["discount"], Decimal("0"))

    def test_place_order_refuses_below_the_minimum(self):
        self.make_coupon()
        with self.assertRaisesMessage(coupons.CouponError, "Minimum order value"):
            place_order(
                self.buyer,
                ADDRESS,
                CARD,
                gateway=payments.SandboxGateway(),
                coupon_code="SAVE10",
            )
        self.assertFalse(Order.objects.exists())

    def test_place_order_applies_a_qualifying_coupon(self):
        self.make_coupon(minimum="100.00")
        order = place_order(
            self.buyer,
            ADDRESS,
            CARD,
            gateway=payments.SandboxGateway(),
            coupon_code="SAVE10",
        )
        self.assertEqual(order.discount, Decimal("30.00"))
        self.assertEqual(order.coupon_code, "SAVE10")

    def test_a_coupon_without_a_minimum_still_applies(self):
        self.make_coupon(minimum=None, code="ANY")
        self.client.post(reverse("apply_coupon"), {"code": "ANY"})
        self.assertEqual(self.summary()["discount"], Decimal("30.00"))
