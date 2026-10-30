"""Evaluation metrics. Plain Python only: no LLM judges the results.

Plain-language definitions
  root_cause_correct   The report cites the expected file and line (+-1 line) in VERIFIED
                       evidence AND its root-cause sentence contains the expected keywords.
  tools_ok             The agent used the kinds of tools the case needed.
  evidence_exists      Of the file+line citations in reports, how many really exist on disk.
  evidence_grounded    Of all evidence items, how many were verified against real tool results.
  uncertainty_ok       (unexplainable cases only) the report says low confidence.
  overconfident_wrong  Confidence was "high" but the answer was wrong, or should have been uncertain.
"""
import re
from pathlib import Path

from tools.code_inspector import CodeInspectorError, read_code
from tools.log_analyzer import LOGS_DIR

# Keyword groups in cases.json may use these shortcuts (any one term matches).
SYNONYMS = {
    "@absent": ["missing", "absent", "omit", "not provided", "not supplied", "not sent",
                "not include", "not contain", "not have", "not present", "not exist",
                "non-existent", "nonexistent", "not in", "unknown", "not found", "no such",
                "lack", "without", "required"],
    "@nullish": ["null", "none", "nonetype"],
    "@notobject": ["list", "array", "not a dict", "not an object", "not a json object",
                   "not a mapping", "non-dict", "non-object", "not a dictionary"],
    "@badtype": ["dict", "object", "mapping", "wrong type", "wrong data type", "not a number",
                 "not an integer", "not numeric", "non-numeric", "invalid type", "incorrect type"],
}

CODE_TOOLS = ["read_source_code", "search_source_code"]
# Each inner list is "any one of these tools"; every inner list must be satisfied.
REQUIRED_TOOL_GROUPS = {
    "full_log": [["analyze_log_text"], CODE_TOOLS],
    "no_log": [CODE_TOOLS],
    "partial_log": [["search_logs", "read_log_file"], CODE_TOOLS],
    "silent": [CODE_TOOLS],
    "unknown": [CODE_TOOLS],
}


def _norm(text: str) -> str:
    """Lowercase and turn every non-word character (hyphens of any kind, quotes, punctuation) into a space."""
    return re.sub(r"\W+", " ", text.lower()).strip()


def _terms(group):
    terms = []
    for item in group:
        terms.extend(SYNONYMS.get(item, [item]))
    return [_norm(term) for term in terms]


def keywords_ok(root_cause: str, keyword_groups: list) -> tuple:
    """Every keyword group must have at least one term inside the root-cause text."""
    text = _norm(root_cause)
    missing = [group for group in keyword_groups if not any(t in text for t in _terms(group))]
    return not missing, missing

def location_ok(evidence: list, file: str, line: int, tolerance: int = 1) -> bool:
    """Is the expected file/line cited by VERIFIED evidence (within +-tolerance lines)?"""
    return any(
        e.get("verified") and e.get("file") == file and e.get("line") is not None
        and abs(e["line"] - line) <= tolerance
        for e in evidence
    )


def location_exists(file: str, line: int) -> bool:
    """Does this file and line really exist? Checked on disk, independent of the agent's tools."""
    if file.endswith(".log"):
        path = LOGS_DIR / Path(file).name
        return path.is_file() and 1 <= line <= len(path.read_text(encoding="utf-8").splitlines())
    try:
        read_code(file, line, line)
        return True
    except CodeInspectorError:
        return False


def check_tools(case: dict, tools_used: list) -> tuple:
    groups = [list(g) for g in REQUIRED_TOOL_GROUPS[case["category"]]]
    if case.get("expects_validator"):
        groups.append(["validate_request_payload"])
    missing = [group for group in groups if not set(group) & set(tools_used)]
    return not missing, missing


def _short(text, limit=160):
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "..."


def score_case(case: dict, result: dict) -> dict:
    report = result["diagnosis"]
    evidence = report.get("evidence", [])
    expected = case["expected"]
    confidence = report.get("confidence", "low")
    reasons = []

    infra_error = bool(result.get("error"))
    if infra_error:
        reasons.append("infrastructure error: " + _short(result.get("error")))

    located = [e for e in evidence if e.get("file") and e.get("line")]
    existing = sum(1 for e in located if location_exists(e["file"], e["line"]))

    tools_pass, tools_missing = check_tools(case, result.get("tools_used", []))
    if not tools_pass:
        reasons.append("required tools not used (any one of each): " + "; ".join("/".join(g) for g in tools_missing))

    if expected.get("unknown"):
        correct = None
        uncertainty = confidence == "low"
        wrong = not uncertainty
        if wrong:
            reasons.append(f"should be uncertain (low confidence) but confidence={confidence}")
    else:
        loc = location_ok(evidence, expected["file"], expected["line"])
        kw, missing_kw = keywords_ok(report.get("root_cause", ""), expected["keywords"])
        correct = loc and kw
        uncertainty = None
        wrong = not correct
        if not loc:
            reasons.append(f"no verified evidence at {expected['file']}:{expected['line']} (+-1)")
        if not kw:
            reasons.append("root cause lacks expected keywords: " + "; ".join(g[0] for g in missing_kw))

    overconfident = confidence == "high" and wrong
    if infra_error:  # an infrastructure failure says nothing about the prompt, so it is not scored as an answer
        correct, uncertainty, overconfident = None, None, False
        reasons = [r for r in reasons if r.startswith("infrastructure error")]
    if overconfident:
        reasons.append("overconfident: high confidence but wrong")

    return {
        "id": case["id"],
        "category": case["category"],
        "confidence": confidence,
        "root_cause_correct": correct,   # True/False, or None for unexplainable cases
        "uncertainty_ok": uncertainty,   # True/False for unexplainable cases, else None
        "tools_ok": tools_pass,
        "infra_error": infra_error,
        "overconfident": overconfident,
        "evidence_total": len(evidence),
        "evidence_grounded": sum(1 for e in evidence if e.get("verified")),
        "located_total": len(located),
        "located_existing": existing,
        "steps": result.get("steps", 0),
        "tokens": result.get("tokens", 0),
        "stop_reason": result.get("stop_reason"),
        "reasons": reasons,
    }


def _pct(part, whole):
    return round(100 * part / whole, 1) if whole else None


def summarize(scores: list) -> dict:
    n = len(scores)
    valid = [s for s in scores if not s["infra_error"]]
    known = [s for s in scores if s["root_cause_correct"] is not None]
    unknown = [s for s in scores if s["uncertainty_ok"] is not None]
    return {
        "cases": n,
        "root_cause_accuracy_pct": _pct(sum(s["root_cause_correct"] for s in known), len(known)),
        "tool_selection_pct": _pct(sum(s["tools_ok"] for s in valid), len(valid)),
        "evidence_exists_pct": _pct(sum(s["located_existing"] for s in scores), sum(s["located_total"] for s in scores)),
        "evidence_grounded_pct": _pct(sum(s["evidence_grounded"] for s in scores), sum(s["evidence_total"] for s in scores)),
        "uncertainty_handling_pct": _pct(sum(s["uncertainty_ok"] for s in unknown), len(unknown)),
        "overconfident_wrong": sum(s["overconfident"] for s in scores),
        "step_limit_hits": sum(s["stop_reason"] == "step_limit" for s in scores),
        "errors": sum(s["infra_error"] for s in scores),
        "avg_steps": round(sum(s["steps"] for s in scores) / n, 1) if n else None,
        "avg_tokens": round(sum(s["tokens"] for s in scores) / n) if n else None,
    }