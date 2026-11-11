from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from bookstore.fields import EncryptedTextField


class Coupon(models.Model):
    """A discount code (FR-11): a percentage or a fixed rupee amount off the book subtotal."""

    class Kind(models.TextChoices):
        PERCENT = "percent", "Percentage off"
        FIXED = "fixed", "Fixed amount off (rupees)"

    code = models.CharField(max_length=40, unique=True)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PERCENT)
    value = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    max_uses = models.PositiveIntegerField(null=True, blank=True, help_text="Leave empty for no limit.")
    times_used = models.PositiveIntegerField(default=0, editable=False)
    min_order_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Leave empty for no minimum order value (FR-11).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        if self.kind == self.Kind.PERCENT and self.value is not None and self.value > 100:
            raise ValidationError({"value": "A percentage cannot be more than 100."})

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.code


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Placed"
        PAYMENT_FAILED = "payment_failed", "Payment Failed"
        PAID = "paid", "Paid"
        SHIPPED = "shipped", "Shipped"
        OUT_FOR_DELIVERY = "out_for_delivery", "Out for delivery"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    coupon_code = models.CharField(max_length=40, blank=True)
    # The carrier's own reference for this shipment (FR-9). Empty until it ships.
    tracking_reference = models.CharField(max_length=64, blank=True, db_index=True)
    shipping_address = EncryptedTextField()
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def reference(self):
        """Carrier-facing order number in the ORD00012 form the Test Plan prints (FR-6_UT03)."""
        return f"ORD{self.pk:05d}"

    @property
    def refunded_total(self):
        """Rupees returned to the buyer so far (FR-13, Test Plan FR-13_IT03)."""
        return self.refunds.aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")

    @property
    def estimated_delivery(self):
        """Ship date plus the configured transit time (FR-9, Test Plan FR-9_UT03)."""
        from .tracking import estimated_delivery as _estimated_delivery

        return _estimated_delivery(self)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    book = models.ForeignKey("catalog.Book", on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)


class PendingPayment(models.Model):
    """A hosted payment that has been started but not yet confirmed with the gateway.

    The order only exists once the gateway says the session was paid, so a
    cancelled or abandoned payment leaves no order and no stock change. Only
    the cart lines, total and address are kept here; no card data ever reaches
    this server because the buyer pays on the gateway's own page.
    """

    class Status(models.TextChoices):
        STARTED = "started", "Started"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments")
    session_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.STARTED, db_index=True)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    coupon_code = models.CharField(max_length=40, blank=True)
    shipping_address = EncryptedTextField()
    lines = models.JSONField(default=list)
    order = models.OneToOneField(Order, null=True, blank=True, on_delete=models.SET_NULL, related_name="payment")
    created_at = models.DateTimeField(auto_now_add=True)


class OrderStatusLog(models.Model):
    """One row per status change, so the buyer sees a real timeline (FR-9)."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_log")
    status = models.CharField(max_length=20, choices=Order.Status.choices)
    note = models.CharField(max_length=255, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_status_changes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self):
        return f"Order #{self.order_id}: {self.get_status_display()}"


class Refund(models.Model):
    """Money returned to the buyer. Partial refunds reduce what the invoice asks for."""

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="refunds")
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    reason = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="refunds_recorded",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"Refund {self.amount} on order #{self.order_id}"


class OrderConfirmation(models.Model):
    """Tracks the confirmation email for one order so a failed send can be retried."""

    class State(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        SKIPPED = "skipped", "Skipped (no address to send to)"
        FAILED = "failed", "Failed"

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="confirmation")
    state = models.CharField(max_length=10, choices=State.choices, default=State.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=100, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    # The SMS confirmation is tracked separately so an email problem never blocks it, or the reverse.
    sms_state = models.CharField(max_length=10, choices=State.choices, default=State.PENDING, db_index=True)
    sms_attempts = models.PositiveSmallIntegerField(default=0)
    sms_last_error = models.CharField(max_length=100, blank=True)
    sms_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
