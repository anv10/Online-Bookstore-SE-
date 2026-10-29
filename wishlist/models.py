from django.conf import settings
from django.db import models


class WishlistItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist_items")
    book = models.ForeignKey("catalog.Book", on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "book"], name="unique_book_per_wishlist")]
        ordering = ["-added_at", "-pk"]

    def __str__(self):
        return f"{self.user_id}: {self.book_id}"
