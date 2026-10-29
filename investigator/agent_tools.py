"""LangChain tool wrappers around the Phase 1 tools."""
import json

from langchain_core.tools import tool

from tools.code_inspector import CodeInspectorError, read_code, search_code
from tools.log_analyzer import analyze_log, search_error_logs
from tools.request_validator import validate_request


@tool
def analyze_log_text(log_text: str) -> str:
    """Parse a log excerpt or traceback and extract the error type, error message,
    file, line number and function where the error was raised."""
    return json.dumps(analyze_log(log_text))


@tool
def search_logs(keyword: str) -> str:
    """Search the stored application log files for a keyword. Returns matching lines
    with the log file name and line number."""
    return json.dumps(search_error_logs(keyword))


@tool
def search_source_code(keyword: str) -> str:
    """Search the sample service source code for a keyword. Returns matching lines
    with file path and line number."""
    return json.dumps(search_code(keyword))


@tool
def read_source_code(path: str, start_line: int = 1, end_line: int = 60) -> str:
    """Read lines from one source file of the sample service, with real line numbers.
    The path looks like sample_service/controllers/user_controller.py."""
    try:
        result = read_code(path, start_line, end_line)
    except CodeInspectorError as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({
        "file": result["file"],
        "start_line": result["start_line"],
        "end_line": result["end_line"],
        "numbered": result["numbered"],
    })


@tool
def validate_request_payload(method: str, endpoint: str, payload_json: str) -> str:
    """Check a JSON request body against the known rules for an endpoint, such as
    missing fields, null values and wrong types. Only use when a request body was provided."""
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"payload_json is not valid JSON: {exc}"})
    return json.dumps(validate_request(method, endpoint, payload))


TOOLS = [analyze_log_text, search_logs, search_source_code, read_source_code, validate_request_payload]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}