from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User
from catalog.models import Book
from reviews.models import Review


class ReviewModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("r@example.com", "pw")
        self.book = Book.objects.create(title="A", author="X", isbn="9780000000004", price=Decimal("3"))

    def test_one_review_per_user_per_book(self):
        Review.objects.create(book=self.book, user=self.user, rating=5)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Review.objects.create(book=self.book, user=self.user, rating=4)

    def test_rating_range(self):
        with self.assertRaises(ValidationError):
            Review(book=self.book, user=self.user, rating=6).full_clean()
