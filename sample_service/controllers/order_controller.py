"""Order controller for the sample API."""

ORDERS = {}


def create_order(payload):
    """Create an order. Expects user_id (int), item (str), quantity (int)."""
    total = payload["quantity"] * 10
    order_id = len(ORDERS) + 1
    ORDERS[order_id] = {
        "id": order_id,
        "user_id": payload["user_id"],
        "item": payload["item"],
        "total": total,
    }
    return ORDERS[order_id]


def get_order(order_id):
    """Return an order by id."""
    return ORDERS[order_id]