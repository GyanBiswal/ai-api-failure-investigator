import json
from pathlib import Path

from evaluation.metrics import (
    REQUIRED_TOOL_GROUPS, SYNONYMS, keywords_ok, location_exists, score_case, summarize,
)
from tools.code_inspector import read_code
from tools.log_analyzer import FRAME_RE

CASES = json.loads((Path(__file__).resolve().parent.parent / "evaluation" / "cases.json").read_text(encoding="utf-8"))

FILE = "sample_service/controllers/user_controller.py"
CASE = {"id": "t", "category": "full_log", "failure": {},
        "expected": {"file": FILE, "line": 12, "keywords": [["@absent", "@nullish"]]}}
UNKNOWN_CASE = {"id": "u", "category": "unknown", "failure": {}, "expected": {"unknown": True}}


def make_result(root_cause, evidence, confidence="high",
                tools=("analyze_log_text", "read_source_code"), stop="enough_evidence"):
    return {"diagnosis": {"root_cause": root_cause, "confidence": confidence, "evidence": evidence},
            "tools_used": list(tools), "steps": 3, "tokens": 5000, "stop_reason": stop, "error": None}


def ev(file, line, verified=True):
    return {"source": "code", "file": file, "line": line, "detail": "d", "verified": verified}


# ---------- the dataset itself ----------
def test_dataset_has_15_to_20_unique_cases():
    ids = [c["id"] for c in CASES]
    assert 15 <= len(ids) <= 20
    assert len(ids) == len(set(ids))
    assert all(c["category"] in REQUIRED_TOOL_GROUPS for c in CASES)


def test_expected_locations_exist_and_keyword_shortcuts_resolve():
    for case in CASES:
        expected = case["expected"]
        if expected.get("unknown"):
            continue
        read_code(expected["file"], expected["line"], expected["line"])
        for group in expected["keywords"]:
            for term in group:
                assert not term.startswith("@") or term in SYNONYMS, case["id"]


def test_traceback_code_lines_match_the_real_source():
    for case in CASES:
        lines = case["failure"].get("log_lines", [])
        for i, text in enumerate(lines):
            match = FRAME_RE.search(text)
            if not match:
                continue
            actual = read_code(match.group(1), int(match.group(2)), int(match.group(2)))["lines"][0]["text"].strip()
            assert lines[i + 1].strip() == actual, case["id"]


# ---------- scoring ----------
def test_correct_diagnosis_scores_correct():
    s = score_case(CASE, make_result("The user is None because the id is unknown", [ev(FILE, 12)]))
    assert s["root_cause_correct"] is True
    assert s["reasons"] == []


def test_line_tolerance_is_one_line():
    near = score_case(CASE, make_result("user is None", [ev(FILE, 11)]))
    far = score_case(CASE, make_result("user is None", [ev(FILE, 17)]))
    assert near["root_cause_correct"] is True
    assert far["root_cause_correct"] is False


def test_unverified_evidence_does_not_count():
    s = score_case(CASE, make_result("user is None", [ev(FILE, 12, verified=False)]))
    assert s["root_cause_correct"] is False


def test_missing_keywords_fail_with_a_reason():
    s = score_case(CASE, make_result("The server crashed", [ev(FILE, 12)], confidence="medium"))
    assert s["root_cause_correct"] is False
    assert any("keywords" in reason for reason in s["reasons"])


def test_high_confidence_and_wrong_is_overconfident():
    s = score_case(CASE, make_result("The server crashed", [ev(FILE, 12)], confidence="high"))
    assert s["overconfident"] is True


def test_unknown_case_rewards_low_confidence():
    ok = score_case(UNKNOWN_CASE, make_result("cannot tell", [], confidence="low", tools=("search_source_code",)))
    bad = score_case(UNKNOWN_CASE, make_result("it is X", [], confidence="high", tools=("search_source_code",)))
    assert ok["uncertainty_ok"] is True and ok["root_cause_correct"] is None
    assert bad["uncertainty_ok"] is False and bad["overconfident"] is True


def test_missing_required_tool_is_flagged():
    s = score_case(CASE, make_result("user is None", [ev(FILE, 12)], tools=("read_source_code",)))
    assert s["tools_ok"] is False


def test_validator_required_when_case_expects_it():
    case = dict(CASE, expects_validator=True)
    s = score_case(case, make_result("user is None", [ev(FILE, 12)]))
    assert s["tools_ok"] is False


def test_location_exists_checks_the_disk():
    assert location_exists(FILE, 12) is True
    assert location_exists(FILE, 999) is False
    assert location_exists("app.log", 10) is True
    assert location_exists("app.log", 999) is False
    assert location_exists("does_not_exist.py", 1) is False


def test_summarize_rates():
    good = score_case(CASE, make_result("user is None", [ev(FILE, 12)]))
    bad = score_case(CASE, make_result("unrelated", [ev(FILE, 99)], confidence="low"))
    summary = summarize([good, bad])
    assert summary["root_cause_accuracy_pct"] == 50.0
    assert summary["evidence_exists_pct"] == 50.0
    assert summary["overconfident_wrong"] == 0


def test_keywords_ignore_hyphen_style_and_accept_common_phrasing():
    assert keywords_ok("KeyError raised when accessing a non\u2011existent order in ORDERS", [["order"], ["@absent"]])[0]
    assert keywords_ok('KeyError from payload["email"] when the request body does not include an "email" field.',
                       [["email"], ["@absent"]])[0]


def test_infrastructure_error_is_not_scored_as_an_answer():
    result = make_result("Investigation could not be completed.", [], confidence="low", tools=())
    result["error"] = "Report generation failed: BadRequestError"
    for case in (CASE, UNKNOWN_CASE):
        s = score_case(case, result)
        assert s["infra_error"] is True
        assert s["root_cause_correct"] is None and s["uncertainty_ok"] is None
        assert s["overconfident"] is False
    summary = summarize([score_case(UNKNOWN_CASE, result)])
    assert summary["errors"] == 1
    assert summary["uncertainty_handling_pct"] is None