import re
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("reader@example.com", "old-pass-123", phone="+15550100")
        self.request_url = reverse("password_reset")

    def _link(self):
        self.client.post(self.request_url, {"identifier": "reader@example.com"})
        return re.search(r"http://testserver(\S+)", mail.outbox[0].body).group(1)

    def test_request_page_renders(self):
        self.assertContains(self.client.get(self.request_url), "Email or phone")

    def test_login_page_links_to_reset(self):
        self.assertContains(self.client.get(reverse("login")), self.request_url)

    def test_request_with_email_sends_link(self):
        response = self.client.post(self.request_url, {"identifier": "READER@example.com"})
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["reader@example.com"])

    def test_request_with_phone_sends_link_to_account_email(self):
        self.client.post(self.request_url, {"identifier": "+1 555-0100"})
        self.assertEqual(len(mail.outbox), 1)

    def test_unknown_account_gets_same_reply_and_no_mail(self):
        response = self.client.post(self.request_url, {"identifier": "nobody@example.com"})
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_phone_only_account_gets_no_mail(self):
        User.objects.create_user(password="x-pass-123", phone="+15550222")
        self.client.post(self.request_url, {"identifier": "+15550222"})
        self.assertEqual(len(mail.outbox), 0)

    def test_valid_link_sets_new_password(self):
        link = self._link()
        self.assertEqual(self.client.get(link).status_code, 200)
        response = self.client.post(link, {"password": "brand-new-9", "confirm_password": "brand-new-9"})
        self.assertRedirects(response, reverse("login"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("brand-new-9"))
        self.assertNotIn("brand-new-9", self.user.password)

    def test_link_is_single_use(self):
        link = self._link()
        self.client.post(link, {"password": "brand-new-9", "confirm_password": "brand-new-9"})
        self.assertEqual(self.client.get(link).status_code, 400)

    def test_link_expires(self):
        link = self._link()
        with mock.patch("django.contrib.auth.tokens.PasswordResetTokenGenerator._now") as now:
            now.return_value = __import__("datetime").datetime.now() + timedelta(hours=2)
            self.assertEqual(self.client.get(link).status_code, 400)

    def test_bad_link_is_rejected(self):
        url = reverse("password_reset_confirm", args=["zzz", "bad-token"])
        self.assertEqual(self.client.get(url).status_code, 400)

    def test_weak_password_is_rejected(self):
        link = self._link()
        response = self.client.post(link, {"password": "short1", "confirm_password": "short1"})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("old-pass-123"))

    def test_password_without_digit_is_rejected(self):
        link = self._link()
        response = self.client.post(link, {"password": "onlyletters", "confirm_password": "onlyletters"})
        self.assertContains(response, "at least one letter and one digit")

    def test_mismatch_is_rejected(self):
        link = self._link()
        response = self.client.post(link, {"password": "brand-new-9", "confirm_password": "other-new-9"})
        self.assertContains(response, "do not match")

    def test_old_sessions_are_logged_out_after_reset(self):
        other = self.client_class()
        other.login(username="reader@example.com", password="old-pass-123")
        self.assertIn("_auth_user_id", other.session)
        link = self._link()
        self.client.post(link, {"password": "brand-new-9", "confirm_password": "brand-new-9"})
        self.assertEqual(other.get(reverse("profile")).status_code, 302)
