"""Password reset by emailed code (Test Plan FR-14_UT02)."""
import re
from datetime import timedelta

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import PasswordResetOTP, User


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ResetOTPTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("buyer@example.com", "Reading2026!")

    def request_code(self):
        self.client.post(reverse("password_reset"), {"identifier": "buyer@example.com"})
        return re.search(r"reset page: ([0-9]{6})", mail.outbox[-1].body).group(1)

    def test_a_code_is_emailed_with_the_reset_link(self):
        code = self.request_code()
        self.assertTrue(PasswordResetOTP.objects.filter(user=self.user).exists())
        self.assertEqual(len(code), 6)

    def test_the_wrong_code_is_refused_and_no_reset_happens(self):
        self.request_code()
        response = self.client.post(
            reverse("password_reset_otp"),
            {"identifier": "buyer@example.com", "code": "000000"},
        )
        self.assertContains(response, "Incorrect OTP")
        self.assertNotIn("otp_reset_user", self.client.session)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Reading2026!"))

    def test_the_right_code_leads_to_the_new_password_page(self):
        code = self.request_code()
        response = self.client.post(
            reverse("password_reset_otp"),
            {"identifier": "buyer@example.com", "code": code},
        )
        self.assertRedirects(response, reverse("password_reset_otp_set"))
        self.assertEqual(self.client.session["otp_reset_user"], self.user.pk)

    def test_a_code_can_only_be_used_once(self):
        code = self.request_code()
        payload = {"identifier": "buyer@example.com", "code": code}
        self.client.post(reverse("password_reset_otp"), payload)
        self.client.post(reverse("password_reset_otp_set"), {"password": "NewReading2026!", "confirm_password": "NewReading2026!"})

        second = self.client.post(reverse("password_reset_otp"), payload)
        self.assertContains(second, "This reset link/OTP is no longer valid")

    def test_an_expired_code_is_refused(self):
        code = self.request_code()
        PasswordResetOTP.objects.filter(user=self.user).update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.client.post(
            reverse("password_reset_otp"),
            {"identifier": "buyer@example.com", "code": code},
        )
        self.assertContains(response, "OTP has expired, please request a new one")

    def test_too_many_wrong_codes_lock_the_code(self):
        code = self.request_code()
        for _ in range(5):
            self.client.post(reverse("password_reset_otp"), {"identifier": "buyer@example.com", "code": "111111"})
        response = self.client.post(
            reverse("password_reset_otp"),
            {"identifier": "buyer@example.com", "code": code},
        )
        self.assertContains(response, "Incorrect OTP")

    def test_the_new_password_is_saved_and_works_for_login(self):
        code = self.request_code()
        self.client.post(reverse("password_reset_otp"), {"identifier": "buyer@example.com", "code": code})
        response = self.client.post(
            reverse("password_reset_otp_set"),
            {"password": "NewReading2026!", "confirm_password": "NewReading2026!"},
            follow=True,
        )
        self.assertContains(response, "Your password has been changed.")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewReading2026!"))

    def test_the_new_password_page_needs_a_verified_code_first(self):
        response = self.client.get(reverse("password_reset_otp_set"))
        self.assertRedirects(response, reverse("password_reset"))

    def test_a_weak_new_password_is_refused(self):
        code = self.request_code()
        self.client.post(reverse("password_reset_otp"), {"identifier": "buyer@example.com", "code": code})
        response = self.client.post(
            reverse("password_reset_otp_set"),
            {"password": "123", "confirm_password": "123"},
        )
        self.assertContains(response, "at least 8")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Reading2026!"))
