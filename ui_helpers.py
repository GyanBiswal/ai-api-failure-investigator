"""Pure helpers for app.py, kept separate so they can be tested without Streamlit."""


def build_failure(method, endpoint, status_code, request_body, log_text, code_snippet):
    """Clean the form values. Returns (failure_dict, None) or (None, error_message).

    The request body is NOT checked for valid JSON: a malformed body can itself be
    the cause of the failure, and the agent's validator tool handles it.
    """
    endpoint = (endpoint or "").strip()
    if not endpoint:
        return None, "Enter the endpoint, for example /orders."
    return {
        "method": method,
        "endpoint": endpoint,
        "status_code": int(status_code),
        "request_body": (request_body or "").strip(),
        "log_text": (log_text or "").strip(),
        "code_snippet": (code_snippet or "").strip(),
    }, None


def outcome_label(score):
    """One-word outcome for a scored evaluation case."""
    if score["infra_error"]:
        return "error"
    if score["root_cause_correct"] is not None:
        return "correct" if score["root_cause_correct"] else "wrong"
    return "uncertain-ok" if score["uncertainty_ok"] else "uncertain-miss"