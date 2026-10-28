"""Order routes for the sample API (plain functions, no web framework)."""
from sample_service.controllers import order_controller


def handle_create_order(payload):
    """POST /orders"""
    return order_controller.create_order(payload)


def handle_get_order(order_id):
    """GET /orders/<id>"""
    return order_controller.get_order(order_id)