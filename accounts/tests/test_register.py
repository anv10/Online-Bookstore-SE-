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

    def test_password_needs_letter_and_digit(self):
        for pw in ("ZyqvMtrLpx", "!@#$%^&*()"):
            r = self.post("pol@example.com", pw)
            self.assertEqual(r.status_code, 200)
        self.assertContains(self.post("pol@example.com", "ZyqvMtrLpx"), "letter and one digit")
        self.assertEqual(User.objects.count(), 0)

    def test_password_whitespace_preserved(self):
        pw = "  Tr1cky-horse-9  "
        self.assertEqual(self.post("sp@example.com", pw).status_code, 302)
        user = User.objects.get(email="sp@example.com")
        self.assertTrue(user.check_password(pw))
        self.assertFalse(user.check_password(pw.strip()))
        self.assertContains(self.post("sp2@example.com", pw, pw.strip()), "do not match")

    def test_duplicate_race_returns_form_error(self):
        from unittest import mock

        from accounts.forms import RegistrationForm

        for ident, label in (("race@example.com", "email"), ("+15550009999", "phone number")):
            form = RegistrationForm(
                {"identifier": ident, "password": "Tr1cky-horse-9", "confirm_password": "Tr1cky-horse-9"}
            )
            self.assertTrue(form.is_valid())
            if label == "email":
                User.objects.create_user(email=ident, password="x1y2z3w4v5")
            else:
                User.objects.create_user(password="x1y2z3w4v5", phone=ident)
            self.assertIsNone(form.save())
            self.assertIn(label, form.errors["identifier"][0])
