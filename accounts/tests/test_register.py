from django.test import TestCase
from django.urls import reverse

from accounts.models import User

PHONE = "+1 555-000-1234"


class RegisterTests(TestCase):
    url = reverse("register")
    password = "Tr1cky-horse-9"

    def post(self, email="new@example.com", phone=PHONE, pw=None, confirm=None):
        password = pw or self.password
        return self.client.post(
            self.url,
            {"email": email, "phone": phone, "password": password, "confirm_password": confirm or password},
        )

    def test_page_loads(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_register_creates_an_account_with_email_and_phone(self):
        r = self.post("New@Example.com")
        self.assertEqual(r.status_code, 302)
        user = User.objects.get(email="new@example.com")
        self.assertEqual(user.phone, "+15550001234")
        self.assertNotEqual(user.password, self.password)
        self.assertTrue(user.check_password(self.password))

    def test_blank_phone_is_rejected(self):
        r = self.post(phone="")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Phone number is required")
        self.assertFalse(User.objects.exists())

    def test_blank_email_is_rejected(self):
        r = self.post(email="")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Email address is required")
        self.assertFalse(User.objects.exists())

    def test_duplicate_email_rejected(self):
        self.post("dup@example.com")
        r = self.post("DUP@example.com", phone="+15550009999")
        self.assertContains(r, "already exists")
        self.assertEqual(User.objects.count(), 1)

    def test_duplicate_phone_rejected(self):
        self.post()
        r = self.post("other@example.com", phone=PHONE)
        self.assertContains(r, "phone number already exists")
        self.assertEqual(User.objects.count(), 1)

    def test_invalid_email_format_rejected(self):
        for bad in ("abc", "a@", "john.doe@@mail"):
            with self.subTest(email=bad):
                r = self.post(bad)
                self.assertContains(r, "valid email address")
        self.assertFalse(User.objects.exists())

    def test_invalid_phone_format_rejected(self):
        r = self.post(phone="12ab")
        self.assertContains(r, "valid phone number")
        self.assertFalse(User.objects.exists())

    def test_weak_password_rejected(self):
        for pw in ("123", "short1", "password123", "12345678901"):
            r = self.post("weak@example.com", pw=pw)
            self.assertEqual(r.status_code, 200)
        self.assertEqual(User.objects.count(), 0)

    def test_password_mismatch(self):
        r = self.post("m@example.com", confirm="Other-pass-123")
        self.assertContains(r, "do not match")

    def test_password_needs_letter_and_digit(self):
        for pw in ("ZyqvMtrLpx", "!@#$%^&*()"):
            r = self.post("pol@example.com", pw=pw)
            self.assertEqual(r.status_code, 200)
        self.assertContains(self.post("pol@example.com", pw="ZyqvMtrLpx"), "letter and one digit")
        self.assertEqual(User.objects.count(), 0)

    def test_password_whitespace_preserved(self):
        pw = "  Tr1cky-horse-9  "
        self.assertEqual(self.post("sp@example.com", pw=pw).status_code, 302)
        user = User.objects.get(email="sp@example.com")
        self.assertTrue(user.check_password(pw))
        self.assertFalse(user.check_password(pw.strip()))
        self.assertContains(
            self.post("sp2@example.com", phone="+15550009998", pw=pw, confirm=pw.strip()), "do not match"
        )

    def test_duplicate_race_returns_form_error(self):
        from accounts.forms import RegistrationForm

        for field, value, label in (
            ("email", "race@example.com", "email"),
            ("phone", "+15550009999", "phone number"),
        ):
            with self.subTest(field=field):
                data = {"email": "race@example.com", "phone": "+15550009999", "password": self.password}
                data["confirm_password"] = self.password
                data[field] = value
                form = RegistrationForm(data)
                self.assertTrue(form.is_valid())
                if field == "email":
                    User.objects.create_user(email=value, phone="+15550001111", password="x1y2z3w4v5")
                else:
                    User.objects.create_user(email="taken@example.com", phone=value, password="x1y2z3w4v5")
                self.assertIsNone(form.save())
                self.assertIn(label, form.errors[field][0])
                User.objects.all().delete()
