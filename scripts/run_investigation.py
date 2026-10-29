"""Run the agent on a sample failure:  python -m scripts.run_investigation 1"""
import json
import sys

from investigator.agent import investigate

CASES = {
    "1": {  # missing user: a None value is indexed
        "method": "GET", "endpoint": "/users/99", "status_code": 500,
        "log_text": (
            "2026-10-01 10:15:40 ERROR GET /users/99 status=500\n"
            "Traceback (most recent call last):\n"
            '  File "sample_service/routes/users.py", line 7, in handle_get_user\n'
            "    return user_controller.get_user(user_id)\n"
            '  File "sample_service/controllers/user_controller.py", line 12, in get_user\n'
            '    return user["name"]\n'
            "TypeError: 'NoneType' object is not subscriptable"
        ),
    },
    "2": {  # null quantity in the request body
        "method": "POST", "endpoint": "/orders", "status_code": 500,
        "request_body": '{"user_id": 1, "item": "pen", "quantity": null}',
        "log_text": (
            "2026-10-01 10:25:48 ERROR POST /orders status=500\n"
            "Traceback (most recent call last):\n"
            '  File "sample_service/routes/orders.py", line 7, in handle_create_order\n'
            "    return order_controller.create_order(payload)\n"
            '  File "sample_service/controllers/order_controller.py", line 8, in create_order\n'
            '    total = payload["quantity"] * 10\n'
            "TypeError: unsupported operand type(s) for *: 'NoneType' and 'int'"
        ),
    },
    "3": {  # no logs at all: tests how the agent handles missing evidence
        "method": "POST", "endpoint": "/users", "status_code": 500,
        "request_body": '{"email": "x@example.com"}',
    },
    "4": {  # truncated log: an error line but no traceback
        "method": "POST", "endpoint": "/orders", "status_code": 500,
        "log_text": "2026-10-01 10:25:48 ERROR POST /orders status=500 (traceback missing)",
    },
    "5": {  # a failure the sample code cannot explain
        "method": "GET", "endpoint": "/health", "status_code": 503,
        "log_text": "upstream connect error or disconnect/reset before headers",
    },
}

if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else "1"
    if key not in CASES:
        raise SystemExit(f"Choose one of: {', '.join(CASES)}")
    version = sys.argv[2] if len(sys.argv) > 2 else "v2"
    result = investigate(CASES[key], prompt_version=version)
    del result["tool_log"]  # long; tools_used already shows which tools ran
    print(json.dumps(result, indent=2))