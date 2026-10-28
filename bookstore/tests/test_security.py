import importlib
import os
from decimal import Decimal
from unittest import mock

from django.db import connection
from django.test import TestCase

from accounts.models import User
from bookstore import settings as project_settings
from orders.models import Order


class PasswordHashingTests(TestCase):
    def test_password_is_hashed_with_argon2(self):
        user = User.objects.create_user("h@example.com", "S3cure-pass!")
        self.assertTrue(user.password.startswith("argon2"))
        self.assertTrue(user.check_password("S3cure-pass!"))
        self.assertNotIn("S3cure-pass!", user.password)


class EncryptionAtRestTests(TestCase):
    def test_shipping_address_is_encrypted_in_the_database(self):
        user = User.objects.create_user("e@example.com", "pw")
        order = Order.objects.create(user=user, total=Decimal("5"), shipping_address="1 Main St")
        with connection.cursor() as cursor:
            cursor.execute("SELECT shipping_address FROM orders_order WHERE id = %s", [order.pk])
            raw = cursor.fetchone()[0]
        self.assertNotIn("Main St", raw)
        order.refresh_from_db()
        self.assertEqual(order.shipping_address, "1 Main St")

    def test_plain_text_rows_from_before_encryption_still_load(self):
        user = User.objects.create_user("p@example.com", "pw")
        order = Order.objects.create(user=user, total=Decimal("5"), shipping_address="x")
        with connection.cursor() as cursor:
            cursor.execute("UPDATE orders_order SET shipping_address = 'old plain' WHERE id = %s", [order.pk])
        order.refresh_from_db()
        self.assertEqual(order.shipping_address, "old plain")

    def test_null_value_is_kept(self):
        from bookstore.fields import EncryptedTextField

        field = EncryptedTextField(null=True)
        self.assertIsNone(field.get_prep_value(None))
        self.assertIsNone(field.from_db_value(None, None, None))


class HttpsSettingsTests(TestCase):
    def _load(self, force):
        with mock.patch.dict(os.environ, {"DJANGO_FORCE_HTTPS": force}):
            return importlib.reload(project_settings)

    def tearDown(self):
        importlib.reload(project_settings)

    def test_https_settings_when_enabled(self):
        cfg = self._load("1")
        self.assertTrue(cfg.SECURE_SSL_REDIRECT)
        self.assertGreaterEqual(cfg.SECURE_HSTS_SECONDS, 31536000)
        self.assertTrue(cfg.SESSION_COOKIE_SECURE)
        self.assertTrue(cfg.CSRF_COOKIE_SECURE)

    def test_https_settings_off_by_default(self):
        cfg = self._load("0")
        self.assertFalse(hasattr(cfg, "SECURE_SSL_REDIRECT"))

    def test_secrets_come_from_environment(self):
        source = open(project_settings.__file__).read()
        self.assertIn('os.environ["DJANGO_SECRET_KEY"]', source)
        self.assertIn('os.environ["DB_PASSWORD"]', source)
