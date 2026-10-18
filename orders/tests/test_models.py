from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from catalog.models import Book
from orders.models import Order, OrderItem


class OrderModelTests(TestCase):
    def test_order_with_items_defaults_to_pending(self):
        user = User.objects.create_user("o@example.com", "pw")
        book = Book.objects.create(title="A", author="X", isbn="9780000000003", price=Decimal("10"))
        order = Order.objects.create(user=user, total=Decimal("20"), shipping_address="1 Main St")
        OrderItem.objects.create(order=order, book=book, quantity=2, unit_price=book.price)
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.items.count(), 1)
