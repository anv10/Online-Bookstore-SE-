from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from catalog.models import Book


class BookModelTests(TestCase):
    def test_same_isbn_supports_multiple_listings(self):
        Book.objects.create(title="A",author="X",isbn="9780132350884",price=10)
        Book.objects.create(title="A",author="X",isbn="9780132350884",price=20)
        self.assertEqual(Book.objects.count(),2)

    def test_str(self):
        self.assertEqual(str(Book(title="Dune")), "Dune")
