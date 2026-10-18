from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from catalog.models import Book


class BookModelTests(TestCase):
    def test_isbn_unique(self):
        Book.objects.create(title="A", author="X", isbn="9780000000001", price=Decimal("9.99"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Book.objects.create(title="B", author="Y", isbn="9780000000001", price=Decimal("5.00"))

    def test_str(self):
        self.assertEqual(str(Book(title="Dune")), "Dune")
