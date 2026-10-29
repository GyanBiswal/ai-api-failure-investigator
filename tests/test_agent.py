import json

from langchain_core.messages import AIMessage

from investigator.agent import MAX_STEPS, route_after_agent, tools_node
from investigator.agent_tools import validate_request_payload
from investigator.report import Diagnosis, Evidence, diagnosis_to_dict


def _tool_call(name, args, call_id="c1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def test_tools_node_runs_real_tool():
    state = {"messages": [_tool_call("read_source_code", {
        "path": "sample_service/controllers/user_controller.py", "start_line": 12, "end_line": 12})]}
    out = tools_node(state)
    result = json.loads(out["tool_log"][0]["result"])
    assert 'user["name"]' in result["numbered"]
    assert out["messages"][0].tool_call_id == "c1"


def test_tools_node_unsafe_path_returns_error_not_crash():
    out = tools_node({"messages": [_tool_call("read_source_code", {"path": "../requirements.txt"})]})
    assert "error" in json.loads(out["tool_log"][0]["result"])


def test_tools_node_unknown_tool_returns_error():
    out = tools_node({"messages": [_tool_call("delete_everything", {})]})
    assert "Unknown tool" in json.loads(out["tool_log"][0]["result"])["error"]


def test_validate_tool_handles_bad_json():
    result = validate_request_payload.invoke(
        {"method": "POST", "endpoint": "/orders", "payload_json": "{bad"})
    assert "error" in json.loads(result)


def test_router_goes_to_tools_when_tool_calls_present():
    state = {"messages": [_tool_call("search_logs", {"keyword": "x"})], "steps": 1}
    assert route_after_agent(state) == "tools"


def test_router_stops_at_step_limit():
    state = {"messages": [_tool_call("search_logs", {"keyword": "x"})], "steps": MAX_STEPS}
    assert route_after_agent(state) == "report"


def test_router_reports_when_no_tool_calls():
    assert route_after_agent({"messages": [AIMessage(content="done")], "steps": 2}) == "report"


def test_router_reports_on_llm_error():
    state = {"messages": [AIMessage(content="")], "steps": 1, "error": "boom"}
    assert route_after_agent(state) == "report"


def test_diagnosis_placeholders_become_none():
    diagnosis = Diagnosis(
        root_cause="x", confidence="low",
        evidence=[Evidence(source="log", detail="no location"),
                  Evidence(source="code", file="a.py", line=3, detail="has location")],
        recommended_fix="f", verification_test="t", missing_information=[], assumptions=[])
    data = diagnosis_to_dict(diagnosis)
    assert data["evidence"][0]["file"] is None and data["evidence"][0]["line"] is None
    assert data["evidence"][1]["file"] == "a.py" and data["evidence"][1]["line"] == 3