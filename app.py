"""Streamlit UI for the AI API Failure Investigator.   Run:  streamlit run app.py"""
import asyncio
import json
import time

import streamlit as st

from evaluation.metrics import score_case, summarize
from evaluation.run_evaluation import (
    RESULTS_DIR, SAVED_FIELDS, TOKENS_PER_MINUTE, is_rate_limit_error,
    load_cases, load_results, prepare_failure, save_results,
)
from investigator.agent import ainvestigate, build_graph, investigate
from mcp_server.client import load_agent_tools
from scripts.run_investigation import CASES as EXAMPLES
from ui_helpers import build_failure, outcome_label

st.set_page_config(page_title="AI API Failure Investigator", layout="wide")

METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]
LOCAL, MCP = "Local tools", "MCP server"
COOLDOWN_SECONDS = 20  # free tier allows 8K tokens per minute; one investigation uses 6K to 11K
EXAMPLE_LABELS = {
    "": "(blank form)",
    "1": "GET /users/99 with a traceback",
    "2": "POST /orders with a null quantity",
    "3": "POST /users with no log submitted",
    "4": "POST /orders with a truncated log",
    "5": "GET /health 503 (the code cannot explain it)",
}

DEFAULTS = {"f_method": "GET", "f_endpoint": "", "f_status": 500, "f_body": "",
            "f_log": "", "f_snippet": "", "example_choice": ""}
for _key, _value in DEFAULTS.items():
    st.session_state.setdefault(_key, _value)

st.sidebar.header("Settings")
version = st.sidebar.selectbox("Prompt version", ["v2", "v1"],
                               help="v2 has an explicit workflow and evidence rules; v1 is the baseline.")
backend = st.sidebar.radio("Tool backend", [LOCAL, MCP],
                           help="MCP runs the log and code tools in a separate MCP server process.")
st.sidebar.caption("Groq free tier: 8K tokens per minute and 200K per day. "
                   "One investigation uses about 6K to 11K tokens.")


def make_graph(prompt_version, tool_backend):
    if tool_backend == MCP:
        return build_graph(prompt_version, tools=asyncio.run(load_agent_tools()))
    return build_graph(prompt_version)


def run_one(graph, failure, tool_backend):
    if tool_backend == MCP:
        return asyncio.run(ainvestigate(failure, graph=graph))
    return investigate(failure, graph=graph)


def load_example():
    example = EXAMPLES.get(st.session_state.example_choice, {})
    st.session_state.f_method = example.get("method", "GET")
    st.session_state.f_endpoint = example.get("endpoint", "")
    st.session_state.f_status = example.get("status_code", 500)
    st.session_state.f_body = example.get("request_body", "")
    st.session_state.f_log = example.get("log_text", "")
    st.session_state.f_snippet = example.get("code_snippet", "")


def show_report(result):
    report = result["diagnosis"]
    st.subheader("Diagnosis")
    st.write(report["root_cause"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Confidence", report["confidence"])
    c2.metric("Steps", result["steps"])
    c3.metric("Tokens", result["tokens"])
    if report.get("confidence_llm") and report["confidence_llm"] != report["confidence"]:
        st.info(f"The model said '{report['confidence_llm']}'. The system capped it at '{report['confidence']}'.")
    for note in report.get("confidence_notes", []):
        st.caption("- " + note)
    if result["error"]:
        st.error(f"The investigation hit an error: {result['error']}")

    st.subheader("Supporting evidence")
    if report["evidence"]:
        st.dataframe([{
            "source": e["source"],
            "file": e.get("file") or "",
            "line": e.get("line"),
            "detail": e["detail"],
            "verified": "yes" if e.get("verified") else "NO",
            "check": e.get("verification_note", ""),
        } for e in report["evidence"]], use_container_width=True)
    else:
        st.write("No evidence was gathered.")

    st.subheader("Recommended fix")
    if not result["fix_tested"]:
        st.warning("This fix is a suggestion. It has not been applied or tested.")
    st.markdown(report["recommended_fix"] or "No fix was suggested.")

    st.subheader("Suggested verification test")
    st.markdown(report["verification_test"] or "No test was suggested.")

    left, right = st.columns(2)
    with left:
        st.subheader("Missing information")
        for item in report["missing_information"] or ["None reported."]:
            st.write("- " + item)
    with right:
        st.subheader("Assumptions (not confirmed by evidence)")
        for item in report.get("assumptions") or ["None reported."]:
            st.write("- " + item)

    with st.expander("Investigation details"):
        st.write(f"Tools used, in order: {', '.join(result['tools_used']) or 'none'}")
        st.write(f"Stop reason: {result['stop_reason']}")
        for i, entry in enumerate(result["tool_log"], start=1):
            st.markdown(f"**{i}. {entry['tool']}** `{json.dumps(entry['args'])}`")
            st.code(entry["result"][:1500], language="json")


def run_pending_cases(prompt_version, tool_backend, how_many):
    label = prompt_version if tool_backend == LOCAL else f"{prompt_version}_mcp"
    cases = load_cases()
    results = load_results(label)
    pending = [c for c in cases if c["id"] not in results][:how_many]
    if not pending:
        st.success(f"All {len(cases)} cases are already done for '{label}'. Nothing to run.")
        return
    graph = make_graph(prompt_version, tool_backend)
    bar = st.progress(0.0)
    for i, case in enumerate(pending, start=1):
        st.write(f"Running {case['id']} ...")
        result = run_one(graph, prepare_failure(case["failure"]), tool_backend)
        if is_rate_limit_error(result["error"]):
            st.error("Groq rate limit reached. Finished cases are saved; try again later.")
            return
        results[case["id"]] = {key: result[key] for key in SAVED_FIELDS}
        save_results(label, results)
        bar.progress(i / len(pending))
        if i < len(pending):
            time.sleep(result["tokens"] / TOKENS_PER_MINUTE * 60)  # stay under the per-minute token limit
    st.success(f"Finished {len(pending)} case(s) for '{label}'.")


def pct(value):
    return "n/a" if value is None else f"{value}%"


def show_saved_results():
    files = sorted(p.stem for p in RESULTS_DIR.glob("*.json") if not p.stem.endswith("_first_attempt")) \
        if RESULTS_DIR.exists() else []
    if not files:
        st.info("No saved evaluation results yet.")
        return
    chosen = st.selectbox("Saved results", files)
    cases = load_cases()
    results = load_results(chosen)
    scores = [score_case(c, results[c["id"]]) for c in cases if c["id"] in results]
    st.caption(f"{len(scores)} of {len(cases)} cases completed for '{chosen}'.")
    if not scores:
        return
    summary = summarize(scores)

    row1 = st.columns(4)
    row1[0].metric("Root-cause accuracy", pct(summary["root_cause_accuracy_pct"]))
    row1[1].metric("Tool selection", pct(summary["tool_selection_pct"]))
    row1[2].metric("Evidence verified", pct(summary["evidence_grounded_pct"]))
    row1[3].metric("Cited location exists", pct(summary["evidence_exists_pct"]))
    row2 = st.columns(4)
    row2[0].metric("Uncertainty handling", pct(summary["uncertainty_handling_pct"]))
    row2[1].metric("Overconfident and wrong", summary["overconfident_wrong"])
    row2[2].metric("Infrastructure errors", summary["errors"])
    row2[3].metric("Average tokens per case", summary["avg_tokens"])

    with st.expander("What the metrics mean"):
        st.markdown(
            "- **Root-cause accuracy:** the report cites the expected file and line (within 1 line) in verified "
            "evidence and its root-cause sentence has the expected keywords. Counted over cases with a known cause.\n"
            "- **Tool selection:** the agent used the kinds of tools the case needed.\n"
            "- **Evidence verified:** share of evidence items matched to a real tool result.\n"
            "- **Cited location exists:** share of file and line citations that exist on disk.\n"
            "- **Uncertainty handling:** on unexplainable cases, the report says low confidence.\n"
            "- **Overconfident and wrong:** high confidence with a wrong answer.\n"
            "- **Infrastructure errors:** Groq failures; excluded from accuracy."
        )

    st.subheader("Cases")
    st.dataframe([{
        "case": s["id"], "category": s["category"], "outcome": outcome_label(s),
        "confidence": s["confidence"], "steps": s["steps"], "tokens": s["tokens"],
    } for s in scores], use_container_width=True)

    problems = [s for s in scores if s["reasons"]]
    st.subheader(f"Cases with problems ({len(problems)})")
    for s in problems:
        with st.expander(f"{s['id']}  ({s['category']}, confidence {s['confidence']})"):
            for reason in s["reasons"]:
                st.write("- " + reason)
            st.write("Root cause given: " + results[s["id"]]["diagnosis"]["root_cause"])

    others = [f for f in files if f != chosen]
    if others:
        other = st.selectbox("Compare with (optional)", ["(none)"] + others)
        if other != "(none)":
            other_results = load_results(other)
            common = [c for c in cases if c["id"] in results and c["id"] in other_results]
            if not common:
                st.info("No cases completed by both result sets yet.")
            else:
                a = summarize([score_case(c, results[c["id"]]) for c in common])
                b = summarize([score_case(c, other_results[c["id"]]) for c in common])
                st.caption(f"Compared on the {len(common)} cases both completed.")
                st.dataframe([{"metric": key, chosen: a[key], other: b[key]} for key in a],
                             use_container_width=True)


st.title("AI API Failure Investigator")
tab_investigate, tab_eval = st.tabs(["Investigate a failure", "Evaluation"])

with tab_investigate:
    st.markdown("Describe a failed request to the sample API. The agent gathers evidence from logs and the "
                "sample service's source code and reports a likely root cause. Failures the code cannot "
                "explain should come back with low confidence.")
    left, right = st.columns([3, 1])
    left.selectbox("Load an example", ["", *EXAMPLES], key="example_choice",
                   format_func=lambda k: EXAMPLE_LABELS.get(k, f"Example {k}"))
    right.button("Load example", on_click=load_example)

    with st.form("investigate_form"):
        a, b, c = st.columns([1, 3, 1])
        a.selectbox("Method", METHODS, key="f_method")
        b.text_input("Endpoint", key="f_endpoint", placeholder="/orders")
        c.number_input("Status code", 100, 599, key="f_status")
        st.text_area("Request body (optional; it may be malformed, which can itself be the cause)",
                     key="f_body", height=100)
        st.text_area("Logs or error message (optional)", key="f_log", height=180)
        st.text_area("Source code snippet (optional)", key="f_snippet", height=100)
        submitted = st.form_submit_button("Investigate")

    if submitted:
        failure, problem = build_failure(
            st.session_state.f_method, st.session_state.f_endpoint, st.session_state.f_status,
            st.session_state.f_body, st.session_state.f_log, st.session_state.f_snippet)
        wait = COOLDOWN_SECONDS - (time.time() - st.session_state.get("last_run", 0.0))
        if problem:
            st.error(problem)
        elif wait > 0:
            st.warning(f"Please wait {int(wait) + 1} more seconds. The free tier limits tokens per minute.")
        else:
            st.session_state["last_run"] = time.time()
            with st.spinner("Investigating. This usually takes 10 to 30 seconds."):
                try:
                    st.session_state["last_result"] = run_one(make_graph(version, backend), failure, backend)
                except Exception as exc:  # show the problem instead of a stack trace
                    st.session_state["last_result"] = None
                    st.error(f"Could not run the investigation: {type(exc).__name__}: {exc}")

    if st.session_state.get("last_result"):
        show_report(st.session_state["last_result"])

with tab_eval:
    with st.expander("Run more evaluation cases (uses Groq tokens)"):
        st.write("Runs the next unfinished cases with the prompt version and tool backend chosen in the sidebar. "
                 "Each case uses about 6K to 11K tokens, and cases are paced to respect the free-tier limit, "
                 "so each takes about a minute. Results are saved to the same files as the command-line runner, "
                 "so do not run both at the same time.")
        how_many = st.number_input("Cases to run now", 1, 5, 2)
        if st.button("Run next cases"):
            try:
                run_pending_cases(version, backend, int(how_many))
            except Exception as exc:
                st.error(f"Could not run the evaluation: {type(exc).__name__}: {exc}")
    show_saved_results()