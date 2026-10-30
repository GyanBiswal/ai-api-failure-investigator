from pathlib import Path

from streamlit.testing.v1 import AppTest

from ui_helpers import build_failure, outcome_label

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_endpoint_is_required():
    failure, problem = build_failure("GET", "   ", 500, "", "", "")
    assert failure is None and "endpoint" in problem.lower()


def test_values_are_trimmed_and_a_malformed_body_is_kept():
    failure, problem = build_failure("POST", " /orders ", "500", ' {"quantity": ', "  log  ", "")
    assert problem is None
    assert failure["endpoint"] == "/orders"
    assert failure["status_code"] == 500
    assert failure["request_body"] == '{"quantity":'
    assert failure["log_text"] == "log"


def test_outcome_labels():
    base = {"infra_error": False, "root_cause_correct": True, "uncertainty_ok": None}
    assert outcome_label(base) == "correct"
    assert outcome_label({**base, "root_cause_correct": False}) == "wrong"
    assert outcome_label({**base, "root_cause_correct": None, "uncertainty_ok": True}) == "uncertain-ok"
    assert outcome_label({**base, "root_cause_correct": None, "uncertainty_ok": False}) == "uncertain-miss"
    assert outcome_label({**base, "infra_error": True}) == "error"


def test_app_loads_without_errors():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception