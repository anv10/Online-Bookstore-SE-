"""Buyer reports against listings (FR-12_ST01)."""
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from catalog.models import Book, ListingFlag


class ListingFlagTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.seller = User.objects.create_user("seller@example.com", "Reading2026!")
        cls.seller.user_permissions.add(Permission.objects.get(codename="add_book", content_type__app_label="catalog"))
        cls.buyer = User.objects.create_user("buyer@example.com", "Reading2026!")
        cls.other_buyer = User.objects.create_user("other@example.com", "Reading2026!")
        cls.admin = User.objects.create_user("admin@example.com", "Reading2026!", is_staff=True)
        cls.admin.user_permissions.add(Permission.objects.get(codename="change_book", content_type__app_label="catalog"))
        cls.book = Book.objects.create(
            title="Approved book", author="Author", isbn="9780132350884", price="10.00",
            seller=cls.seller, stock=3, status=Book.Status.APPROVED,
        )

    def setUp(self):
        self.flag_url = reverse("flag_listing", args=[self.book.pk])
        self.detail_url = reverse("book_detail", args=[self.book.pk])

    def verify(self):
        session = self.client.session
        session["moderation_verified_until"] = timezone.now().timestamp() + 600
        session.save()

    def test_a_signed_in_buyer_can_report_a_listing(self):
        self.client.force_login(self.buyer)
        response = self.client.post(self.flag_url, {"reason": "Wrong edition on the cover"}, follow=True)
        self.assertContains(response, "A moderator will review this listing.")
        flag = ListingFlag.objects.get()
        self.assertEqual(flag.reporter, self.buyer)
        self.assertEqual(flag.book, self.book)
        self.assertEqual(flag.state, ListingFlag.State.OPEN)

    def test_a_report_without_a_reason_is_refused(self):
        self.client.force_login(self.buyer)
        response = self.client.post(self.flag_url, {"reason": "   "}, follow=True)
        self.assertContains(response, "A reason is required to report a listing.")
        self.assertFalse(ListingFlag.objects.exists())

    def test_reporting_the_same_listing_twice_keeps_one_open_flag(self):
        self.client.force_login(self.buyer)
        self.client.post(self.flag_url, {"reason": "First"})
        response = self.client.post(self.flag_url, {"reason": "Second"}, follow=True)
        self.assertContains(response, "You have already reported this listing.")
        self.assertEqual(ListingFlag.objects.filter(state=ListingFlag.State.OPEN).count(), 1)

    def test_anonymous_visitors_cannot_report(self):
        response = self.client.post(self.flag_url, {"reason": "Spam"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ListingFlag.objects.exists())

    def test_the_report_form_is_shown_to_signed_in_buyers(self):
        self.client.force_login(self.buyer)
        self.assertContains(self.client.get(self.detail_url), 'name="reason"')

    def test_reported_listings_appear_in_the_moderation_queue(self):
        ListingFlag.objects.create(book=self.book, reporter=self.buyer, reason="Misleading")
        self.client.force_login(self.admin)
        self.verify()
        response = self.client.get(reverse("moderation_queue"), {"status": "flagged"})
        self.assertContains(response, "Approved book")
        self.assertContains(response, "Reported by buyers")

    # --- end-to-end: report, review, reject, listing disappears ---
    def test_a_moderator_rejecting_a_reported_listing_hides_it_from_buyers(self):
        ListingFlag.objects.create(book=self.book, reporter=self.buyer, reason="Counterfeit copy")
        self.client.force_login(self.admin)
        self.verify()
        self.assertEqual(
            self.client.post(reverse("moderation_decide", args=[self.book.pk]), {
                "status": Book.Status.REMOVED,
                "expected_status": Book.Status.APPROVED,
                "reason": "Counterfeit confirmed",
            }).status_code,
            302,
        )
        self.book.refresh_from_db()
        self.assertEqual(self.book.status, Book.Status.REMOVED)
        flag = ListingFlag.objects.get()
        self.assertEqual(flag.state, ListingFlag.State.UPHELD)
        self.assertEqual(flag.decided_by, self.admin)
        self.assertIsNotNone(flag.decided_at)

        self.client.force_login(self.other_buyer)
        self.assertEqual(self.client.get(self.detail_url).status_code, 404)
        self.assertNotContains(self.client.get(reverse("catalog")), "Approved book")

    def test_an_approved_listing_keeps_its_open_flags(self):
        ListingFlag.objects.create(book=self.book, reporter=self.buyer, reason="Unsure")
        self.client.force_login(self.admin)
        self.verify()
        self.client.post(reverse("moderation_decide", args=[self.book.pk]), {
            "status": Book.Status.APPROVED,
            "expected_status": Book.Status.APPROVED,
            "reason": "Checked and fine",
        })
        self.assertEqual(ListingFlag.objects.get().state, ListingFlag.State.OPEN)
