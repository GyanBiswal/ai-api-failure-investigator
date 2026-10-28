import pytest

from tools.code_inspector import CodeInspectorError, read_code, search_code
from tools.log_analyzer import analyze_log, search_error_logs
from tools.request_validator import validate_request

USER_TRACEBACK = """2026-10-01 10:15:40 ERROR GET /users/99 status=500
Traceback (most recent call last):
  File "sample_service/routes/users.py", line 7, in handle_get_user
    return user_controller.get_user(user_id)
  File "sample_service/controllers/user_controller.py", line 12, in get_user
    return user["name"]
TypeError: 'NoneType' object is not subscriptable
"""


# ---------- log analyzer ----------
def test_analyze_log_traceback():
    result = analyze_log(USER_TRACEBACK)
    assert result["found"] is True
    assert result["error_type"] == "TypeError"
    assert result["error_message"] == "'NoneType' object is not subscriptable"
    assert result["file"] == "sample_service/controllers/user_controller.py"
    assert result["line"] == 12
    assert result["function"] == "get_user"
    assert len(result["frames"]) == 2


def test_analyze_log_single_line_without_traceback():
    result = analyze_log("ValidationError: quantity must be an integer")
    assert result["found"] is True
    assert result["error_type"] == "ValidationError"
    assert result["file"] is None
    assert result["line"] is None


def test_analyze_log_no_error():
    assert analyze_log("INFO all good, nothing to see")["found"] is False


def test_search_error_logs_finds_keyword():
    results = search_error_logs("KeyError")
    assert len(results) >= 2
    assert all(r["file"] == "app.log" and isinstance(r["line"], int) for r in results)


def test_search_error_logs_empty_keyword():
    assert search_error_logs("   ") == []


# ---------- code inspector ----------
def test_search_code_finds_line_with_number():
    results = search_code('payload["quantity"]')
    assert len(results) == 1
    assert results[0]["file"] == "sample_service/controllers/order_controller.py"
    assert results[0]["line"] == 8


def test_read_code_returns_real_line_numbers():
    result = read_code("sample_service/controllers/user_controller.py", 12, 12)
    assert result["lines"][0]["line"] == 12
    assert 'user["name"]' in result["lines"][0]["text"]
    assert result["numbered"].startswith("12: ")


def test_read_code_missing_file():
    with pytest.raises(CodeInspectorError):
        read_code("sample_service/controllers/does_not_exist.py")


@pytest.mark.parametrize("bad_path", [
    "../requirements.txt",
    "sample_service/../requirements.txt",
    "sample_service/../../etc/passwd",
    "/etc/passwd",
    "",
])
def test_read_code_blocks_unsafe_paths(bad_path):
    with pytest.raises(CodeInspectorError):
        read_code(bad_path)


# ---------- request validator ----------
def test_validator_accepts_valid_order():
    result = validate_request("POST", "/orders", {"user_id": 1, "item": "pen", "quantity": 2})
    assert result["valid"] is True
    assert result["issues"] == []


def test_validator_detects_missing_field():
    result = validate_request("POST", "/orders", {"user_id": 1, "item": "pen"})
    assert result["valid"] is False
    assert result["issues"][0]["field"] == "quantity"
    assert result["issues"][0]["problem"] == "missing"


def test_validator_detects_wrong_type_and_rejects_bool():
    result = validate_request("POST", "/orders", {"user_id": True, "item": "pen", "quantity": "3"})
    problems = {i["field"]: i["got"] for i in result["issues"]}
    assert problems == {"user_id": "bool", "quantity": "str"}


def test_validator_unknown_endpoint_makes_no_claim():
    result = validate_request("GET", "/health", {})
    assert result["checked"] is False
    assert result["valid"] is None


def test_validator_rejects_non_object_body():
    result = validate_request("POST", "/users", ["not", "a", "dict"])
    assert result["valid"] is False
    assert result["issues"][0]["problem"] == "not_an_object"