from orders.models import Order


def has_delivered_purchase(user, book):
    """A buyer may review a book only after an order containing it was delivered."""
    return Order.objects.filter(
        user=user,
        status=Order.Status.DELIVERED,
        items__book=book,
    ).exists()
