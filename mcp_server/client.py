"""MCP client: connects to the MCP server and hands its tools to the agent."""
import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

from investigator.agent_tools import TOOLS

ROOT = Path(__file__).resolve().parent.parent
MCP_CONFIG = {
    "investigator": {
        "transport": "stdio",
        "command": sys.executable,
        "args": ["-m", "mcp_server.server"],
        "env": {"PYTHONPATH": str(ROOT)},  # lets the server subprocess import tools/
    }
}
MCP_TOOL_NAMES = {"search_logs", "read_log_file", "search_source_code", "read_source_code"}


async def load_agent_tools():
    """Agent tools: the 4 MCP-served tools come from the server, the rest stay local Python.

    The order matches investigator.agent_tools.TOOLS, so the model sees the same tool list as before.
    """
    mcp_tools = {t.name: t for t in await MultiServerMCPClient(MCP_CONFIG).get_tools()}
    missing = MCP_TOOL_NAMES - set(mcp_tools)
    if missing:
        raise RuntimeError(f"MCP server did not provide: {sorted(missing)}")
    return [mcp_tools.get(tool.name, tool) for tool in TOOLS]