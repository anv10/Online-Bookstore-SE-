from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from decimal import Decimal
from pathlib import Path
from uuid import uuid4


def book_image_path(instance, filename):
    return f"books/{uuid4().hex}{Path(filename).suffix.lower()}"



class Book(models.Model):
    title = models.CharField(max_length=255, db_index=True)
    author = models.CharField(max_length=255, db_index=True)
    isbn = models.CharField(max_length=13, db_index=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, blank=True, db_index=True)
    price = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    stock = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Status(models.TextChoices):
        PENDING = "pending", "Pending approval"
        APPROVED = "approved", "Approved"
        SUSPENDED = "suspended", "Suspended"
        REMOVED = "removed", "Removed"

    seller = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="listings")
    condition = models.CharField(max_length=8, choices=[("new", "New"), ("used", "Used")], default="new")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    @property
    def cover_url(self):
        image = next(iter(self.images.all()), None)
        return image.image.url if image else ""

    def __str__(self):
        return self.title


class BookImage(models.Model):
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=book_image_path)

    class Meta:
        ordering = ["pk"]


class ModerationEvent(models.Model):
    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name="moderation_events")
    admin = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    previous_status = models.CharField(max_length=10)
    new_status = models.CharField(max_length=10, choices=Book.Status.choices)
    reason = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        default_permissions = ("view",)


class AdminChallenge(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    code_hash = models.CharField(max_length=256, blank=True)
    session_hash = models.CharField(max_length=64, blank=True)
    expires_at = models.DateTimeField(null=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    window_started = models.DateTimeField()
    requests = models.PositiveSmallIntegerField(default=0)

    class Meta:
        default_permissions = ()


class ListingFlag(models.Model):
    """A buyer's report against a listing (FR-12_ST01).

    Moderators work the open flags in the review queue. A decision on the
    listing settles every open flag on it, so the queue drains as listings
    are approved, suspended or removed.
    """

    class State(models.TextChoices):
        OPEN = "open", "Open"
        UPHELD = "upheld", "Upheld"
        DISMISSED = "dismissed", "Dismissed"

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="flags")
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="listing_flags")
    reason = models.CharField(max_length=1000)
    state = models.CharField(max_length=10, choices=State.choices, default=State.OPEN, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="flag_decisions"
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        default_permissions = ("view",)
        constraints = [
            models.UniqueConstraint(
                fields=["book", "reporter"],
                condition=models.Q(state="open"),
                name="one_open_flag_per_reporter",
            )
        ]

    def __str__(self):
        return f"{self.book_id} flagged by {self.reporter_id}"
