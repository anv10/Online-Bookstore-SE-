from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import LoginThrottle, User

GOOD = "s3cret-pass"


@override_settings(LOGIN_MAX_FAILURES=3, LOGIN_LOCKOUT_MINUTES=15)
class LoginLockoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("reader@example.com", GOOD, phone="+15550100")
        self.url = reverse("login")

    def attempt(self, username="reader@example.com", password="wrong-pass"):
        return self.client.post(self.url, {"username": username, "password": password})

    def test_first_failures_keep_the_generic_error(self):
        for _ in range(2):
            self.assertContains(self.attempt(), "Invalid credentials. Please try again.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_third_failure_locks_with_a_warning(self):
        self.attempt()
        self.attempt()
        response = self.attempt()
        self.assertContains(response, "Too many failed sign-in attempts. Please try again in 15 minutes.")
        self.assertNotContains(response, "Invalid credentials")

    def test_correct_password_is_refused_while_locked(self):
        for _ in range(3):
            self.attempt()
        response = self.attempt(password=GOOD)
        self.assertContains(response, "Too many failed sign-in attempts")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_lock_expires(self):
        for _ in range(3):
            self.attempt()
        LoginThrottle.objects.update(locked_until=timezone.now() - timedelta(seconds=1))
        response = self.attempt(password=GOOD)
        self.assertRedirects(response, reverse("catalog"))

    def test_failure_after_expired_lock_starts_a_fresh_count(self):
        for _ in range(3):
            self.attempt()
        LoginThrottle.objects.update(locked_until=timezone.now() - timedelta(seconds=1))
        self.assertContains(self.attempt(), "Invalid credentials. Please try again.")
        self.assertEqual(LoginThrottle.objects.get().failures, 1)

    def test_success_clears_the_count(self):
        self.attempt()
        self.attempt()
        self.assertRedirects(self.attempt(password=GOOD), reverse("catalog"))
        self.assertFalse(LoginThrottle.objects.exists())
        self.client.logout()
        self.attempt()
        self.assertContains(self.attempt(), "Invalid credentials. Please try again.")

    def test_unknown_identifier_locks_the_same_way(self):
        for _ in range(2):
            self.attempt("ghost@example.com")
        self.assertContains(self.attempt("ghost@example.com"), "Too many failed sign-in attempts")

    def test_lock_is_per_identifier_and_case_insensitive(self):
        for _ in range(3):
            self.attempt("READER@example.com")
        self.assertContains(self.attempt("reader@example.com", GOOD), "Too many failed sign-in attempts")
        self.assertRedirects(self.attempt("+15550100", GOOD), reverse("catalog"))

    def test_blank_credentials_do_not_count(self):
        for _ in range(5):
            self.attempt("", "")
        self.assertFalse(LoginThrottle.objects.exists())

    @override_settings(LOGIN_LOCKOUT_MINUTES=1)
    def test_singular_minute(self):
        for _ in range(2):
            self.attempt()
        self.assertContains(self.attempt(), "try again in 1 minute.")
