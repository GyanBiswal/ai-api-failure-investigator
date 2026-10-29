import json

from investigator.verify import verify_diagnosis

CODE_FILE = "sample_service/controllers/user_controller.py"
FAILURE = {"log_text": "TypeError: 'NoneType' object is not subscriptable"}

READ_ENTRY = {
    "tool": "read_source_code", "args": {},
    "result": json.dumps({"file": CODE_FILE, "start_line": 1, "end_line": 60, "numbered": "..."}),
}
SEARCH_ENTRY = {
    "tool": "search_logs", "args": {},
    "result": json.dumps([{"file": "app.log", "line": 10, "text": "ERROR POST /users status=500"}]),
}
VALIDATE_ENTRY = {"tool": "validate_request_payload", "args": {}, "result": json.dumps({"checked": True})}


def report(evidence, confidence="high"):
    return {"root_cause": "x", "confidence": confidence, "evidence": evidence,
            "recommended_fix": "f", "verification_test": "t",
            "missing_information": [], "assumptions": []}


def code_item(line):
    return {"source": "code", "file": CODE_FILE, "line": line, "detail": "d"}


def test_grounded_evidence_keeps_confidence():
    out = verify_diagnosis(report([code_item(12)]), FAILURE, [READ_ENTRY], "enough_evidence")
    assert out["evidence"][0]["verified"] is True
    assert out["confidence"] == "high"
    assert out["confidence_notes"] == []


def test_fabricated_line_is_flagged_and_confidence_drops_to_low():
    out = verify_diagnosis(report([code_item(999)]), FAILURE, [READ_ENTRY], "enough_evidence")
    assert out["evidence"][0]["verified"] is False
    assert out["confidence"] == "low"


def test_mixed_evidence_caps_at_medium():
    out = verify_diagnosis(report([code_item(12), code_item(999)]), FAILURE, [READ_ENTRY], "enough_evidence")
    assert out["confidence"] == "medium"


def test_source_without_matching_tool_is_unverified():
    item = {"source": "request_validation", "file": None, "line": None, "detail": "d"}
    out = verify_diagnosis(report([code_item(12), item]), FAILURE, [READ_ENTRY], "enough_evidence")
    assert out["evidence"][1]["verified"] is False
    assert out["confidence"] == "medium"


def test_request_validation_verified_when_validator_ran():
    item = {"source": "request_validation", "file": None, "line": None, "detail": "d"}
    out = verify_diagnosis(report([code_item(12), item]), FAILURE, [READ_ENTRY, VALIDATE_ENTRY], "enough_evidence")
    assert all(e["verified"] for e in out["evidence"])
    assert out["confidence"] == "high"


def test_log_search_hit_is_verified():
    item = {"source": "log", "file": "app.log", "line": 10, "detail": "d"}
    out = verify_diagnosis(report([item]), FAILURE, [SEARCH_ENTRY], "enough_evidence")
    assert out["evidence"][0]["verified"] is True


def test_user_input_alone_does_not_support_high_confidence():
    item = {"source": "user_input", "file": None, "line": None, "detail": "d"}
    out = verify_diagnosis(report([item]), FAILURE, [], "enough_evidence")
    assert out["evidence"][0]["verified"] is True
    assert out["confidence"] == "low"


def test_missing_user_log_caps_at_medium():
    out = verify_diagnosis(report([code_item(12)]), {"log_text": ""}, [READ_ENTRY], "enough_evidence")
    assert out["confidence"] == "medium"
    assert any("No log" in note for note in out["confidence_notes"])


def test_step_limit_caps_at_medium():
    out = verify_diagnosis(report([code_item(12)]), FAILURE, [READ_ENTRY], "step_limit")
    assert out["confidence"] == "medium"


def test_verification_never_raises_confidence():
    out = verify_diagnosis(report([code_item(12)], confidence="low"), FAILURE, [READ_ENTRY], "enough_evidence")
    assert out["confidence"] == "low"
    assert out["confidence_llm"] == "low"

def test_invented_file_name_in_fix_is_flagged():
    r = report([code_item(12)])
    r["recommended_fix"] = "Edit health_handler.go and sample_service/controllers/user_controller.py"
    out = verify_diagnosis(r, FAILURE, [READ_ENTRY], "enough_evidence")
    assert out["confidence"] == "medium"
    assert any("health_handler.go" in note for note in out["confidence_notes"])
    assert not any("user_controller.py" in note for note in out["confidence_notes"])

def test_no_match_evidence_alone_caps_at_low():
    item = {"source": "code", "file": None, "line": None, "detail": "search found no matches"}
    empty_search = {"tool": "search_source_code", "args": {}, "result": "[]"}
    out = verify_diagnosis(report([item]), FAILURE, [empty_search], "enough_evidence")
    assert out["evidence"][0]["verified"] is True
    assert out["confidence"] == "low"