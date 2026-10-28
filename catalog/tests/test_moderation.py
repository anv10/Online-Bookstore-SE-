from datetime import timedelta
import re
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core import mail
from django.db import IntegrityError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from catalog.models import AdminChallenge, Book, ModerationEvent
from orders.models import Order, OrderItem


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ModerationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("admin@example.com", "Reading2026!", is_staff=True)
        cls.permission = Permission.objects.get(codename="change_book", content_type__app_label="catalog")
        cls.admin.user_permissions.add(cls.permission)
        cls.seller = User.objects.create_user("seller@example.com", "Reading2026!")
        cls.seller.user_permissions.add(Permission.objects.get(codename="add_book", content_type__app_label="catalog"))
        cls.buyer = User.objects.create_user("buyer@example.com", "Reading2026!")
        cls.book = Book.objects.create(title="Pending book", author="Author", isbn="9780132350884", price="10.00", seller=cls.seller, stock=3)

    def setUp(self):
        self.client.force_login(self.admin)
        self.verify_url = reverse("moderation_verify")
        self.queue_url = reverse("moderation_queue")
        self.decide_url = reverse("moderation_decide", args=[self.book.pk])

    def send_code(self):
        self.client.post(self.verify_url, {"action": "send"})
        return re.search(r"\b[0-9]{6}\b", mail.outbox[-1].body).group()

    def verify(self):
        return self.client.post(self.verify_url, {"action": "verify", "code": self.send_code()})

    def data(self, status="approved", **changes):
        self.book.refresh_from_db()
        data = {"status": status, "expected_status": self.book.status, "reason": "Reviewed listing details"}
        data.update(changes)
        return data

    def test_anonymous_and_non_admin_access(self):
        self.client.logout()
        for url in (self.verify_url, self.queue_url, self.decide_url):
            self.assertEqual(self.client.get(url).status_code, 302)
        for user in (self.buyer, self.seller):
            self.client.force_login(user)
            for url in (self.verify_url, self.queue_url, self.decide_url):
                for method in (self.client.get, self.client.post):
                    self.assertEqual(method(url).status_code, 405 if method == self.client.post and url == self.queue_url else 403)

    def test_permission_alone_and_staff_alone_do_not_grant_admin_access(self):
        self.buyer.user_permissions.add(self.permission)
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.get(self.queue_url).status_code, 403)
        self.buyer.is_staff = True
        self.buyer.save()
        self.buyer.user_permissions.clear()
        self.assertEqual(self.client.get(self.queue_url).status_code, 403)

    def test_second_factor_required_and_expires(self):
        self.assertRedirects(self.client.get(self.queue_url), self.verify_url)
        self.assertRedirects(self.client.post(self.decide_url, self.data()), self.verify_url)
        self.assertRedirects(self.verify(), self.queue_url)
        self.assertEqual(self.client.get(self.queue_url).status_code, 200)
        self.assertRedirects(self.client.get(self.verify_url), self.queue_url)
        session = self.client.session
        session["moderation_verified_until"] = timezone.now().timestamp() - 1
        session.save()
        self.assertRedirects(self.client.get(self.queue_url), self.verify_url)

    def test_codes_are_hashed_single_use_and_bound_to_session(self):
        code = self.send_code()
        challenge = AdminChallenge.objects.get(user=self.admin)
        self.assertNotEqual(challenge.code_hash, code)
        second = Client()
        second.force_login(self.admin)
        second.post(self.verify_url, {"action": "verify", "code": code})
        self.assertRedirects(second.get(self.queue_url), self.verify_url)
        self.assertRedirects(self.client.post(self.verify_url, {"action": "verify", "code": code}), self.queue_url)
        challenge.refresh_from_db()
        self.assertEqual(challenge.code_hash, "")

    def test_expired_code_is_rejected(self):
        code = self.send_code()
        AdminChallenge.objects.filter(user=self.admin).update(expires_at=timezone.now()-timedelta(seconds=1))
        response = self.client.post(self.verify_url, {"action": "verify", "code": code})
        self.assertContains(response, "Invalid or expired")
        self.assertRedirects(self.client.get(self.queue_url), self.verify_url)

    def test_five_incorrect_guesses_lock_code(self):
        code = self.send_code()
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            self.client.post(self.verify_url, {"action": "verify", "code": wrong})
        self.assertContains(self.client.post(self.verify_url, {"action": "verify", "code": code}), "Invalid or expired")

    def test_five_requests_per_account_per_hour_including_other_sessions(self):
        for _ in range(5):
            self.send_code()
        response = self.client.post(self.verify_url, {"action": "send"})
        self.assertContains(response, "Too many code requests")
        self.assertEqual(len(mail.outbox), 5)
        AdminChallenge.objects.filter(user=self.admin).update(window_started=timezone.now()-timedelta(hours=2))
        self.send_code()
        self.assertEqual(len(mail.outbox), 6)

    def test_delivery_failure_is_generic_and_code_invalidated(self):
        with patch("catalog.moderation.send_mail", side_effect=RuntimeError("private SMTP details")):
            response = self.client.post(self.verify_url, {"action": "send"})
        self.assertContains(response, "could not be sent")
        self.assertNotContains(response, "private SMTP details")
        self.assertEqual(AdminChallenge.objects.get(user=self.admin).code_hash, "")

    def test_email_backend_accepting_no_messages_fails_closed(self):
        with patch("catalog.moderation.send_mail", return_value=0):
            response = self.client.post(self.verify_url, {"action": "send"})
        self.assertContains(response, "could not be sent")
        self.assertEqual(AdminChallenge.objects.get(user=self.admin).code_hash, "")

    def test_other_sellers_cannot_read_decisions(self):
        self.verify()
        self.client.post(self.decide_url, self.data(reason="Seller private outcome"))
        other = User.objects.create_user("other@example.com", "Reading2026!")
        other.user_permissions.add(Permission.objects.get(codename="add_book", content_type__app_label="catalog"))
        self.client.force_login(other)
        self.assertNotContains(self.client.get(reverse("seller_listings")), "Seller private outcome")

    def test_email_required_and_invalid_code_format(self):
        self.admin.email = None
        self.admin.save()
        self.assertContains(self.client.post(self.verify_url, {"action": "send"}), "configure your email")
        self.assertEqual(AdminChallenge.objects.count(), 0)
        self.assertContains(self.client.post(self.verify_url, {"action": "verify", "code": "not-a-code"}), "Enter a valid value")

    def test_queue_defaults_to_pending_and_filters_paginate(self):
        self.verify()
        Book.objects.create(title="Approved book", author="A", isbn="x", price=3, seller=self.seller, status="approved")
        response = self.client.get(self.queue_url)
        self.assertContains(response, self.book.title)
        self.assertNotContains(response, "Approved book")
        self.assertContains(self.client.get(self.queue_url, {"status": "approved"}), "Approved book")
        self.assertContains(self.client.get(self.queue_url, {"status": "invalid", "page": "invalid"}), self.book.title)

    def test_approve_suspend_remove_are_audited_and_hide_listing(self):
        self.verify()
        for target in ("approved", "suspended", "approved", "removed"):
            previous = self.data()["expected_status"]
            self.assertRedirects(self.client.post(self.decide_url, self.data(target)), self.queue_url)
            self.book.refresh_from_db()
            self.assertEqual(self.book.status, target)
            event = self.book.moderation_events.first()
            self.assertEqual((event.admin_id, event.previous_status, event.new_status, event.reason), (self.admin.pk, previous, target, "Reviewed listing details"))
            self.assertIsNotNone(event.created_at)
            detail = self.client.get(reverse("book_detail", args=[self.book.pk]))
            self.assertEqual(detail.status_code, 200 if target == "approved" else 404)
            search = self.client.get(reverse("catalog"), {"q": self.book.title})
            self.assertEqual(bool(search.context["page_obj"].object_list), target == "approved")
        self.assertEqual(ModerationEvent.objects.count(), 4)

    def test_reason_invalid_target_and_stale_decision_rejected(self):
        self.verify()
        for changes in ({"reason": " "}, {"reason": "x"*1001}, {"status": "pending"}, {"status": "invented"}):
            response = self.client.post(self.decide_url, self.data(**changes))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors)
        stale = self.data()
        Book.objects.filter(pk=self.book.pk).update(status="suspended")
        self.assertEqual(self.client.post(self.decide_url, stale).status_code, 409)
        self.assertEqual(ModerationEvent.objects.count(), 0)

    def test_duplicate_and_removed_listing_cannot_be_reinstated(self):
        self.verify()
        self.client.post(self.decide_url, self.data())
        self.assertContains(self.client.post(self.decide_url, self.data()), "already approved")
        self.client.post(self.decide_url, self.data("removed"))
        self.assertContains(self.client.post(self.decide_url, self.data()), "cannot be reinstated")
        self.assertEqual(ModerationEvent.objects.count(), 2)

    def test_inactive_or_missing_seller_prevents_approval(self):
        self.verify()
        self.seller.is_active = False
        self.seller.save()
        self.assertContains(self.client.post(self.decide_url, self.data()), "active seller is required")
        Book.objects.filter(pk=self.book.pk).update(seller=None)
        self.assertContains(self.client.post(self.decide_url, self.data()), "active seller is required")
        self.assertEqual(ModerationEvent.objects.count(), 0)

    def test_order_history_survives_moderation_removal(self):
        order = Order.objects.create(user=self.buyer, total=10, shipping_address="Test address", status="paid")
        item = OrderItem.objects.create(order=order, book=self.book, quantity=1, unit_price=10)
        self.verify()
        self.client.post(self.decide_url, self.data("removed"))
        item.refresh_from_db()
        self.assertEqual(item.book_id, self.book.pk)
        self.assertEqual(order.items.count(), 1)

    def test_audit_failure_rolls_back_decision(self):
        self.verify()
        with patch("catalog.moderation.ModerationEvent.objects.create", side_effect=IntegrityError):
            with self.assertRaises(IntegrityError):
                self.client.post(self.decide_url, self.data())
        self.book.refresh_from_db()
        self.assertEqual(self.book.status, "pending")

    def test_get_does_not_change_status_and_unknown_book_returns_404(self):
        self.verify()
        self.assertEqual(self.client.get(self.decide_url).status_code, 200)
        self.assertEqual(self.client.get(reverse("moderation_decide", args=[999999])).status_code, 404)
        self.assertEqual(ModerationEvent.objects.count(), 0)
        self.assertEqual(self.client.put(self.decide_url).status_code, 405)

    def test_csrf_required_for_codes_and_decisions(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(self.verify_url, {"action": "send"}).status_code, 403)
        self.assertEqual(client.post(self.decide_url, self.data()).status_code, 403)
        self.assertEqual(ModerationEvent.objects.count(), 0)

    def test_reason_escaped_and_seller_sees_own_outcome(self):
        self.verify()
        self.client.post(self.decide_url, self.data(reason="<script>alert(1)</script>"))
        response = self.client.get(self.decide_url)
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.client.force_login(self.seller)
        self.assertContains(self.client.get(reverse("seller_listings")), "&lt;script&gt;")

    def test_seller_edit_does_not_undo_concurrent_moderation(self):
        from catalog.forms import EditListingForm
        original_save = EditListingForm.save
        def concurrent_save(form, commit=True):
            Book.objects.filter(pk=form.instance.pk).update(status="suspended")
            return original_save(form, commit=commit)
        self.client.force_login(self.seller)
        with patch.object(EditListingForm, "save", concurrent_save):
            response = self.client.post(reverse("listing_edit", args=[self.book.pk]), {
                "title": "Revised title", "author": "Author", "isbn": "9780132350884",
                "category": "Books", "price": "10", "condition": "new", "stock": 3, "description": "Revised"
            })
        self.assertEqual(response.status_code, 302)
        self.book.refresh_from_db()
        self.assertEqual(self.book.title, "Revised title")
        self.assertEqual(self.book.status, "suspended")

    def test_django_admin_cannot_bypass_status_or_hard_delete(self):
        from catalog.admin import BookAdmin
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory
        model_admin = BookAdmin(Book, AdminSite())
        request = RequestFactory().get("/admin/")
        request.user = self.admin
        self.assertIn("status", model_admin.get_readonly_fields(request, self.book))
        self.assertFalse(model_admin.has_delete_permission(request, self.book))
