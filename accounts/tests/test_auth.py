from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class LoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("reader@example.com", "s3cret-pass", phone="+15550100")
        self.login_url = reverse("login")
        self.profile_url = reverse("profile")
        self.landing_url = reverse("catalog")

    def test_login_page_renders(self):
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email or phone")

    def test_login_with_email_starts_session(self):
        response = self.client.post(self.login_url, {"username": "reader@example.com", "password": "s3cret-pass"})
        self.assertRedirects(response, self.landing_url)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_login_with_email_is_case_insensitive(self):
        response = self.client.post(self.login_url, {"username": "READER@Example.com", "password": "s3cret-pass"})
        self.assertRedirects(response, self.landing_url)

    def test_login_with_phone(self):
        response = self.client.post(self.login_url, {"username": "+15550100", "password": "s3cret-pass"})
        self.assertRedirects(response, self.landing_url)

    def test_wrong_password_and_unknown_user_give_same_generic_error(self):
        wrong_password = self.client.post(self.login_url, {"username": "reader@example.com", "password": "nope"})
        unknown_user = self.client.post(self.login_url, {"username": "ghost@example.com", "password": "nope"})
        self.assertEqual(wrong_password.status_code, 200)
        self.assertEqual(unknown_user.status_code, 200)
        message = "Invalid credentials. Please try again."
        self.assertContains(wrong_password, message)
        self.assertContains(unknown_user, message)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_user_cannot_log_in(self):
        self.user.is_active = False
        self.user.save()
        response = self.client.post(self.login_url, {"username": "reader@example.com", "password": "s3cret-pass"})
        self.assertContains(response, "Invalid credentials. Please try again.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_blank_credentials_rejected(self):
        response = self.client.post(self.login_url, {"username": "", "password": ""})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_backend_ignores_missing_username_or_password(self):
        from accounts.backends import EmailOrPhoneBackend

        backend = EmailOrPhoneBackend()
        self.assertIsNone(backend.authenticate(None, username=None, password="x"))
        self.assertIsNone(backend.authenticate(None, username="reader@example.com", password=None))
        self.assertEqual(backend.authenticate(None, email="reader@example.com", password="s3cret-pass"), self.user)


class LogoutAndProtectionTests(TestCase):
    def setUp(self):
        User.objects.create_user("reader@example.com", "s3cret-pass")

    def test_logout_ends_session(self):
        self.client.login(username="reader@example.com", password="s3cret-pass")
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_protected_page_redirects_to_login_when_anonymous(self):
        response = self.client.get(reverse("profile"))
        expected = f"{reverse('login')}?next={reverse('profile')}"
        self.assertRedirects(response, expected)

    def test_protected_page_available_when_logged_in(self):
        self.client.login(username="reader@example.com", password="s3cret-pass")
        response = self.client.get(reverse("profile"))
        self.assertContains(response, "reader@example.com")

    def test_login_honours_next_parameter(self):
        url = f"{reverse('login')}?next={reverse('profile')}"
        response = self.client.post(url, {"username": "reader@example.com", "password": "s3cret-pass"})
        self.assertRedirects(response, reverse("profile"))


class PhoneOnlyUserTests(TestCase):
    def test_phone_only_user_can_log_in_and_see_profile(self):
        User.objects.create_user(password="s3cret-pass", phone="+15550222")
        response = self.client.post(reverse("login"), {"username": "+15550222", "password": "s3cret-pass"})
        self.assertRedirects(response, reverse("catalog"))
        page = self.client.get(reverse("profile"))
        self.assertContains(page, "+15550222")
        self.assertNotContains(page, "None")
