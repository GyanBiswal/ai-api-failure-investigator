"""Deterministic checks on the LLM's report.

The LLM proposes a diagnosis; this code decides how far to trust it.
  1. Every evidence item is checked against the real tool results.
  2. Confidence can only be lowered by these checks, never raised.
"""
import json
import re

LEVELS = ["low", "medium", "high"]

# Which tools can legitimately back each kind of evidence.
SOURCE_TOOLS = {
    "log": {"analyze_log_text", "search_logs", "read_log_file"},
    "code": {"read_source_code", "search_source_code"},
    "request_validation": {"validate_request_payload"},
}


def _lowest(*levels: str) -> str:
    return min(levels, key=LEVELS.index)

FILE_RE = re.compile(r"[\w./-]+\.(?:py|go|js|ts|java|rb|php|json|ya?ml|log)\b")


def ungrounded_files(report: dict, tool_log: list) -> list:
    """File names mentioned in the report's prose that no tool result ever showed."""
    seen_text = " ".join(str(entry["result"]) for entry in tool_log)
    text = " ".join([report["root_cause"], report["recommended_fix"], report["verification_test"]])
    return sorted({name for name in FILE_RE.findall(text) if name not in seen_text})


def _matches(data, file: str, line: int) -> bool:
    """True if a tool result shows this exact file and line
    (as a search hit, a traceback frame, or inside a line range that was read)."""
    if isinstance(data, list):
        return any(_matches(item, file, line) for item in data)
    if not isinstance(data, dict):
        return False
    if data.get("file") == file:
        if data.get("line") == line:
            return True
        start, end = data.get("start_line"), data.get("end_line")
        if isinstance(start, int) and isinstance(end, int) and start <= line <= end:
            return True
    return any(_matches(frame, file, line) for frame in data.get("frames") or [])


def _seen_by_tools(file: str, line: int, tool_log: list) -> bool:
    for entry in tool_log:
        try:
            data = json.loads(entry["result"])
        except (TypeError, ValueError):
            continue
        if _matches(data, file, line):
            return True
    return False


def check_evidence(item: dict, tools_used: set, tool_log: list) -> tuple:
    """Return (verified, note) for one evidence item."""
    source = item.get("source")
    if source == "user_input":
        return True, "taken from the submitted request"

    allowed = SOURCE_TOOLS.get(source)
    if not allowed or not (allowed & tools_used):
        return False, f"no matching tool was run for source '{source}'"

    file, line = item.get("file"), item.get("line")
    if line and not file:
        return False, "a line number was given without a file"
    if file and line and not _seen_by_tools(file, line, tool_log):
        return False, f"{file}:{line} does not appear in any tool result"
    return True, "backed by a tool result"


def verify_diagnosis(report: dict, failure: dict, tool_log: list, stop_reason: str) -> dict:
    """Annotate the evidence and cap the confidence. Returns the same report dict."""
    tools_used = {entry["tool"] for entry in tool_log}
    notes = []

    for item in report["evidence"]:
        item["verified"], item["verification_note"] = check_evidence(item, tools_used, tool_log)

    # "Pointer" evidence = verified evidence that points at a file and line, or at a
    # request-validation finding. A note like "search found no matches" does not count.
    pointers = [
        e for e in report["evidence"]
        if e["verified"] and e["source"] != "user_input"
        and ((e.get("file") and e.get("line")) or e["source"] == "request_validation")
    ]
    unverified = [e for e in report["evidence"] if not e["verified"]]

    ceiling = "high"
    if not pointers:
        ceiling = "low"
        notes.append("No verified evidence points to a specific file and line or a failed request validation.")
    elif unverified:
        ceiling = _lowest(ceiling, "medium")
        notes.append(f"{len(unverified)} evidence item(s) could not be verified against tool results.")

    invented = ungrounded_files(report, tool_log)
    if invented:
        ceiling = _lowest(ceiling, "medium")
        notes.append("The report mentions file names that no tool result showed: " + ", ".join(invented) + ".")

    if stop_reason == "step_limit":
        ceiling = _lowest(ceiling, "medium")
        notes.append("The investigation hit the step limit before finishing.")
    if stop_reason == "error":
        ceiling = "low"
        notes.append("The investigation ended with an error.")
    if not (failure.get("log_text") or "").strip():
        ceiling = _lowest(ceiling, "medium")
        notes.append("No log or traceback was submitted for this request, so stored logs may describe a different incident.")

    report["confidence_llm"] = report["confidence"]
    report["confidence"] = _lowest(report["confidence"], ceiling)
    report["confidence_notes"] = notes
    return report