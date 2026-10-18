from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User
from cart.models import Cart, CartItem
from catalog.models import Book


class CartModelTests(TestCase):
    def test_one_row_per_book_in_cart(self):
        user = User.objects.create_user("c@example.com", "pw")
        book = Book.objects.create(title="A", author="X", isbn="9780000000002", price=Decimal("1"))
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, book=book)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CartItem.objects.create(cart=cart, book=book)
