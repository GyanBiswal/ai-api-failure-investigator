"""LangGraph investigation agent: agent <-> tools loop, then a structured report."""
import json

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph

from investigator.agent_tools import TOOLS, TOOLS_BY_NAME
from investigator.llm import get_llm
from investigator.prompts import PROMPTS, build_failure_message
from investigator.report import Diagnosis, diagnosis_to_dict, fallback_report
from investigator.state import InvestigationState

MAX_STEPS = 6            # maximum agent turns per investigation
MAX_RESULT_CHARS = 3000  # cap on each tool result shown to the report step


def tools_node(state: InvestigationState) -> dict:
    """Run every tool the LLM asked for. Errors become results, never crashes."""
    last = state["messages"][-1]
    tool_messages, log_entries = [], []
    for call in last.tool_calls:
        tool = TOOLS_BY_NAME.get(call["name"])
        if tool is None:
            result = json.dumps({"error": f"Unknown tool: {call['name']}"})
        else:
            try:
                result = tool.invoke(call["args"])
            except Exception as exc:  # a bad tool call must not kill the investigation
                result = json.dumps({"error": f"{type(exc).__name__}: {exc}"})
        tool_messages.append(ToolMessage(content=result, tool_call_id=call["id"], name=call["name"]))
        log_entries.append({"tool": call["name"], "args": call["args"], "result": result})
    return {"messages": tool_messages, "tool_log": log_entries}


def route_after_agent(state: InvestigationState) -> str:
    """Decide: run tools, or move on to the report."""
    if state.get("error"):
        return "report"
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None) and state["steps"] < MAX_STEPS:
        return "tools"
    return "report"


def format_evidence(tool_log: list) -> str:
    if not tool_log:
        return "(no tool results were gathered)"
    parts = []
    for i, entry in enumerate(tool_log, start=1):
        result = entry["result"]
        if len(result) > MAX_RESULT_CHARS:
            result = result[:MAX_RESULT_CHARS] + "...[truncated]"
        parts.append(f"[{i}] tool={entry['tool']} args={json.dumps(entry['args'])}\nresult={result}")
    return "\n\n".join(parts)


def build_graph(prompt_version: str = "v1"):
    prompts = PROMPTS[prompt_version]
    llm = get_llm()
    llm_with_tools = llm.bind_tools(TOOLS)
    structured_llm = llm.with_structured_output(Diagnosis, method="function_calling")

    def agent_node(state: InvestigationState) -> dict:
        messages = [SystemMessage(content=prompts["system"])] + state["messages"]
        try:
            response = llm_with_tools.invoke(messages)
        except Exception as exc:
            return {"error": f"LLM call failed: {type(exc).__name__}: {exc}", "steps": state["steps"] + 1}
        return {"messages": [response], "steps": state["steps"] + 1}

    def report_node(state: InvestigationState) -> dict:
        last = state["messages"][-1]
        hit_limit = bool(getattr(last, "tool_calls", None)) and state["steps"] >= MAX_STEPS
        if state.get("error"):
            stop_reason = "error"
        elif hit_limit:
            stop_reason = "step_limit"
        else:
            stop_reason = "enough_evidence"

        if state.get("error") and not state["tool_log"]:
            return {"diagnosis": fallback_report(state["error"]), "stop_reason": stop_reason}

        prompt = [
            SystemMessage(content=prompts["system"]),
            HumanMessage(content=(
                f"{build_failure_message(state['failure'])}\n\n"
                f"EVIDENCE GATHERED:\n{format_evidence(state['tool_log'])}\n\n"
                f"{prompts['report']}"
            )),
        ]
        try:
            diagnosis = structured_llm.invoke(prompt)
            if diagnosis is None:
                raise ValueError("model returned no structured report")
            return {"diagnosis": diagnosis_to_dict(diagnosis), "stop_reason": stop_reason}
        except Exception as exc:
            reason = f"Report generation failed: {type(exc).__name__}: {exc}"
            return {"diagnosis": fallback_report(reason), "stop_reason": stop_reason, "error": reason}

    graph = StateGraph(InvestigationState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("report", report_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_agent, {"tools": "tools", "report": "report"})
    graph.add_edge("tools", "agent")
    graph.add_edge("report", END)
    return graph.compile()


def investigate(failure: dict, prompt_version: str = "v1", graph=None) -> dict:
    """Investigate one failure. Pass a prebuilt graph to reuse it across many cases."""
    graph = graph or build_graph(prompt_version)
    initial = {
        "failure": failure,
        "messages": [HumanMessage(content=build_failure_message(failure))],
        "tool_log": [],
        "steps": 0,
        "error": None,
        "stop_reason": None,
        "diagnosis": None,
    }
    final = graph.invoke(initial)
    return {
        "diagnosis": final["diagnosis"],
        "fix_tested": False,  # set by code, never by the LLM: we do not run or apply fixes
        "tools_used": [entry["tool"] for entry in final["tool_log"]],
        "tool_log": final["tool_log"],
        "steps": final["steps"],
        "stop_reason": final["stop_reason"],
        "error": final["error"],
    }