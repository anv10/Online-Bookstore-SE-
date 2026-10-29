"""The steps a buyer sees on the order page (FR-9)."""

from .models import Order

# Label and how far along the order is when it reaches that step.
STEPS = ("Placed", "Shipped", "Out for delivery", "Delivered")
PROGRESS = {
    Order.Status.PENDING: 0,
    Order.Status.PAID: 0,
    Order.Status.SHIPPED: 1,
    Order.Status.OUT_FOR_DELIVERY: 2,
    Order.Status.DELIVERED: 3,
}


def tracking_steps(order):
    """Steps with a state of done, current or upcoming. Cancelled orders have no tracker."""
    if order.status not in PROGRESS:
        return []
    reached = PROGRESS[order.status]
    delivered = order.status == Order.Status.DELIVERED
    steps = []
    for index, label in enumerate(STEPS):
        if index < reached or (delivered and index == reached):
            state = "done"
        elif index == reached:
            state = "current"
        else:
            state = "upcoming"
        steps.append({"label": label, "state": state})
    return steps
