"""Extract structured clues from API error logs.

Plain Python, no LLM: the LLM later interprets these clues,
it never has to guess what the log literally says.
"""
import re
from pathlib import Path

LOGS_DIR = Path(__file__).resolve().parent.parent / "sample_service" / "sample_logs"

# Matches:  File "path/to/file.py", line 12, in function_name
FRAME_RE = re.compile(r'File "([^"]+)", line (\d+), in (\S+)')
# Matches:  KeyError: 'name'   or   ValidationError: some message
EXCEPTION_RE = re.compile(
    r"^([A-Za-z_][\w.]*(?:Error|Exception))(?::[ \t]*(.*))?$", re.MULTILINE
)


def analyze_log(log_text: str) -> dict:
    """Parse one failure's log text and return the key facts.

    The LAST stack frame is used as the origin, because that is
    where the exception was actually raised.
    """
    frames = [
        {"file": f, "line": int(n), "function": fn}
        for f, n, fn in FRAME_RE.findall(log_text)
    ]
    exceptions = EXCEPTION_RE.findall(log_text)

    result = {
        "found": bool(exceptions or frames),
        "error_type": None,
        "error_message": None,
        "file": None,
        "line": None,
        "function": None,
        "frames": frames,
    }
    if exceptions:
        result["error_type"], result["error_message"] = exceptions[-1]
    if frames:
        origin = frames[-1]
        result["file"] = origin["file"]
        result["line"] = origin["line"]
        result["function"] = origin["function"]
    return result


def search_error_logs(keyword: str, logs_dir: Path = LOGS_DIR, max_results: int = 20) -> list:
    """Case-insensitive keyword search across the *.log files in the logs folder.

    Only the logs folder is ever read, and the keyword is matched against
    file contents, never used as a path.
    """
    if not keyword or not keyword.strip():
        return []
    needle = keyword.lower()
    results = []
    for log_file in sorted(logs_dir.glob("*.log")):
        for number, line in enumerate(log_file.read_text(encoding="utf-8").splitlines(), start=1):
            if needle in line.lower():
                results.append({"file": log_file.name, "line": number, "text": line.rstrip()})
                if len(results) >= max_results:
                    return results
    return results

def read_log_lines(file_name: str, start_line: int = 1, end_line: int = 40,
                   logs_dir: Path = LOGS_DIR) -> dict:
    """Read a line range from one stored log file, with real line numbers.

    Only a bare file name ending in .log inside the logs folder is accepted,
    so paths like ../secret.txt are rejected.
    """
    if not file_name or Path(file_name).name != file_name or not file_name.endswith(".log"):
        raise ValueError("Provide only a log file name such as app.log")
    path = logs_dir / file_name
    if not path.is_file():
        raise ValueError(f"Log file not found: {file_name}")
    all_lines = path.read_text(encoding="utf-8").splitlines()
    total = len(all_lines)
    start = max(1, start_line)
    end = min(end_line, total, start + 59)
    if start > end:
        raise ValueError(f"Invalid line range (file has {total} lines)")
    lines = [{"line": n, "text": all_lines[n - 1]} for n in range(start, end + 1)]
    return {
        "file": file_name,
        "start_line": start,
        "end_line": end,
        "total_lines": total,
        "numbered": "\n".join(f"{item['line']}: {item['text']}" for item in lines),
    }