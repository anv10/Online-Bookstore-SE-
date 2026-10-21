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
