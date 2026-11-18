"""Security validation suite: one test class per requirement in
Documents/SecurityRequirements_Online_Bookstore (SEC-1 to SEC-39).

Each class name starts with the requirement ID so the run log doubles as the
evidence column of Documents/SecurityValidationReport_Online_Bookstore.docx.
Run just this suite with:

    python manage.py test security -v 2
"""

import io
import logging
import os
import re
import stat
import subprocess
import tempfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.sessions.models import Session
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountAction, PasswordResetOTP, User
from cart.models import Cart, CartItem
from catalog.models import Book, ModerationEvent
from orders.models import Coupon, Order, OrderItem
from reviews.models import Review
from security.models import RateLimitBucket, SecurityEvent
from wishlist.models import WishlistItem

REPO = Path(settings.BASE_DIR)
PASSWORD = "Reading2026!"
ADDRESS = "12 Reading Lane, Bengaluru 560001, India"
CARD_NUMBER = "4242424242424242"
CARD = {"card_number": "4242 4242 4242 4242", "card_expiry": "12/34", "card_cvc": "987"}
Kind = SecurityEvent.Kind


def verify_second_factor(client):
    session = client.session
    session["moderation_verified_until"] = timezone.now().timestamp() + 1800
    session.save()


class Fixtures(TestCase):
    """Buyers, two sellers, a listing each and helpers shared by the requirement tests."""

    def setUp(self):
        self.buyer = User.objects.create_user("buyer@example.com", PASSWORD, phone="+919800000001", full_name="Asha Rao")
        self.other = User.objects.create_user("other@example.com", PASSWORD, phone="+919800000002")
        self.seller = self.make_seller("seller@example.com")
        self.rival = self.make_seller("rival@example.com")
        self.book = self.make_book(self.seller, "Clean Code", "9780132350884", "400.00")
        self.rival_book = self.make_book(self.rival, "The Hobbit", "9780261103344", "100.00")

    def make_seller(self, email):
        user = User.objects.create_user(email, PASSWORD)
        user.user_permissions.add(Permission.objects.get(codename="add_book", content_type__app_label="catalog"))
        return User.objects.get(pk=user.pk)

    def make_admin(self, email="admin@example.com", *codenames):
        user = User.objects.create_user(email, PASSWORD, is_staff=True)
        for app_label, codename in codenames or (("accounts", "change_user"), ("catalog", "change_book")):
            user.user_permissions.add(Permission.objects.get(codename=codename, content_type__app_label=app_label))
        return User.objects.get(pk=user.pk)

    def make_book(self, seller, title, isbn, price, stock=5, **extra):
        return Book.objects.create(
            title=title, author="Author", isbn=isbn, price=Decimal(price), stock=stock,
            seller=seller, status=Book.Status.APPROVED, **extra,
        )

    def add_to_cart(self, user=None, book=None, quantity=1):
        cart, _ = Cart.objects.get_or_create(user=user or self.buyer)
        return CartItem.objects.create(cart=cart, book=book or self.book, quantity=quantity)

    def make_order(self, user=None, book=None, status=Order.Status.PAID, coupon_code=""):
        book = book or self.book
        order = Order.objects.create(
            user=user or self.buyer, status=status, total=book.price, shipping_address=ADDRESS, coupon_code=coupon_code,
        )
        OrderItem.objects.create(order=order, book=book, quantity=1, unit_price=book.price)
        return order

    def login(self, client, user, password=PASSWORD):
        return client.post(reverse("login"), {"username": user.email, "password": password})

    def events(self, kind):
        return SecurityEvent.objects.filter(kind=kind)


# ---------------------------------------------------------------- 3.1 Authentication


class SEC01PasswordPolicyTests(Fixtures):
    """SEC-1: at least 8 characters with a letter and a digit, at registration and at reset."""

    WEAK = ("Ab1", "abcdefghij", "1234567890", "password1")

    def register(self, password, n):
        return self.client.post(reverse("register"), {
            "email": f"new{n}@example.com", "phone": f"+91980000{n:04d}",
            "password": password, "confirm_password": password,
        })

    def test_weak_passwords_are_rejected_at_registration(self):
        for n, password in enumerate(self.WEAK):
            with self.subTest(password=password):
                self.assertEqual(self.register(password, n).status_code, 200)
                self.assertFalse(User.objects.filter(email=f"new{n}@example.com").exists())

    def test_strong_password_is_accepted(self):
        self.register("Bookworm42x", 99)
        self.assertTrue(User.objects.filter(email="new99@example.com").exists())

    def test_weak_passwords_are_rejected_at_reset(self):
        from accounts.forms import SetNewPasswordForm

        for password in self.WEAK:
            with self.subTest(password=password):
                form = SetNewPasswordForm(self.buyer, {"password": password, "confirm_password": password})
                self.assertFalse(form.is_valid())
        self.assertTrue(SetNewPasswordForm(self.buyer, {"password": "Bookworm42x", "confirm_password": "Bookworm42x"}).is_valid())


class SEC02PasswordStorageTests(Fixtures):
    """SEC-2: salted, slow adaptive hashes only."""

    def test_argon2_is_the_hasher_and_hashes_are_salted(self):
        self.assertEqual(settings.PASSWORD_HASHERS[0], "django.contrib.auth.hashers.Argon2PasswordHasher")
        self.buyer.refresh_from_db()
        self.other.refresh_from_db()
        self.assertTrue(self.buyer.password.startswith("argon2$argon2id$"))
        self.assertNotEqual(self.buyer.password, self.other.password)  # same password, different salt
        self.assertNotIn(PASSWORD, self.buyer.password)

    def test_plain_password_is_nowhere_in_the_user_table(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT t::text FROM accounts_user t")
            rows = " ".join(row[0] for row in cursor.fetchall())
        self.assertNotIn(PASSWORD, rows)


class SEC03LockoutTests(Fixtures):
    """SEC-3: three failures show a warning and lock the account for 15 minutes."""

    def test_three_failures_lock_and_warn(self):
        self.assertEqual(settings.LOGIN_MAX_FAILURES, 3)
        self.assertEqual(settings.LOGIN_LOCKOUT_MINUTES, 15)
        for _ in range(2):
            self.assertContains(self.login(self.client, self.buyer, "wrong-pass-1"), "Invalid credentials")
        response = self.login(self.client, self.buyer, "wrong-pass-1")
        self.assertContains(response, "Too many failed sign-in attempts. Please try again in 15 minutes.")
        # Even the right password is refused while the lock lasts.
        self.assertContains(self.login(self.client, self.buyer), "Too many failed sign-in attempts")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.events(Kind.LOCKOUT).count(), 1)

    def test_lock_expires_after_fifteen_minutes(self):
        for _ in range(3):
            self.login(self.client, self.buyer, "wrong-pass-1")
        later = timezone.now() + timedelta(minutes=16)
        with mock.patch("django.utils.timezone.now", return_value=later):
            self.assertEqual(self.login(self.client, self.buyer).status_code, 302)


class SEC04GenericMessagesTests(Fixtures):
    """SEC-4: login and reset replies do not reveal whether an account exists."""

    def test_login_error_is_identical_for_unknown_and_known_accounts(self):
        known = self.client.post(reverse("login"), {"username": "buyer@example.com", "password": "Wrong-pass-9"})
        unknown = self.client.post(reverse("login"), {"username": "nobody@example.com", "password": "Wrong-pass-9"})
        self.assertEqual(known.context["form"].non_field_errors(), unknown.context["form"].non_field_errors())
        self.assertNotContains(unknown, "does not exist")

    def test_lockout_also_applies_to_unknown_identifiers(self):
        for _ in range(3):
            response = self.client.post(reverse("login"), {"username": "ghost@example.com", "password": "Wrong-pass-9"})
        self.assertContains(response, "Too many failed sign-in attempts")

    def test_reset_reply_is_identical_for_unknown_and_known_accounts(self):
        known = self.client.post(reverse("password_reset"), {"identifier": "buyer@example.com"})
        unknown = self.client.post(reverse("password_reset"), {"identifier": "nobody@example.com"})
        self.assertEqual((known.status_code, known["Location"]), (unknown.status_code, unknown["Location"]))
        self.assertEqual(len(mail.outbox), 1)


class SEC05ResetCodeLifetimeTests(Fixtures):
    """SEC-5: reset links and OTPs are single use and expire after 10 minutes."""

    def request_code(self):
        self.client.post(reverse("password_reset"), {"identifier": "buyer@example.com"})
        body = mail.outbox[-1].body
        return re.search(r"code on the reset page: (\d{6})", body).group(1), re.search(r"(http\S+)", body).group(1)

    def enter(self, code):
        return self.client.post(reverse("password_reset_otp"), {"identifier": "buyer@example.com", "code": code})

    def test_otp_is_single_use(self):
        code, _ = self.request_code()
        self.assertRedirects(self.enter(code), reverse("password_reset_otp_set"), fetch_redirect_response=False)
        self.assertContains(self.enter(code), "no longer valid")

    def test_otp_expires_after_ten_minutes(self):
        code, _ = self.request_code()
        otp = PasswordResetOTP.objects.get(user=self.buyer)
        self.assertLessEqual(otp.expires_at - otp.created_at, timedelta(minutes=10, seconds=1))
        PasswordResetOTP.objects.filter(pk=otp.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertContains(self.enter(code), "OTP has expired")

    def test_link_expires_after_ten_minutes_and_is_single_use(self):
        self.assertEqual(settings.PASSWORD_RESET_TIMEOUT, 600)
        _, link = self.request_code()
        with mock.patch("django.contrib.auth.tokens.PasswordResetTokenGenerator._now") as now:
            now.return_value = __import__("datetime").datetime.now() + timedelta(minutes=11)
            self.assertEqual(self.client.get(link).status_code, 400)
        self.client.get(link, follow=True)
        self.client.post(link, {"password": "Bookworm42x", "confirm_password": "Bookworm42x"})
        self.assertEqual(self.client.get(link).status_code, 400)


class SEC06ResetRequestLimitTests(Fixtures):
    """SEC-6: at most 5 reset messages per account per hour, with an unchanged reply."""

    def test_sixth_request_in_an_hour_sends_nothing(self):
        responses = [self.client.post(reverse("password_reset"), {"identifier": "buyer@example.com"}) for _ in range(6)]
        self.assertEqual(len(mail.outbox), 5)
        self.assertEqual({(r.status_code, r["Location"]) for r in responses}, {(302, reverse("password_reset_done"))})
        self.assertEqual(self.events(Kind.RATE_LIMITED).filter(detail="password_reset_account").count(), 1)


# ---------------------------------------------------------------- 3.2 Sessions


class SEC07SessionTokenTests(Fixtures):
    """SEC-7: a fresh random token at login, HttpOnly cookie, Secure when HTTPS is on."""

    def test_login_issues_a_new_random_httponly_session(self):
        self.client.get(reverse("login"))
        self.client.session.save()
        before = self.client.session.session_key
        self.login(self.client, self.buyer)
        after = self.client.session.session_key
        self.assertNotEqual(before, after)
        self.assertGreaterEqual(len(after), 32)
        cookie = self.client.cookies[settings.SESSION_COOKIE_NAME]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")

    @override_settings(SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True)
    def test_cookie_is_secure_when_https_is_enforced(self):
        self.login(self.client, self.buyer)
        self.assertTrue(self.client.cookies[settings.SESSION_COOKIE_NAME]["secure"])


class SEC08SessionExpiryTests(Fixtures):
    """SEC-8: 30 minutes of inactivity ends the session; logout kills it on the server."""

    def test_idle_timeout_is_thirty_minutes_and_renewed_by_activity(self):
        self.assertEqual(settings.SESSION_COOKIE_AGE, 1800)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)

    def test_idle_session_is_rejected(self):
        self.login(self.client, self.buyer)
        key = self.client.session.session_key
        Session.objects.filter(session_key=key).update(expire_date=timezone.now() - timedelta(seconds=1))
        self.assertRedirects(self.client.get(reverse("profile")), f"{reverse('login')}?next={reverse('profile')}")

    def test_logout_deletes_the_server_side_session(self):
        self.login(self.client, self.buyer)
        key = self.client.session.session_key
        stolen = Client()
        stolen.cookies[settings.SESSION_COOKIE_NAME] = key
        self.assertEqual(stolen.get(reverse("profile")).status_code, 200)
        self.client.post(reverse("logout"))
        self.assertFalse(Session.objects.filter(session_key=key).exists())
        self.assertEqual(stolen.get(reverse("profile")).status_code, 302)


class SEC09SessionsEndOnPasswordChangeTests(Fixtures):
    """SEC-9: every session of the user ends when the password is reset (link and OTP paths)."""

    def test_otp_reset_ends_other_sessions(self):
        other_device = Client()
        self.login(other_device, self.buyer)
        self.assertEqual(other_device.get(reverse("profile")).status_code, 200)
        self.client.post(reverse("password_reset"), {"identifier": "buyer@example.com"})
        code = re.search(r"code on the reset page: (\d{6})", mail.outbox[-1].body).group(1)
        self.client.post(reverse("password_reset_otp"), {"identifier": "buyer@example.com", "code": code})
        self.client.post(reverse("password_reset_otp_set"), {"password": "Bookworm42x", "confirm_password": "Bookworm42x"})
        self.assertEqual(other_device.get(reverse("profile")).status_code, 302)

    def test_link_reset_ends_other_sessions(self):
        other_device = Client()
        self.login(other_device, self.buyer)
        self.client.post(reverse("password_reset"), {"identifier": "buyer@example.com"})
        link = re.search(r"(http\S+)", mail.outbox[-1].body).group(1)
        self.client.get(link, follow=True)
        self.client.post(link, {"password": "Bookworm42x", "confirm_password": "Bookworm42x"})
        self.assertEqual(other_device.get(reverse("profile")).status_code, 302)


# ---------------------------------------------------------------- 3.3 Access control


class SEC10RoleBasedAccessTests(Fixtures):
    """SEC-10: roles are enforced on the server for every request, not by hiding links."""

    def test_anonymous_users_are_sent_to_login(self):
        for name, args in (("cart", []), ("checkout", []), ("order_list", []), ("wishlist", []), ("profile", []),
                           ("seller_listings", []), ("listing_add", []), ("seller_orders", []),
                           ("moderation_queue", []), ("user_admin_list", [])):
            with self.subTest(url=name):
                response = self.client.get(reverse(name, args=args))
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response["Location"])

    def test_buyer_cannot_use_seller_or_admin_features_by_typing_the_url(self):
        self.client.force_login(self.buyer)
        for name, args in (("seller_listings", []), ("listing_add", []), ("listing_edit", [self.book.pk]),
                           ("seller_orders", []), ("moderation_queue", []), ("moderation_verify", []),
                           ("user_admin_list", []), ("user_admin_detail", [self.other.pk])):
            with self.subTest(url=name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 403)
        response = self.client.get("/admin/")
        self.assertIn("/admin/login/", response["Location"])
        self.assertTrue(self.events(Kind.AUTHZ_DENIED).exists())


class SEC11BuyerDataIsolationTests(Fixtures):
    """SEC-11: a buyer sees only their own orders, cart and wishlist."""

    def setUp(self):
        super().setUp()
        self.order = self.make_order(user=self.other)
        self.cart_item = self.add_to_cart(user=self.other)
        self.wish = WishlistItem.objects.create(user=self.other, book=self.book)
        self.client.force_login(self.buyer)

    def test_other_buyers_orders_and_invoices_are_not_found(self):
        for name in ("order_detail", "invoice_view", "invoice_download"):
            with self.subTest(url=name):
                self.assertEqual(self.client.get(reverse(name, args=[self.order.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("order_confirmation", args=[self.order.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("order_list")), f"#{self.order.pk}<")
        self.assertTrue(self.events(Kind.AUTHZ_DENIED).filter(detail__contains=f"order {self.order.pk}").exists())

    def test_other_buyers_cart_and_wishlist_cannot_be_changed(self):
        self.assertEqual(self.client.post(reverse("cart_update", args=[self.cart_item.pk]), {"quantity": 3}).status_code, 404)
        self.assertEqual(self.client.post(reverse("cart_remove", args=[self.cart_item.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("wishlist_remove", args=[self.wish.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("wishlist_to_cart", args=[self.wish.pk])).status_code, 404)
        self.cart_item.refresh_from_db()
        self.assertEqual(self.cart_item.quantity, 1)
        self.assertTrue(WishlistItem.objects.filter(pk=self.wish.pk).exists())


class SEC12SellerOwnershipTests(Fixtures):
    """SEC-12: sellers can only change their own listings and orders containing them."""

    def setUp(self):
        super().setUp()
        self.rival_order = self.make_order(book=self.rival_book)
        self.client.force_login(self.seller)

    def test_another_sellers_listing_cannot_be_edited_or_removed(self):
        for name in ("listing_edit", "listing_remove"):
            with self.subTest(url=name):
                self.assertEqual(self.client.post(reverse(name, args=[self.rival_book.pk]), {"title": "Hacked"}).status_code, 404)
        self.rival_book.refresh_from_db()
        self.assertEqual((self.rival_book.title, self.rival_book.status), ("The Hobbit", Book.Status.APPROVED))

    def test_orders_without_my_books_cannot_be_viewed_or_shipped(self):
        self.assertEqual(self.client.get(reverse("seller_order_detail", args=[self.rival_order.pk])).status_code, 404)
        for name in ("seller_order_ship", "seller_order_out_for_delivery", "seller_order_deliver"):
            with self.subTest(url=name):
                self.assertEqual(self.client.post(reverse(name, args=[self.rival_order.pk])).status_code, 404)
        self.rival_order.refresh_from_db()
        self.assertEqual(self.rival_order.status, Order.Status.PAID)


class SEC13AdminActionsTests(Fixtures):
    """SEC-13: only admins approve, suspend or remove; each action records who, what, why and when."""

    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.client.force_login(self.admin)
        verify_second_factor(self.client)

    def test_account_action_is_audited(self):
        self.client.post(reverse("user_admin_detail", args=[self.other.pk]), {"action": "suspend", "reason": "Spam"})
        action = AccountAction.objects.get()
        self.assertEqual((action.admin, action.target, action.reason), (self.admin, self.other, "Spam"))
        self.assertIsNotNone(action.created_at)

    def test_listing_decision_is_audited(self):
        self.client.post(reverse("moderation_decide", args=[self.book.pk]),
                         {"status": "suspended", "expected_status": "approved", "reason": "Counterfeit"})
        event = ModerationEvent.objects.get()
        self.assertEqual((event.admin, event.book, event.reason, event.new_status), (self.admin, self.book, "Counterfeit", "suspended"))
        self.assertIsNotNone(event.created_at)
        self.assertEqual(self.events(Kind.ADMIN_ACTION).count(), 1)

    def test_non_admins_cannot_moderate(self):
        for user in (self.buyer, self.seller):
            self.client.force_login(user)
            verify_second_factor(self.client)
            with self.subTest(user=user.email):
                self.assertEqual(self.client.post(reverse("user_admin_detail", args=[self.other.pk]), {"action": "remove", "reason": "x"}).status_code, 403)
                self.assertEqual(self.client.post(reverse("moderation_decide", args=[self.rival_book.pk]), {"status": "removed", "expected_status": "approved", "reason": "x"}).status_code, 403)
        self.assertFalse(AccountAction.objects.exists())
        self.assertFalse(ModerationEvent.objects.exists())


class SEC14AdminSecondFactorTests(Fixtures):
    """SEC-14: every admin surface needs an emailed one-time code on top of the password."""

    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.admin.is_superuser = True
        self.admin.save()
        self.client.force_login(self.admin)

    def test_all_admin_areas_require_the_second_factor(self):
        for url in ("/admin/", reverse("user_admin_list"), reverse("moderation_queue")):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith(reverse("moderation_verify")))

    def test_emailed_code_unlocks_the_requested_admin_page(self):
        verify = f"{reverse('moderation_verify')}?next=/admin/"
        self.client.post(verify, {"action": "send", "next": "/admin/"})
        code = re.search(r"code is (\d{6})", mail.outbox[-1].body).group(1)
        wrong = "000000" if code != "000000" else "111111"
        self.assertEqual(self.client.post(verify, {"action": "verify", "code": wrong, "next": "/admin/"}).status_code, 200)
        response = self.client.post(verify, {"action": "verify", "code": code, "next": "/admin/"})
        self.assertRedirects(response, "/admin/")
        self.assertEqual(self.client.get(reverse("user_admin_list")).status_code, 200)
        self.assertEqual(self.events(Kind.ADMIN_2FA_FAILED).count(), 1)
        self.assertEqual(self.events(Kind.ADMIN_2FA_PASSED).count(), 1)

    def test_next_cannot_redirect_off_site(self):
        verify_second_factor(self.client)
        response = self.client.get(f"{reverse('moderation_verify')}?next=https://evil.example/")
        self.assertRedirects(response, reverse("moderation_queue"), fetch_redirect_response=False)


class SEC15VerifiedPurchaseReviewTests(Fixtures):
    """SEC-15: only a buyer with a delivered order for the book can review it."""

    def post_review(self):
        return self.client.post(reverse("review_submit", args=[self.book.pk]), {"rating": 5, "comment": "Great read"})

    def test_buyer_without_a_delivered_order_is_refused(self):
        self.client.force_login(self.buyer)
        self.make_order(status=Order.Status.SHIPPED)
        self.post_review()
        self.assertFalse(Review.objects.exists())

    def test_buyer_with_a_delivered_order_can_review(self):
        self.client.force_login(self.buyer)
        self.make_order(status=Order.Status.DELIVERED)
        self.post_review()
        self.assertTrue(Review.objects.filter(user=self.buyer, book=self.book).exists())


# ---------------------------------------------------------------- 3.4 Data protection


class SEC16TransportSecurityTests(Fixtures):
    """SEC-16: HTTP is redirected to HTTPS and HSTS is sent when DJANGO_FORCE_HTTPS=1."""

    @override_settings(SECURE_SSL_REDIRECT=True, SECURE_HSTS_SECONDS=31536000, SECURE_HSTS_INCLUDE_SUBDOMAINS=True)
    def test_plain_http_is_redirected_and_https_gets_hsts(self):
        response = self.client.get(reverse("catalog"))
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response["Location"].startswith("https://"))
        secure = self.client.get(reverse("catalog"), secure=True)
        self.assertIn("max-age=31536000", secure["Strict-Transport-Security"])

    def test_force_https_switch_turns_the_settings_on(self):
        source = (REPO / "bookstore" / "settings.py").read_text()
        for name in ("SECURE_SSL_REDIRECT = True", "SECURE_HSTS_SECONDS = 31536000", "SESSION_COOKIE_SECURE = True", "CSRF_COOKIE_SECURE = True"):
            self.assertIn(name, source)


class SEC17EncryptionAtRestTests(Fixtures):
    """SEC-17: phone numbers and shipping addresses are encrypted in the database."""

    def raw(self, sql, params):
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()[0]

    def test_phone_number_is_encrypted_but_still_works_for_login(self):
        raw = self.raw("SELECT phone FROM accounts_user WHERE id = %s", [self.buyer.pk])
        self.assertNotIn("9800000001", raw)
        self.assertEqual(User.objects.get(pk=self.buyer.pk).phone, "+919800000001")
        response = self.client.post(reverse("login"), {"username": "+91 98000-00001", "password": PASSWORD})
        self.assertEqual(response.status_code, 302)

    def test_duplicate_phone_is_still_rejected(self):
        response = self.client.post(reverse("register"), {
            "email": "dup@example.com", "phone": "+919800000001", "password": "Bookworm42x", "confirm_password": "Bookworm42x",
        })
        self.assertContains(response, "phone number already exists")

    def test_shipping_address_is_encrypted(self):
        order = self.make_order()
        self.assertNotIn("Reading Lane", self.raw("SELECT shipping_address FROM orders_order WHERE id = %s", [order.pk]))


class SEC18NoSecretsInLogsOrUrlsTests(Fixtures):
    """SEC-18: passwords, OTPs, tokens and card data never reach logs, URLs or error messages."""

    def capture_logs(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.DEBUG)
        root = logging.getLogger()
        security = logging.getLogger("bookstore.security")
        old_level = root.level
        root.addHandler(handler)
        security.addHandler(handler)
        root.setLevel(logging.DEBUG)
        self.addCleanup(root.removeHandler, handler)
        self.addCleanup(security.removeHandler, handler)
        self.addCleanup(root.setLevel, old_level)
        return stream

    def test_secrets_never_appear_in_logs_events_or_pages(self):
        logs = self.capture_logs()
        failed = self.client.post(reverse("login"), {"username": "buyer@example.com", "password": "Sup3rSecretGuess"})
        self.client.post(reverse("password_reset"), {"identifier": "buyer@example.com"})
        code = re.search(r"code on the reset page: (\d{6})", mail.outbox[-1].body).group(1)
        wrong = "000000" if code != "000000" else "111111"
        self.client.post(reverse("password_reset_otp"), {"identifier": "buyer@example.com", "code": wrong})
        self.client.force_login(self.buyer)
        self.add_to_cart()
        declined = self.client.post(reverse("checkout"), {"shipping_address": ADDRESS, "card_number": "4000 0000 0000 0002", "card_expiry": "12/34", "card_cvc": "987"})
        self.client.post(reverse("checkout"), {"shipping_address": ADDRESS, **CARD})
        recorded = logs.getvalue() + " ".join(SecurityEvent.objects.values_list("detail", flat=True))
        for secret in ("Sup3rSecretGuess", code, wrong, CARD_NUMBER, "4000000000000002", "987"):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, recorded)
        self.assertNotContains(failed, "Sup3rSecretGuess")
        self.assertNotContains(declined, "4000 0000 0000 0002")
        self.assertNotContains(declined, "4000000000000002")

    def test_reset_token_is_moved_out_of_the_address_bar(self):
        self.client.post(reverse("password_reset"), {"identifier": "buyer@example.com"})
        link = re.search(r"(http\S+)", mail.outbox[-1].body).group(1)
        token = link.rstrip("/").rsplit("/", 1)[-1]
        response = self.client.get(link, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(token, response.redirect_chain[-1][0])
        self.assertNotContains(response, token)

    def test_sensitive_views_hide_post_data_from_error_reports(self):
        cases = {
            reverse("register"): ("password", "confirm_password"),
            reverse("password_reset_otp"): ("code",),
            reverse("checkout"): ("card_number", "card_expiry", "card_cvc"),
        }
        self.client.force_login(self.buyer)
        self.add_to_cart()
        for url, fields in cases.items():
            request = self.client.post(url, {field: "x" for field in fields}).wsgi_request
            with self.subTest(url=url):
                self.assertTrue(set(fields) <= set(getattr(request, "sensitive_post_parameters", [])))


@override_settings(ROOT_URLCONF="security.tests.urls_with_error")
class SEC19GenericErrorPagesTests(TestCase):
    """SEC-19: users see generic error pages; stack traces and database errors stay in server logs."""

    def test_unhandled_error_shows_a_generic_page(self):
        client = Client(raise_request_exception=False)
        with self.assertLogs("django.request", level="ERROR") as logs:
            response = client.get("/boom/")
        self.assertEqual(response.status_code, 500)
        self.assertContains(response, "Something went wrong", status_code=500)
        for leak in ("Traceback", "relation", "secret-table-name", "RuntimeError"):
            self.assertNotContains(response, leak, status_code=500)
        self.assertIn("secret-table-name", "\n".join(logs.output))  # the detail goes to the server log

    def test_debug_is_off(self):
        self.assertFalse(settings.DEBUG)

    def test_missing_page_is_generic(self):
        response = self.client.get("/no-such-page/")
        self.assertContains(response, "Page not found", status_code=404)
        self.assertNotContains(response, "URLconf", status_code=404)


class SEC20EncryptedBackupTests(TestCase):
    """SEC-20: database backups are encrypted and readable only by the operator account."""

    def test_backup_refuses_to_run_without_a_key(self):
        with override_settings(BACKUP_ENCRYPTION_KEY=""), self.assertRaises(CommandError):
            call_command("encrypted_backup", stdout=io.StringIO())

    def test_backup_is_encrypted_private_and_restorable(self):
        key = Fernet.generate_key().decode()
        dump = b"CREATE TABLE accounts_user (email text); INSERT INTO accounts_user VALUES ('buyer@example.com');"
        with tempfile.TemporaryDirectory() as tmp, override_settings(BACKUP_ENCRYPTION_KEY=key), \
                mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, dump, b"")) as run:
            call_command("encrypted_backup", output_dir=tmp, stdout=io.StringIO())
            self.assertEqual(run.call_args.args[0][0], "pg_dump")
            self.assertNotIn("PGPASSWORD", " ".join(run.call_args.args[0]))  # password via env, not argv
            backup = next(Path(tmp).glob("*.sql.enc"))
            self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(Path(tmp).stat().st_mode), 0o700)
            self.assertNotIn(b"buyer@example.com", backup.read_bytes())
            restored = Path(tmp) / "restore.sql"
            call_command("encrypted_backup", decrypt=str(backup), to=str(restored), stdout=io.StringIO())
            self.assertEqual(restored.read_bytes(), dump)
            with override_settings(BACKUP_ENCRYPTION_KEY=Fernet.generate_key().decode()), self.assertRaises(CommandError):
                call_command("encrypted_backup", decrypt=str(backup), to=str(Path(tmp) / "x.sql"), stdout=io.StringIO())


# ---------------------------------------------------------------- 3.5 Payment


class CheckoutFixtures(Fixtures):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.buyer)
        self.add_to_cart()

    def checkout(self, **extra):
        return self.client.post(reverse("checkout"), {"shipping_address": ADDRESS, **CARD, **extra})


class SEC21NoCardStorageTests(CheckoutFixtures):
    """SEC-21: no card number, CVV or expiry is stored anywhere; only the transaction reference."""

    def test_no_table_or_session_contains_card_data_after_checkout(self):
        self.checkout()
        order = Order.objects.get(user=self.buyer, status=Order.Status.PAID)
        self.assertTrue(order.payment_reference.startswith("SBX-"))
        with connection.cursor() as cursor:
            for table in connection.introspection.table_names():
                cursor.execute(f'SELECT t::text FROM "{table}" t')  # nosec B608
                dump = " ".join(row[0] for row in cursor.fetchall())
                with self.subTest(table=table):
                    self.assertNotIn(CARD_NUMBER, dump)
                    self.assertNotIn("4242 4242", dump)
        field_names = {f.name.lower() for model in (Order, OrderItem) for f in model._meta.get_fields()}
        self.assertFalse({"card_number", "cvc", "cvv", "card_expiry"} & field_names)


class SEC22ServerSideTotalsTests(CheckoutFixtures):
    """SEC-22: prices, tax, shipping, discount and total are computed on the server."""

    def test_tampered_amounts_from_the_browser_are_ignored(self):
        self.checkout(total="1.00", price="1.00", discount="999", tax="0", shipping="0", unit_price="1")
        order = Order.objects.get(user=self.buyer, status=Order.Status.PAID)
        # 400 + 5% tax + 50 shipping
        self.assertEqual(order.total, Decimal("470.00"))
        self.assertEqual(order.items.get().unit_price, Decimal("400.00"))


class SEC23VerifiedPaymentTests(CheckoutFixtures):
    """SEC-23: an order exists only after the gateway's success is verified on the server."""

    def assert_no_paid_order_and_cart_intact(self):
        self.assertFalse(Order.objects.filter(user=self.buyer, status=Order.Status.PAID).exists())
        self.assertEqual(CartItem.objects.filter(cart__user=self.buyer).count(), 1)
        self.book.refresh_from_db()
        self.assertEqual(self.book.stock, 5)

    def test_gateway_timeout_creates_no_order(self):
        with mock.patch("orders.payments.SandboxGateway.charge", side_effect=TimeoutError):
            response = self.checkout()
        self.assertContains(response, "could not confirm your payment")
        self.assert_no_paid_order_and_cart_intact()
        self.assertTrue(self.events(Kind.PAYMENT_FAILED).exists())

    def test_success_without_a_transaction_reference_creates_no_order(self):
        from orders.payments import PaymentResult

        with mock.patch("orders.payments.SandboxGateway.charge", return_value=PaymentResult(True, reference="")):
            self.checkout()
        self.assert_no_paid_order_and_cart_intact()

    def test_declined_card_creates_no_paid_order(self):
        self.checkout(card_number="4000 0000 0000 0002")
        self.assert_no_paid_order_and_cart_intact()

    @override_settings(PAYMENT_GATEWAY="stripe", STRIPE_SECRET_KEY="sk_test_dummy")
    def test_hosted_return_url_is_not_trusted_without_asking_the_gateway(self):
        response = self.client.get(reverse("checkout_complete"), {"session_id": "cs_test_forged"})
        self.assertEqual(response.status_code, 302)
        self.assert_no_paid_order_and_cart_intact()


class SEC24CouponAbuseTests(CheckoutFixtures):
    """SEC-24: coupons are validated on the server, respect per-buyer limits and resist guessing."""

    def apply(self, code):
        return self.client.post(reverse("apply_coupon"), {"code": code}, follow=True)

    def test_per_buyer_limit_is_enforced(self):
        Coupon.objects.create(code="WELCOME10", value=Decimal("10"), max_uses_per_buyer=1)
        self.make_order(coupon_code="WELCOME10")
        self.assertContains(self.apply("WELCOME10"), "maximum number of times")
        self.assertNotIn("coupon_code", self.client.session)
        # Another buyer may still use it.
        self.client.force_login(self.other)
        self.add_to_cart(user=self.other)
        self.assertContains(self.apply("WELCOME10"), "Coupon WELCOME10 applied")

    def test_per_buyer_limit_is_rechecked_when_the_order_is_placed(self):
        Coupon.objects.create(code="ONCE", value=Decimal("10"), max_uses_per_buyer=1)
        self.apply("ONCE")
        self.make_order(coupon_code="ONCE")  # used in another tab meanwhile
        response = self.client.post(reverse("checkout"), {"shipping_address": ADDRESS, **CARD}, follow=True)
        self.assertContains(response, "maximum number of times")
        self.assertEqual(Order.objects.filter(user=self.buyer, status=Order.Status.PAID, coupon_code="ONCE").count(), 1)

    def test_guessing_codes_is_rate_limited(self):
        Coupon.objects.create(code="REAL20", value=Decimal("20"))
        for n in range(10):
            self.apply(f"GUESS{n}")
        self.assertContains(self.apply("REAL20"), "Too many invalid coupon attempts")
        self.assertNotIn("coupon_code", self.client.session)
        self.assertEqual(self.events(Kind.COUPON_REJECTED).count(), 10)

    def test_discount_comes_from_the_server_side_coupon(self):
        Coupon.objects.create(code="TEN", value=Decimal("10"))
        self.apply("TEN")
        self.checkout(discount="400")
        self.assertEqual(Order.objects.get(user=self.buyer, status=Order.Status.PAID).discount, Decimal("40.00"))


# ---------------------------------------------------------------- 3.6 Input handling


class SEC25InputValidationTests(Fixtures):
    """SEC-25: forms, search terms, filters and URL parameters are validated on the server."""

    def test_search_and_filters_reject_bad_types_and_lengths(self):
        for params in ({"q": "x" * 300}, {"min_price": "-5"}, {"max_price": "abc"}, {"min_price": "9", "max_price": "1"}):
            with self.subTest(params=params):
                response = self.client.get(reverse("catalog"), params)
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.context["form"].is_valid())
                self.assertEqual(len(response.context["page_obj"]), 0)

    def test_registration_rejects_bad_email_and_phone(self):
        response = self.client.post(reverse("register"), {"email": "not-an-email", "phone": "12ab", "password": "Bookworm42x", "confirm_password": "Bookworm42x"})
        self.assertContains(response, "Enter a valid email address")
        self.assertContains(response, "Enter a valid phone number")

    def test_listing_and_cart_reject_out_of_range_values(self):
        from catalog.forms import ListingForm

        form = ListingForm({"title": "T", "author": "A", "isbn": "9780132350884", "category": "Tech", "price": "-1", "condition": "new", "stock": "-2", "description": ""})
        self.assertFalse(form.is_valid())
        self.assertIn("price", form.errors)
        self.client.force_login(self.buyer)
        item = self.add_to_cart()
        for quantity in ("0", "-3", "abc", "100000"):
            self.client.post(reverse("cart_update", args=[item.pk]), {"quantity": quantity})
            item.refresh_from_db()
            self.assertEqual(item.quantity, 1, quantity)

    def test_non_numeric_url_ids_never_reach_the_view(self):
        self.assertEqual(self.client.get("/books/1%20OR%201=1/").status_code, 404)


class SEC26SqlInjectionTests(Fixtures):
    """SEC-26: queries are parameterised; injected SQL is treated as plain text."""

    def test_injection_strings_in_search_are_harmless(self):
        for payload in ("' OR '1'='1", "'; DROP TABLE catalog_book; --", "9780132350884' OR 1=1 --"):
            with self.subTest(payload=payload):
                response = self.client.get(reverse("catalog"), {"q": payload})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.context["page_obj"]), 0)
        self.assertEqual(Book.objects.count(), 2)

    def test_injection_in_login_is_harmless(self):
        response = self.client.post(reverse("login"), {"username": "' OR 1=1 --", "password": "' OR 1=1 --"})
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(response.status_code, 200)

    def test_application_code_uses_no_raw_sql(self):
        allowed = {"bookstore/tests", "security/tests", "migrations", "security/management/commands/encrypted_backup.py"}
        offenders = []
        for path in REPO.glob("*/**/*.py"):
            rel = path.relative_to(REPO).as_posix()
            if rel.startswith((".", "venv")) or any(part in rel for part in allowed) or "/tests/" in rel:
                continue
            text = path.read_text()
            if re.search(r"\.raw\(|\.extra\(|cursor\.execute|RawSQL", text):
                offenders.append(rel)
        self.assertEqual(offenders, [])


class SEC27OutputEncodingTests(Fixtures):
    """SEC-27: user-written content is HTML-escaped when shown."""

    def test_listing_description_and_title_are_escaped(self):
        book = self.make_book(self.seller, "<b>Bold</b>", "9780261103340", "10.00", description="<script>alert('x')</script>")
        page = self.client.get(reverse("book_detail", args=[book.pk]))
        self.assertNotContains(page, "<script>alert('x')</script>")
        self.assertContains(page, "&lt;script&gt;")
        self.assertNotContains(page, "<b>Bold</b>")

    def test_review_text_is_escaped(self):
        Review.objects.create(book=self.book, user=self.buyer, rating=4, comment='<img src=x onerror="alert(1)">')
        page = self.client.get(reverse("book_detail", args=[self.book.pk]))
        self.assertNotContains(page, '<img src=x onerror="alert(1)">')
        self.assertContains(page, "&lt;img")

    def test_templates_never_mark_user_content_safe(self):
        hits = [p.as_posix() for p in REPO.glob("**/templates/**/*.html") if re.search(r"\|\s*safe|autoescape\s+off", p.read_text())]
        self.assertEqual(hits, [])


class SEC28CsrfTests(Fixtures):
    """SEC-28: state-changing requests need a CSRF token."""

    def test_posts_without_a_token_are_refused(self):
        order = self.make_order()
        cases = [
            (self.buyer, reverse("checkout")),
            (self.buyer, reverse("cart_add", args=[self.book.pk])),
            (self.buyer, reverse("apply_coupon")),
            (self.buyer, reverse("review_submit", args=[self.book.pk])),
            (self.buyer, reverse("flag_listing", args=[self.book.pk])),
            (self.buyer, reverse("profile_delete")),
            (self.seller, reverse("listing_edit", args=[self.book.pk])),
            (self.seller, reverse("listing_remove", args=[self.book.pk])),
            (self.seller, reverse("seller_order_ship", args=[order.pk])),
        ]
        for user, url in cases:
            strict = Client(enforce_csrf_checks=True)
            strict.force_login(user)
            with self.subTest(url=url):
                self.assertEqual(strict.post(url, {"x": "1"}).status_code, 403)
        self.book.refresh_from_db()
        self.assertEqual(self.book.status, Book.Status.APPROVED)
        self.assertEqual(self.events(Kind.CSRF_FAILED).count(), len(cases))

    @override_settings(LOGISTICS_WEBHOOK_SECRET="carrier-secret")
    def test_the_only_csrf_exempt_endpoint_requires_a_signature(self):
        response = Client(enforce_csrf_checks=True).post(reverse("tracking_webhook"), b"{}", content_type="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(self.events(Kind.WEBHOOK_REJECTED).exists())


class SEC29ReviewModerationTests(Fixtures):
    """SEC-29: reviews flagged by the content filter wait for an admin before publication."""

    def setUp(self):
        super().setUp()
        self.make_order(status=Order.Status.DELIVERED)
        self.client.force_login(self.buyer)

    def review(self, text):
        self.client.post(reverse("review_submit", args=[self.book.pk]), {"rating": 1, "comment": text})
        return Review.objects.get(user=self.buyer, book=self.book)

    def test_flagged_reviews_are_held_and_hidden(self):
        for text in ("This seller is a scam, total idiot", "Cheap copies at www.spam.example", "Call me on +91 98765 43210"):
            Review.objects.filter(user=self.buyer).delete()
            with self.subTest(text=text):
                review = self.review(text)
                self.assertEqual(review.status, Review.Status.HELD)
                page = Client().get(reverse("book_detail", args=[self.book.pk]))
                self.assertNotContains(page, text[:10])
                self.assertEqual(page.context["review_count"], 0)
        self.assertEqual(self.events(Kind.REVIEW_HELD).count(), 3)

    def test_clean_review_is_published_and_admin_can_approve_a_held_one(self):
        self.assertEqual(self.review("A careful, well argued book.").status, Review.Status.PUBLISHED)
        Review.objects.all().delete()
        held = self.review("Stupid ending")
        admin = User.objects.create_superuser("root@example.com", PASSWORD)
        self.client.force_login(admin)
        verify_second_factor(self.client)
        self.client.post(reverse("admin:reviews_review_changelist"), {"action": "approve_reviews", "_selected_action": [held.pk]})
        held.refresh_from_db()
        self.assertEqual(held.status, Review.Status.PUBLISHED)
        self.assertContains(Client().get(reverse("book_detail", args=[self.book.pk])), "Stupid ending")


class SEC30RateLimitTests(Fixtures):
    """SEC-30: login, registration, password reset and search are rate limited per client."""

    def flood(self, method, url, data, times, ip="203.0.113.7"):
        client = Client(REMOTE_ADDR=ip)
        send = getattr(client, method)
        return [send(url, data(n) if callable(data) else data).status_code for n in range(times)]

    def test_each_entry_point_returns_429_after_its_limit(self):
        cases = {
            "login": ("post", reverse("login"), {"username": "x@example.com", "password": "y"}),
            "register": ("post", reverse("register"), lambda n: {"email": f"bad{n}"}),
            "password_reset": ("post", reverse("password_reset"), {"identifier": "nobody@example.com"}),
            "password_reset_otp": ("post", reverse("password_reset_otp"), {"identifier": "nobody@example.com", "code": "123456"}),
            "search": ("get", reverse("catalog"), {"q": "clean"}),
        }
        for scope, (method, url, data) in cases.items():
            limit, _ = settings.RATE_LIMITS[scope]
            with self.subTest(scope=scope):
                codes = self.flood(method, url, data, limit + 1, ip=f"203.0.113.{len(scope)}")
                self.assertNotIn(429, codes[:limit])
                self.assertEqual(codes[-1], 429)
                self.assertEqual(self.flood(method, url, data, 1, ip="198.51.100.1")[0] != 429, True)
        self.assertEqual(self.events(Kind.RATE_LIMITED).count(), len(cases))

    def test_limits_are_shared_in_the_database_across_servers(self):
        self.flood("get", reverse("catalog"), {"q": "clean"}, 3)
        self.assertEqual(RateLimitBucket.objects.get(scope="search").count, 3)


# ---------------------------------------------------------------- 3.7 Logging


class SEC31SecurityEventLogTests(Fixtures):
    """SEC-31: security events are logged with a time and, where known, the user id."""

    def test_each_event_type_is_recorded(self):
        self.login(self.client, self.buyer, "Wrong-pass-9")
        self.login(self.client, self.buyer)
        self.client.post(reverse("logout"))
        self.client.post(reverse("password_reset"), {"identifier": "buyer@example.com"})
        self.client.force_login(self.buyer)
        self.client.get(reverse("listing_add"))  # authorisation failure
        self.add_to_cart()
        self.client.post(reverse("checkout"), {"shipping_address": ADDRESS, **CARD, "card_number": "4000 0000 0000 0002"})
        for _ in range(3):
            self.login(Client(), self.other, "Wrong-pass-9")
        expected = {
            Kind.LOGIN_FAILED: None, Kind.LOGIN_SUCCESS: self.buyer.pk, Kind.LOGOUT: self.buyer.pk,
            Kind.RESET_REQUESTED: self.buyer.pk, Kind.AUTHZ_DENIED: self.buyer.pk,
            Kind.PAYMENT_FAILED: self.buyer.pk, Kind.LOCKOUT: None,
        }
        for kind, user_id in expected.items():
            with self.subTest(kind=kind):
                event = SecurityEvent.objects.filter(kind=kind).order_by("pk").first()
                self.assertIsNotNone(event)
                self.assertIsNotNone(event.created_at)
                self.assertEqual(event.ip_address, "127.0.0.1")
                if user_id:
                    self.assertEqual(event.user_id_ref, user_id)

    def test_events_also_go_to_the_security_logger(self):
        with self.assertLogs("bookstore.security", level="INFO") as logs:
            self.login(self.client, self.buyer)
        self.assertIn(f"kind=login_success user={self.buyer.pk}", logs.output[0])


class SEC32ProtectedLogTests(Fixtures):
    """SEC-32: the log cannot be altered, is read-only to staff and is kept for 90 days."""

    def setUp(self):
        super().setUp()
        self.event = SecurityEvent.objects.create(kind=Kind.LOGIN_FAILED, detail="test")

    def test_application_cannot_edit_or_delete_events(self):
        self.event.detail = "rewritten"
        with self.assertRaises(PermissionError):
            self.event.save()
        with self.assertRaises(PermissionError):
            self.event.delete()

    def test_database_rejects_raw_updates_and_early_deletes(self):
        for sql in ("UPDATE security_securityevent SET detail = 'x'", "DELETE FROM security_securityevent"):
            with self.subTest(sql=sql), self.assertRaises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql)
        self.assertEqual(SecurityEvent.objects.get(pk=self.event.pk).detail, "test")

    def test_admin_is_read_only_and_needs_view_permission(self):
        from django.contrib.admin.sites import site
        from django.test import RequestFactory

        model_admin = site._registry[SecurityEvent]
        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser("root@example.com", PASSWORD)
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request, self.event))
        self.assertFalse(model_admin.has_delete_permission(request, self.event))
        self.assertEqual(SecurityEvent._meta.default_permissions, ("view",))

    def test_retention_purge_keeps_ninety_days(self):
        self.assertEqual(settings.SECURITY_LOG_RETENTION_DAYS, 90)
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO security_securityevent (created_at, kind, path, detail) VALUES (now() - interval '91 days', 'login_failed', '', 'old')"
            )
        call_command("purge_security_events", stdout=io.StringIO())
        self.assertEqual(list(SecurityEvent.objects.values_list("detail", flat=True)), ["test"])


# ---------------------------------------------------------------- 3.8 Privacy


class SEC33DataMinimisationTests(TestCase):
    """SEC-33: only account, delivery and order data is collected."""

    def test_user_model_holds_only_account_data(self):
        stored = {f.name for f in User._meta.concrete_fields}
        expected = {"id", "password", "last_login", "is_superuser", "email", "phone", "phone_digest", "full_name",
                    "is_active", "is_staff", "date_joined", "suspended_at", "removed_at"}
        self.assertEqual(stored, expected)

    def test_registration_asks_only_for_what_is_needed(self):
        from accounts.forms import RegistrationForm

        self.assertEqual(list(RegistrationForm.base_fields), ["email", "phone", "password", "confirm_password"])

    def test_orders_hold_no_extra_personal_data(self):
        personal = {"date_of_birth", "gender", "national_id", "aadhaar", "pan"}
        for model in (User, Order):
            self.assertFalse(personal & {f.name for f in model._meta.get_fields()})


class SEC34PrivacyNoticeTests(TestCase):
    """SEC-34: registration links to a privacy notice that says what is collected and why."""

    def test_registration_page_links_to_the_notice(self):
        self.assertContains(self.client.get(reverse("register")), f'href="{reverse("privacy")}"')

    def test_notice_explains_what_and_why(self):
        page = self.client.get(reverse("privacy"))
        for text in ("What we collect", "email address", "shipping address", "card numbers", "Your rights"):
            self.assertContains(page, text)


class SEC35DataCorrectionAndDeletionTests(Fixtures):
    """SEC-35: users can correct or delete their personal data; order records are kept."""

    def setUp(self):
        super().setUp()
        self.order = self.make_order()
        self.client.force_login(self.buyer)

    def test_user_can_correct_their_details(self):
        self.client.post(reverse("profile_update"), {"full_name": "Asha R.", "email": "asha@example.com", "phone": "+919811111111"})
        self.buyer.refresh_from_db()
        self.assertEqual((self.buyer.full_name, self.buyer.email, self.buyer.phone), ("Asha R.", "asha@example.com", "+919811111111"))
        self.assertTrue(self.events(Kind.ACCOUNT_UPDATED).exists())

    def test_deletion_needs_the_password(self):
        self.client.post(reverse("profile_delete"), {"password": "wrong", "confirm": "on"})
        self.buyer.refresh_from_db()
        self.assertTrue(self.buyer.is_active)

    def test_deletion_erases_personal_data_but_keeps_orders(self):
        response = self.client.post(reverse("profile_delete"), {"password": PASSWORD, "confirm": "on"})
        self.assertRedirects(response, reverse("catalog"))
        self.buyer.refresh_from_db()
        self.assertEqual((self.buyer.email, self.buyer.phone, self.buyer.full_name, self.buyer.is_active), (None, None, "", False))
        self.assertFalse(self.buyer.has_usable_password())
        self.assertTrue(Order.objects.filter(pk=self.order.pk, user=self.buyer).exists())
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.login(Client(), User(email="buyer@example.com")).status_code, 200)
        self.assertTrue(self.events(Kind.ACCOUNT_DELETED).exists())


# ---------------------------------------------------------------- 3.9 Integrations and practice


class SEC36SecureIntegrationsTests(Fixtures):
    """SEC-36: payment, shipping and notification integrations use authenticated APIs over TLS."""

    def test_payment_api_is_https_and_authenticated(self):
        from orders import stripe_gateway

        self.assertTrue(stripe_gateway.API_BASE.startswith("https://"))
        with override_settings(STRIPE_SECRET_KEY="sk_test_dummy"), mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = b"{}"
            stripe_gateway._request("GET", "/checkout/sessions/cs_test")
        request = urlopen.call_args.args[0]
        self.assertTrue(request.full_url.startswith("https://"))
        self.assertEqual(request.get_header("Authorization"), "Bearer sk_test_dummy")

    def test_carrier_api_must_be_https(self):
        from orders.logistics import HttpCarrier, ShipmentError

        order = self.make_order()
        with override_settings(SHIPPING_API_URL="http://carrier.example"), mock.patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(ShipmentError):
                HttpCarrier().create_shipment(order)
            urlopen.assert_not_called()
        with override_settings(SHIPPING_API_URL="https://carrier.example", SHIPPING_API_KEY="k"), mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = b'{"tracking_number": "TRK1"}'
            HttpCarrier().create_shipment(order)
            self.assertEqual(urlopen.call_args.args[0].get_header("Authorization"), "Bearer k")

    def test_email_uses_tls_by_default(self):
        self.assertIn('os.environ.get("EMAIL_USE_TLS", "1")', (REPO / "bookstore" / "settings.py").read_text())


class SEC37SecretsOutOfSourceTests(TestCase):
    """SEC-37: secrets come from the environment and are not committed."""

    def test_settings_read_secrets_from_the_environment(self):
        source = (REPO / "bookstore" / "settings.py").read_text()
        for name in ("DJANGO_SECRET_KEY", "DB_PASSWORD", "STRIPE_SECRET_KEY", "EMAIL_HOST_PASSWORD", "FIELD_ENCRYPTION_KEY", "BACKUP_ENCRYPTION_KEY"):
            self.assertRegex(source, rf'os\.environ(\.get\(|\[)\s*"{name}"')

    def test_no_secret_values_are_committed(self):
        tracked = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=False).stdout.split()
        if not tracked:
            self.skipTest("not a git checkout")
        self.assertNotIn(".env", tracked)
        pattern = re.compile(r"sk_live_[0-9A-Za-z]{10,}|sk_test_[0-9A-Za-z]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC )?PRIVATE KEY-----|ghp_[0-9A-Za-z]{30,}")
        leaks = []
        for name in tracked:
            path = REPO / name
            if path.suffix in {".py", ".txt", ".md", ".yml", ".yaml", ".example", ".cfg", ".toml", ".json", ".html", ".sh"} or path.name.startswith(".env"):
                if path.is_file() and pattern.search(path.read_text(errors="ignore")):
                    leaks.append(name)
        self.assertEqual(leaks, [])
        self.assertIn(".env", (REPO / ".gitignore").read_text().split())


class SEC38DependencyHygieneTests(TestCase):
    """SEC-38: dependencies are scanned for known vulnerabilities in CI and kept current."""

    def test_ci_runs_pip_audit(self):
        workflow = (REPO / ".github" / "workflows" / "django-tests.yml").read_text()
        self.assertIn("pip-audit -r requirements.txt", workflow)

    def test_pillow_is_on_the_patched_major_version(self):
        from importlib.metadata import version

        self.assertIn("Pillow>=13", (REPO / "requirements.txt").read_text())
        self.assertGreaterEqual(int(version("pillow").split(".")[0]), 13)


class SEC39SecureDevelopmentTests(TestCase):
    """SEC-39: reviews include a security check and unit tests cover every security rule."""

    def test_pull_requests_carry_a_security_checklist(self):
        template = (REPO / ".github" / "pull_request_template.md").read_text()
        self.assertIn("Security check (SEC-39)", template)

    def test_ci_runs_tests_and_static_analysis(self):
        workflow = (REPO / ".github" / "workflows" / "django-tests.yml").read_text()
        self.assertIn("coverage run manage.py test", workflow)
        self.assertIn("bandit", workflow)

    def test_every_requirement_has_a_test_class(self):
        names = {name for name in globals() if re.match(r"SEC\d\d", name)}
        covered = {int(name[3:5]) for name in names}
        self.assertEqual(covered, set(range(1, 40)))
