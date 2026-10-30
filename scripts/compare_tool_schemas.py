"""Compare the tool definitions the LLM sees: local tools vs MCP tools. No LLM, no tokens."""
import asyncio
import json

from langchain_core.utils.function_calling import convert_to_openai_tool

from investigator.agent_tools import TOOLS
from mcp_server.client import load_agent_tools


def definition(tool):
    spec = convert_to_openai_tool(tool)["function"]
    return {"description": spec.get("description", "").strip(), "parameters": spec.get("parameters", {})}


mcp_tools = asyncio.run(load_agent_tools())
for local, remote in zip(TOOLS, mcp_tools):
    a, b = definition(local), definition(remote)
    if a == b:
        print(f"{local.name}: identical")
        continue
    print(f"{local.name}: DIFFERENT")
    for key in ("description", "parameters"):
        if a[key] != b[key]:
            print(f"  {key} local: {json.dumps(a[key], sort_keys=True)}")
            print(f"  {key} mcp:   {json.dumps(b[key], sort_keys=True)}")