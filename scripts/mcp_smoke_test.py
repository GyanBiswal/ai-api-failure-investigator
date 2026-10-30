"""Start the MCP server as a subprocess, discover its tools and call them. No LLM, no tokens."""
import asyncio
import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

ROOT = Path(__file__).resolve().parent.parent
CONFIG = {
    "investigator": {
        "transport": "stdio",
        "command": sys.executable,
        "args": ["-m", "mcp_server.server"],
        "env": {"PYTHONPATH": str(ROOT)},  # lets the subprocess import tools/
    }
}


async def main():
    client = MultiServerMCPClient(CONFIG)
    tools = await client.get_tools()
    print("Discovered tools:", sorted(t.name for t in tools))
    by_name = {t.name: t for t in tools}

    ok = await by_name["read_source_code"].ainvoke(
        {"path": "sample_service/controllers/user_controller.py", "start_line": 12, "end_line": 12})
    print("\n1) valid call. Result type:", type(ok).__name__)
    print(ok)

    blocked = await by_name["read_source_code"].ainvoke({"path": "../requirements.txt"})
    print("\n2) path traversal attempt:")
    print(blocked)

    try:
        sync_result = by_name["search_logs"].invoke({"keyword": "KeyError"})
        print("\n3) sync .invoke() works:", str(sync_result)[:100])
    except Exception as exc:
        print("\n3) sync .invoke() fails:", type(exc).__name__, str(exc)[:150])


asyncio.run(main())