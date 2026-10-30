import asyncio
import json

from langchain_core.messages import AIMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

from investigator.agent import make_async_tools_node, result_to_text, tools_node
from investigator.agent_tools import TOOLS
from mcp_server.client import MCP_CONFIG, load_agent_tools

USER_FILE = "sample_service/controllers/user_controller.py"


def payload(result):
    """MCP tool results may be a plain string or a list of content blocks; return the JSON they carry."""
    return json.loads(result_to_text(result))


def discovered_names():
    async def run():
        tools = await MultiServerMCPClient(MCP_CONFIG).get_tools()
        return sorted(t.name for t in tools)
    return asyncio.run(run())


def call_tools(calls):
    """Start the server, run [(tool_name, args), ...] and return the parsed JSON of each result."""
    async def run():
        tools = {t.name: t for t in await MultiServerMCPClient(MCP_CONFIG).get_tools()}
        return [payload(await tools[name].ainvoke(args)) for name, args in calls]
    return asyncio.run(run())


def test_server_exposes_the_four_read_only_tools():
    assert discovered_names() == ["read_log_file", "read_source_code", "search_logs", "search_source_code"]


def test_read_source_code_over_mcp_returns_the_real_line():
    [result] = call_tools([("read_source_code", {"path": USER_FILE, "start_line": 12, "end_line": 12})])
    assert result["start_line"] == 12
    assert 'user["name"]' in result["numbered"]


def test_path_traversal_is_blocked_over_mcp():
    results = call_tools([
        ("read_source_code", {"path": "../requirements.txt"}),
        ("read_source_code", {"path": "/etc/passwd"}),
        ("read_log_file", {"file_name": "../requirements.txt"}),
    ])
    assert all("error" in r for r in results)


def test_search_logs_over_mcp_finds_hits():
    [hits] = call_tools([("search_logs", {"keyword": "KeyError"})])
    assert len(hits) >= 2 and all(h["file"] == "app.log" for h in hits)


def test_agent_tool_list_keeps_the_same_names_and_order():
    tools = asyncio.run(load_agent_tools())
    assert [t.name for t in tools] == [t.name for t in TOOLS]


def test_async_tools_node_over_mcp_matches_local_tools():
    tools = asyncio.run(load_agent_tools())
    state = {"messages": [AIMessage(content="", tool_calls=[
        {"name": "read_source_code", "args": {"path": USER_FILE, "start_line": 12, "end_line": 12}, "id": "c1"},
        {"name": "search_logs", "args": {"keyword": "KeyError"}, "id": "c2"},
        {"name": "analyze_log_text", "args": {"log_text": "KeyError: 'name'"}, "id": "c3"},  # stays local
    ])]}
    remote = asyncio.run(make_async_tools_node(tools)(state))
    local = tools_node(state)
    assert [e["result"] for e in remote["tool_log"]] == [e["result"] for e in local["tool_log"]]


def test_async_tools_node_unsafe_path_and_unknown_tool_do_not_crash():
    tools = asyncio.run(load_agent_tools())
    state = {"messages": [AIMessage(content="", tool_calls=[
        {"name": "read_source_code", "args": {"path": "../requirements.txt"}, "id": "c1"},
        {"name": "delete_everything", "args": {}, "id": "c2"},
    ])]}
    out = asyncio.run(make_async_tools_node(tools)(state))
    assert "error" in json.loads(out["tool_log"][0]["result"])
    assert "Unknown tool" in json.loads(out["tool_log"][1]["result"])["error"]


def test_result_to_text_handles_strings_and_content_blocks():
    assert result_to_text('{"a": 1}') == '{"a": 1}'
    assert result_to_text([{"type": "text", "text": '{"a": '}, {"type": "text", "text": "1}"}]) == '{"a": 1}'
    assert result_to_text(5) == "5"

def test_async_tools_node_survives_a_server_failure_mid_run():
    class BrokenTool:
        name = "read_source_code"

        async def ainvoke(self, args):
            raise ConnectionError("MCP server went away")

    state = {"messages": [AIMessage(content="", tool_calls=[
        {"name": "read_source_code", "args": {"path": USER_FILE}, "id": "c1"}])]}
    out = asyncio.run(make_async_tools_node([BrokenTool()])(state))
    assert "ConnectionError" in json.loads(out["tool_log"][0]["result"])["error"]