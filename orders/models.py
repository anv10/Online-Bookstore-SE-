from django.conf import settings
from django.db import models

from bookstore.fields import EncryptedTextField


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Placed"
        PAID = "paid", "Paid"
        SHIPPED = "shipped", "Shipped"
        OUT_FOR_DELIVERY = "out_for_delivery", "Out for delivery"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_address = EncryptedTextField()
    created_at = models.DateTimeField(auto_now_add=True)


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
    shipping_address = EncryptedTextField()
    lines = models.JSONField(default=list)
    order = models.OneToOneField(Order, null=True, blank=True, on_delete=models.SET_NULL, related_name="payment")
    created_at = models.DateTimeField(auto_now_add=True)


class OrderConfirmation(models.Model):
    """Tracks the confirmation email for one order so a failed send can be retried."""

    class State(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        SKIPPED = "skipped", "Skipped (no email address)"
        FAILED = "failed", "Failed"

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="confirmation")
    state = models.CharField(max_length=10, choices=State.choices, default=State.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=100, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
