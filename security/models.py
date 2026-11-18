"""Security event log (SEC-31, SEC-32) and request rate-limit counters (SEC-6, SEC-24, SEC-30)."""

from django.db import models


class SecurityEvent(models.Model):
    """One append-only security log entry.

    Rows can be added but never changed: ``save`` refuses updates, the Django
    admin is read-only, and on PostgreSQL a trigger (migration 0002) rejects
    UPDATE outright and DELETE of anything younger than the retention period,
    so even code that bypasses the ORM cannot rewrite recent history.
    """

    class Kind(models.TextChoices):
        LOGIN_SUCCESS = "login_success", "Successful login"
        LOGIN_FAILED = "login_failed", "Failed login"
        LOGOUT = "logout", "Logout"
        LOCKOUT = "lockout", "Account lockout"
        RESET_REQUESTED = "reset_requested", "Password reset requested"
        RESET_COMPLETED = "reset_completed", "Password reset completed"
        RESET_OTP_FAILED = "reset_otp_failed", "Wrong password reset code"
        ADMIN_2FA_SENT = "admin_2fa_sent", "Admin verification code sent"
        ADMIN_2FA_PASSED = "admin_2fa_passed", "Admin verification passed"
        ADMIN_2FA_FAILED = "admin_2fa_failed", "Admin verification failed"
        ADMIN_ACTION = "admin_action", "Admin action"
        AUTHZ_DENIED = "authz_denied", "Authorisation failure"
        CSRF_FAILED = "csrf_failed", "CSRF check failed"
        PAYMENT_FAILED = "payment_failed", "Failed payment"
        RATE_LIMITED = "rate_limited", "Request rate limited"
        COUPON_REJECTED = "coupon_rejected", "Coupon code rejected"
        REVIEW_HELD = "review_held", "Review held for moderation"
        ACCOUNT_UPDATED = "account_updated", "Personal data corrected"
        ACCOUNT_DELETED = "account_deleted", "Account deleted on request"
        WEBHOOK_REJECTED = "webhook_rejected", "Webhook signature rejected"

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    kind = models.CharField(max_length=32, choices=Kind.choices, db_index=True)
    # A plain id, not a foreign key: the log must not change when an account does.
    user_id_ref = models.BigIntegerField(null=True, blank=True, db_index=True, verbose_name="user id")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    path = models.CharField(max_length=255, blank=True)
    detail = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        default_permissions = ("view",)

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Security events are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Security events are removed only by the retention purge.")

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M:%S} {self.kind} user={self.user_id_ref}"


class RateLimitBucket(models.Model):
    """Requests counted for one scope and key inside one fixed time window.

    Kept in the database (not a per-process cache) so every app server shares
    the same counts and tests roll them back with everything else.
    """

    scope = models.CharField(max_length=40)
    key = models.CharField(max_length=128)
    window_start = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=["scope", "key", "window_start"], name="one_bucket_per_window"),
        ]
        indexes = [models.Index(fields=["window_start"])]
