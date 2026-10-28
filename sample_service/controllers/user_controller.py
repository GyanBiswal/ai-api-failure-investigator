"""User controller for the sample API."""

USERS = {
    1: {"id": 1, "name": "Asha", "email": "asha@example.com"},
    2: {"id": 2, "name": "Ravi", "email": "ravi@example.com"},
}


def get_user(user_id):
    """Return a user's name by id."""
    user = USERS.get(user_id)
    return user["name"]


def create_user(payload):
    """Create a user from a JSON payload."""
    name = payload["name"]
    email = payload["email"]
    new_id = max(USERS) + 1
    USERS[new_id] = {"id": new_id, "name": name, "email": email}
    return USERS[new_id]