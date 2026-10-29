from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


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
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
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
        return self.email or self.phone


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
