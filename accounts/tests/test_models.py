from django.test import TestCase

from accounts.models import User


class UserModelTests(TestCase):
    def test_create_user_hashes_password(self):
        user = User.objects.create_user("a@example.com", "s3cret-pass", phone="+15550001")
        self.assertNotEqual(user.password, "s3cret-pass")
        self.assertTrue(user.check_password("s3cret-pass"))
        self.assertEqual(str(user), "a@example.com")

    def test_email_or_phone_required(self):
        with self.assertRaises(ValueError):
            User.objects.create_user("", "x")

    def test_create_superuser(self):
        admin = User.objects.create_superuser("root@example.com", "pw")
        self.assertTrue(admin.is_staff and admin.is_superuser)
