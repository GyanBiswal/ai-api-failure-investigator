"""MCP server: exposes the read-only investigation tools over stdio.

An MCP client starts this as a subprocess:  python -m mcp_server.server
IMPORTANT: a stdio server must never print to stdout, because stdout carries the protocol messages.
"""
import json

from mcp.server.fastmcp import FastMCP

from tools.code_inspector import CodeInspectorError, read_code, search_code
from tools.log_analyzer import read_log_lines, search_error_logs

server = FastMCP("failure-investigator-tools")


@server.tool()
def search_logs(keyword: str) -> str:
    """Search the stored application log files for a keyword. Returns matching lines
    with the log file name and line number."""
    return json.dumps(search_error_logs(keyword))


@server.tool()
def read_log_file(file_name: str, start_line: int = 1, end_line: int = 40) -> str:
    """Read lines from one stored log file (for example app.log) with real line numbers.
    Use it after search_logs finds a match, to read the traceback that follows the matching line."""
    try:
        return json.dumps(read_log_lines(file_name, start_line, end_line))
    except ValueError as exc:
        return json.dumps({"error": str(exc)})


@server.tool()
def search_source_code(keyword: str) -> str:
    """Search the sample service source code for a keyword. Returns matching lines
    with file path and line number."""
    return json.dumps(search_code(keyword))


@server.tool()
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


if __name__ == "__main__":
    server.run(transport="stdio")