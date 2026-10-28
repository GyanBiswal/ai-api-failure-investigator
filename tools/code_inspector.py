"""Safe, read-only access to the sample codebase.

Safety rules:
  1. Only files inside sample_service/ can be read.
  2. Absolute paths are rejected.
  3. The path is fully resolved (this collapses '..' and symlinks) and
     THEN checked to still be inside the allowed folder.
  4. Only a small set of text file types is allowed.
  5. Output size is capped.
"""
from pathlib import Path

ALLOWED_ROOT = Path(__file__).resolve().parent.parent / "sample_service"
ALLOWED_EXTENSIONS = {".py", ".log", ".json", ".txt", ".md"}
MAX_LINES = 200


class CodeInspectorError(Exception):
    """Raised when a request is unsafe or cannot be served."""


def _resolve_safe(path_str: str, allowed_root: Path) -> Path:
    root = allowed_root.resolve()
    base = root.parent  # paths look like "sample_service/controllers/x.py"

    if not path_str or not path_str.strip():
        raise CodeInspectorError("Path is empty")
    candidate = Path(path_str)
    if candidate.is_absolute():
        raise CodeInspectorError("Absolute paths are not allowed")

    resolved = (base / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise CodeInspectorError("Access denied: path is outside the sample service")
    if resolved.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise CodeInspectorError(f"File type not allowed: {resolved.suffix or '(none)'}")
    if not resolved.is_file():
        raise CodeInspectorError(f"File not found: {path_str}")
    return resolved


def search_code(keyword: str, allowed_root: Path = ALLOWED_ROOT, max_results: int = 20) -> list:
    """Find lines containing the keyword in the sample service's .py files."""
    if not keyword or not keyword.strip():
        return []
    root = allowed_root.resolve()
    base = root.parent
    needle = keyword.lower()
    results = []
    for py_file in sorted(root.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        for number, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), start=1):
            if needle in line.lower():
                results.append({
                    "file": py_file.relative_to(base).as_posix(),
                    "line": number,
                    "text": line.rstrip(),
                })
                if len(results) >= max_results:
                    return results
    return results


def read_code(path: str, start_line: int = 1, end_line: int | None = None,
              allowed_root: Path = ALLOWED_ROOT) -> dict:
    """Read a line range from one file, returning real line numbers."""
    resolved = _resolve_safe(path, allowed_root)
    base = allowed_root.resolve().parent
    all_lines = resolved.read_text(encoding="utf-8").splitlines()
    total = len(all_lines)

    start = max(1, start_line)
    end = total if end_line is None else min(end_line, total)
    end = min(end, start + MAX_LINES - 1)
    if start > end:
        raise CodeInspectorError(f"Invalid line range (file has {total} lines)")

    lines = [{"line": n, "text": all_lines[n - 1]} for n in range(start, end + 1)]
    return {
        "file": resolved.relative_to(base).as_posix(),
        "start_line": start,
        "end_line": end,
        "total_lines": total,
        "lines": lines,
        "numbered": "\n".join(f"{item['line']}: {item['text']}" for item in lines),
    }