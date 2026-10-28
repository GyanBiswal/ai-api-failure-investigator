"""Check request payloads against the sample API's known rules.

Ordinary Python on purpose: these are exact, known requirements,
so there is no reason to ask an LLM.
"""

# (METHOD, endpoint) -> {field: required_type}
RULES = {
    ("POST", "/users"): {"name": str, "email": str},
    ("POST", "/orders"): {"user_id": int, "item": str, "quantity": int},
}


def validate_request(method: str, endpoint: str, payload) -> dict:
    """Return {"checked", "valid", "issues"}.

    checked=False means we have no rules for this endpoint, so we
    make no claim about validity (valid is None, not True).
    """
    key = (method.upper(), endpoint.rstrip("/") or "/")
    rules = RULES.get(key)
    if rules is None:
        return {"checked": False, "valid": None, "issues": []}

    if not isinstance(payload, dict):
        return {
            "checked": True,
            "valid": False,
            "issues": [{"field": "(body)", "problem": "not_an_object", "got": type(payload).__name__}],
        }

    issues = []
    for field, expected in rules.items():
        if field not in payload:
            issues.append({"field": field, "problem": "missing", "expected": expected.__name__})
            continue
        value = payload[field]
        if value is None:
            issues.append({"field": field, "problem": "null_value", "expected": expected.__name__})
        elif type(value) is not expected:  # exact check, so True is not accepted as int
            issues.append({
                "field": field,
                "problem": "wrong_type",
                "expected": expected.__name__,
                "got": type(value).__name__,
            })
    return {"checked": True, "valid": not issues, "issues": issues}