"""Run and score the evaluation.

  python -m evaluation.run_evaluation run v2 --token-budget 100000   # run / resume (saves after every case)
  python -m evaluation.run_evaluation report v2                      # score saved results, no LLM calls
  python -m evaluation.run_evaluation compare v1 v2                  # same cases, two prompt versions
"""
import argparse
import json
import time
from pathlib import Path

from evaluation.metrics import score_case, summarize
from investigator.agent import ainvestigate, build_graph, investigate
from mcp_server.client import load_agent_tools

HERE = Path(__file__).resolve().parent
CASES_FILE = HERE / "cases.json"
RESULTS_DIR = HERE / "results"
TOKENS_PER_MINUTE = 7000  # a little under the free tier's 8,000 tokens/minute for this model
SAVED_FIELDS = ["diagnosis", "tools_used", "steps", "tokens", "stop_reason", "error"]


def load_cases():
    return json.loads(CASES_FILE.read_text(encoding="utf-8"))


def results_path(version):
    return RESULTS_DIR / f"{version}.json"


def load_results(version):
    path = results_path(version)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_results(version, results):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results_path(version).write_text(json.dumps(results, indent=2), encoding="utf-8")


def prepare_failure(failure):
    """Turn the JSON case into the dict the agent expects."""
    failure = dict(failure)
    if "log_lines" in failure:
        failure["log_text"] = "\n".join(failure.pop("log_lines"))
    if "request_body" in failure:
        failure["request_body"] = json.dumps(failure["request_body"])
    return failure


def is_rate_limit_error(error):
    text = (error or "").lower()
    return "rate_limit" in text or "rate limit" in text or "429" in text


def run(version, limit=None, token_budget=None, retry_errors=False, backend="local"):
    label = version if backend == "local" else f"{version}_mcp"  # results are kept separate per backend
    cases = load_cases()
    results = load_results(label)
    if retry_errors:  # re-run cases that failed with an infrastructure error
        results = {k: v for k, v in results.items() if not v.get("error")}
        save_results(label, results)
    pending = [c for c in cases if c["id"] not in results]
    if limit:
        pending = pending[:limit]
    print(f"Prompt {version} ({backend} tools): {len(results)} cases already done, {len(pending)} to run")

    if backend == "mcp":
        graph = build_graph(version, tools=asyncio.run(load_agent_tools()))
    else:
        graph = build_graph(version)
    spent = 0
    for index, case in enumerate(pending, start=1):
        print(f"[{index}/{len(pending)}] {case['id']}", flush=True)
        failure = prepare_failure(case["failure"])
        if backend == "mcp":
            result = asyncio.run(ainvestigate(failure, graph=graph))
        else:
            result = investigate(failure, graph=graph)
        if is_rate_limit_error(result["error"]):
            print("Groq rate limit reached. Progress is saved; rerun the same command later.")
            print(str(result["error"])[:300])
            return
        results[case["id"]] = {key: result[key] for key in SAVED_FIELDS}
        save_results(label, results)
        spent += result["tokens"]
        print(f"    tokens={result['tokens']} steps={result['steps']} stop={result['stop_reason']} "
              f"confidence={result['diagnosis']['confidence']}")
        if token_budget and spent >= token_budget:
            print(f"Token budget of {token_budget} reached. Progress is saved; rerun later to continue.")
            return
        if index < len(pending):
            time.sleep(result["tokens"] / TOKENS_PER_MINUTE * 60)  # stay under the per-minute token limit
    print("Run finished.")

def _fmt(value):
    return "n/a" if value is None else str(value)


def _outcome(score):
    if score["infra_error"]:
        return "error"
    if score["root_cause_correct"] is not None:
        return "correct" if score["root_cause_correct"] else "wrong"
    return "uncertain-ok" if score["uncertainty_ok"] else "uncertain-miss"


def show_report(version):
    cases = load_cases()
    results = load_results(version)
    scores = [score_case(c, results[c["id"]]) for c in cases if c["id"] in results]
    if not scores:
        print(f"No saved results for {version}. Run:  python -m evaluation.run_evaluation run {version}")
        return
    print(f"\n== Prompt {version}: {len(scores)} of {len(cases)} cases completed ==")
    for key, value in summarize(scores).items():
        print(f"{key:>26}: {_fmt(value)}")
    print(f"\n{'case':<40}{'outcome':<16}{'confidence':<12}{'steps':>5}{'tokens':>8}")
    for s in scores:
        print(f"{s['id']:<40}{_outcome(s):<16}{s['confidence']:<12}{s['steps']:>5}{s['tokens']:>8}")
    problems = [s for s in scores if s["reasons"]]
    print(f"\nCases with problems: {len(problems)} of {len(scores)}")
    for s in problems:
        print(f"- {s['id']} ({s['category']}), confidence={s['confidence']}")
        for reason in s["reasons"]:
            print(f"    * {reason}")
        print(f"    root cause given: {results[s['id']]['diagnosis']['root_cause'][:200]}")


def show_compare(version_a, version_b):
    cases = load_cases()
    res_a, res_b = load_results(version_a), load_results(version_b)
    common = [c for c in cases if c["id"] in res_a and c["id"] in res_b]
    if not common:
        print("No cases completed by both versions yet.")
        return
    scores_a = [score_case(c, res_a[c["id"]]) for c in common]
    scores_b = [score_case(c, res_b[c["id"]]) for c in common]
    sum_a, sum_b = summarize(scores_a), summarize(scores_b)
    print(f"\nCompared on the {len(common)} cases both versions completed\n")
    print(f"{'metric':<28}{version_a:>10}{version_b:>10}")
    for key in sum_a:
        print(f"{key:<28}{_fmt(sum_a[key]):>10}{_fmt(sum_b[key]):>10}")
    print("\nCases where the versions differ:")
    differ = False
    for sa, sb in zip(scores_a, scores_b):
        if (_outcome(sa), sa["confidence"]) != (_outcome(sb), sb["confidence"]):
            differ = True
            print(f"- {sa['id']}: {version_a}={_outcome(sa)}/{sa['confidence']}  {version_b}={_outcome(sb)}/{sb['confidence']}")
    if not differ:
        print("  (none)")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run")
    run_p.add_argument("version")
    run_p.add_argument("--limit", type=int)
    run_p.add_argument("--token-budget", type=int)
    run_p.add_argument("--retry-errors", action="store_true")
    run_p.add_argument("--backend", choices=["local", "mcp"], default="local")
    report_p = sub.add_parser("report")
    report_p.add_argument("version")
    compare_p = sub.add_parser("compare")
    compare_p.add_argument("version_a")
    compare_p.add_argument("version_b")
    args = parser.parse_args()

    if args.command == "run":
        run(args.version, args.limit, args.token_budget, args.retry_errors, args.backend)
    elif args.command == "report":
        show_report(args.version)
    else:
        show_compare(args.version_a, args.version_b)


if __name__ == "__main__":
    main()