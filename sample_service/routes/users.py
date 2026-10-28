"""User routes for the sample API (plain functions, no web framework)."""
from sample_service.controllers import user_controller


def handle_get_user(user_id):
    """GET /users/<id>"""
    return user_controller.get_user(user_id)


def handle_create_user(payload):
    """POST /users"""
    return user_controller.create_user(payload)