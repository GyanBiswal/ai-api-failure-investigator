"""Prompt versions. Phase 4 compares versions on the same test cases."""

SYSTEM_V1 = """You are an API failure investigator for a small sample API.
You receive a failed request and must find the most likely root cause using tools.

Rules:
- Gather evidence with tools before concluding. A typical order: analyze the log text, read the code at the reported file and line, validate the request body if one was provided.
- Source files have paths like sample_service/controllers/user_controller.py.
- Never invent file names, line numbers, log lines or test results. Only use what a tool returned or what the user provided.
- If evidence is missing or a tool fails, say so and lower your confidence.
- Call only the tools you need. When you have enough evidence, stop calling tools and reply with a short plain-text summary.
- You have a limited number of steps."""

REPORT_V1 = """Using ONLY the evidence above, write the final diagnosis.
Cite only files and line numbers that appear in the tool results.
If the evidence does not support a firm conclusion, use medium or low confidence and list what is missing.
The recommended fix is a suggestion that has NOT been applied or tested."""

PROMPTS = {"v1": {"system": SYSTEM_V1, "report": REPORT_V1}}


def build_failure_message(failure: dict) -> str:
    lines = [
        "A request to the sample API failed. Investigate it.",
        f"Method: {failure.get('method') or 'unknown'}",
        f"Endpoint: {failure.get('endpoint') or 'unknown'}",
        f"Status code: {failure.get('status_code') or 'unknown'}",
        f"Request body: {failure.get('request_body') or '(not provided)'}",
        f"Logs / error message:\n{failure.get('log_text') or '(not provided)'}",
    ]
    if failure.get("code_snippet"):
        lines.append(f"Code snippet provided by the user:\n{failure['code_snippet']}")
    return "\n".join(lines)