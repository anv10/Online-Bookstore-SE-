from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class RegisterTests(TestCase):
    url = reverse("register")

    def post(self, ident, pw="Tr1cky-horse-9", confirm=None):
        return self.client.post(
            self.url,
            {"identifier": ident, "password": pw, "confirm_password": confirm or pw},
        )

    def test_page_loads(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_register_with_email(self):
        r = self.post("New@Example.com")
        self.assertEqual(r.status_code, 302)
        user = User.objects.get(email="new@example.com")
        self.assertNotEqual(user.password, "Tr1cky-horse-9")
        self.assertTrue(user.check_password("Tr1cky-horse-9"))

    def test_register_with_phone(self):
        self.assertEqual(self.post("+1 555-000-1234").status_code, 302)
        user = User.objects.get(phone="+15550001234")
        self.assertIsNone(user.email)
        self.assertTrue(user.check_password("Tr1cky-horse-9"))

    def test_duplicate_email_rejected(self):
        self.post("dup@example.com")
        r = self.post("DUP@example.com")
        self.assertContains(r, "already exists")
        self.assertEqual(User.objects.count(), 1)

    def test_duplicate_phone_rejected(self):
        self.post("+15550001234")
        r = self.post("+15550001234")
        self.assertContains(r, "phone number already exists")

    def test_invalid_identifier(self):
        self.assertContains(self.post("abc"), "valid email address or phone")
        self.assertContains(self.post("a@"), "valid email")

    def test_weak_password_rejected(self):
        for pw in ("short1", "password123", "12345678901"):
            r = self.post("weak@example.com", pw)
            self.assertEqual(r.status_code, 200)
        self.assertEqual(User.objects.count(), 0)

    def test_password_mismatch(self):
        r = self.post("m@example.com", confirm="Other-pass-123")
        self.assertContains(r, "do not match")
