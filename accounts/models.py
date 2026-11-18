import hashlib
import hmac
import re
from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.conf import settings
from django.utils import timezone

from bookstore.fields import EncryptedTextField


def normalise_phone(value):
    return re.sub(r"[\s-]", "", value or "")


def phone_digest(value):
    """Keyed hash of a phone number, used to look accounts up by phone (SEC-17).

    The number itself is stored encrypted, which makes it unsearchable; this
    HMAC gives exact-match lookup and uniqueness without revealing the number.
    """
    value = normalise_phone(value)
    if not value:
        return None
    key = (getattr(settings, "FIELD_ENCRYPTION_KEY", "") or settings.SECRET_KEY).encode()
    return hmac.new(key, f"phone:{value}".encode(), hashlib.sha256).hexdigest()


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email=None, password=None, **extra):
        if not email and not extra.get("phone"):
            raise ValueError("Email or phone is required")
        user = self.model(email=self.normalize_email(email) if email else None, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True, null=True, blank=True)
    # Encrypted at rest (SEC-17); phone_digest is the lookup and uniqueness key.
    phone = EncryptedTextField(null=True, blank=True)
    phone_digest = models.CharField(max_length=64, unique=True, null=True, blank=True, editable=False)
    full_name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    # Account moderation keeps the row so orders, reviews and listings retain their owner.
    suspended_at = models.DateTimeField(null=True, blank=True)
    removed_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def save(self, *args, **kwargs):
        self.phone = normalise_phone(self.phone) or None
        self.phone_digest = phone_digest(self.phone)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "phone" in update_fields:
            kwargs["update_fields"] = set(update_fields) | {"phone_digest"}
        super().save(*args, **kwargs)

    @property
    def is_suspended(self):
        return self.suspended_at is not None and self.removed_at is None

    @property
    def is_removed(self):
        return self.removed_at is not None

    @property
    def moderation_status(self):
        if self.is_removed:
            return "removed"
        if self.is_suspended:
            return "suspended"
        return "active"

    def __str__(self):
        return self.email or self.phone or f"Deleted user #{self.pk}"


class LoginThrottle(models.Model):
    """Consecutive failed sign-ins for one typed identifier, and when its temporary lock ends."""

    identifier = models.CharField(max_length=254, unique=True)
    failures = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ()


class AccountAction(models.Model):
    """An audited administrative action on a user account."""

    class Action(models.TextChoices):
        SUSPEND = "suspend", "Suspended"
        REMOVE = "remove", "Removed"

    target = models.ForeignKey(User, on_delete=models.PROTECT, related_name="moderation_actions_received")
    admin = models.ForeignKey(User, on_delete=models.PROTECT, related_name="moderation_actions_made")
    action = models.CharField(max_length=10, choices=Action.choices)
    reason = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        default_permissions = ("view",)

    def __str__(self):
        return f"{self.get_action_display()} {self.target} by {self.admin}"


class PasswordResetOTP(models.Model):
    """A six digit reset code emailed alongside the reset link (FR-14, Test Plan FR-14_UT02)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reset_otps")
    code_hash = models.CharField(max_length=256)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        default_permissions = ()

    @property
    def is_live(self):
        return self.used_at is None and self.expires_at > timezone.now() and self.attempts < MAX_OTP_ATTEMPTS


MAX_OTP_ATTEMPTS = 5
MAX_OTP_LIFETIME = timedelta(minutes=10)
