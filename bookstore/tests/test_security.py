import importlib
import os
from decimal import Decimal
from unittest import mock

from django.db import connection
from cryptography.fernet import Fernet
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings

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

    def _raw_set(self, order, value):
        with connection.cursor() as cursor:
            cursor.execute("UPDATE orders_order SET shipping_address = %s WHERE id = %s", [value, order.pk])

    def test_plain_text_value_is_rejected(self):
        user = User.objects.create_user("p@example.com", "pw")
        order = Order.objects.create(user=user, total=Decimal("5"), shipping_address="x")
        self._raw_set(order, "old plain")
        with self.assertRaises(ValueError):
            order.refresh_from_db()

    def test_wrong_key_is_rejected(self):
        user = User.objects.create_user("w@example.com", "pw")
        order = Order.objects.create(user=user, total=Decimal("5"), shipping_address="1 Main St")
        with override_settings(FIELD_ENCRYPTION_KEY=Fernet.generate_key().decode()):
            with self.assertRaises(ValueError):
                order.refresh_from_db()

    def test_tampered_token_is_rejected(self):
        user = User.objects.create_user("t@example.com", "pw")
        order = Order.objects.create(user=user, total=Decimal("5"), shipping_address="1 Main St")
        with connection.cursor() as cursor:
            cursor.execute("SELECT shipping_address FROM orders_order WHERE id = %s", [order.pk])
            raw = cursor.fetchone()[0]
        self._raw_set(order, raw[:-4] + ("AAAA" if not raw.endswith("AAAA") else "BBBB"))
        with self.assertRaises(ValueError):
            order.refresh_from_db()

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
        for name in ("SECURE_SSL_REDIRECT", "SECURE_PROXY_SSL_HEADER", "SECURE_HSTS_SECONDS",
                     "SECURE_HSTS_INCLUDE_SUBDOMAINS", "SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE"):
            if hasattr(project_settings, name):
                delattr(project_settings, name)
        importlib.reload(project_settings)

    def test_https_settings_when_enabled(self):
        cfg = self._load("1")
        self.assertTrue(cfg.SECURE_SSL_REDIRECT)
        self.assertGreaterEqual(cfg.SECURE_HSTS_SECONDS, 31536000)
        self.assertTrue(cfg.SESSION_COOKIE_SECURE)
        self.assertTrue(cfg.CSRF_COOKIE_SECURE)

    def test_https_settings_off_by_default(self):
        for name in ("SECURE_SSL_REDIRECT", "SESSION_COOKIE_SECURE"):
            if hasattr(project_settings, name):
                delattr(project_settings, name)
        cfg = self._load("0")
        self.assertFalse(getattr(cfg, "SECURE_SSL_REDIRECT", False))

    def test_secrets_come_from_environment(self):
        source = open(project_settings.__file__).read()
        self.assertIn('os.environ["DJANGO_SECRET_KEY"]', source)
        self.assertIn('os.environ["DB_PASSWORD"]', source)


class ExistingAddressMigrationTests(TransactionTestCase):
    def tearDown(self):
        MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def _raw_addresses(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT shipping_address FROM orders_order ORDER BY id")
            return [row[0] for row in cursor.fetchall()]

    def test_existing_plain_addresses_are_encrypted_once(self):
        executor = MigrationExecutor(connection)
        executor.migrate([("orders", "0002_encrypt_shipping_address")])
        user = User.objects.create_user("m@example.com", "pw")
        already = Fernet(_key()).encrypt(b"2 Side St").decode()
        with connection.cursor() as cursor:
            for address in ("1 Main St", already):
                cursor.execute(
                    "INSERT INTO orders_order (user_id, status, total, shipping_address, created_at) "
                    "VALUES (%s, 'pending', 5, %s, now())",
                    [user.pk, address],
                )
        MigrationExecutor(connection).migrate([("orders", "0003_encrypt_existing_addresses")])
        raw = self._raw_addresses()
        self.assertNotIn("1 Main St", raw[0])
        self.assertEqual(raw[1], already)
        self.assertEqual(
            [o.shipping_address for o in Order.objects.order_by("id")], ["1 Main St", "2 Side St"]
        )

    def test_migration_can_be_reversed(self):
        user = User.objects.create_user("r@example.com", "pw")
        Order.objects.create(user=user, total=Decimal("5"), shipping_address="3 Back St")
        MigrationExecutor(connection).migrate([("orders", "0002_encrypt_shipping_address")])
        self.assertEqual(self._raw_addresses(), ["3 Back St"])


def _key():
    import base64
    import hashlib

    from django.conf import settings

    return base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
