"""Measure the real token cost of investigations (needed to plan the evaluation run).

    python -m scripts.measure_tokens        # cases 1, 2 and 5
    python -m scripts.measure_tokens 1 3
"""
import sys
import time

from investigator.agent import build_graph, investigate
from scripts.run_investigation import CASES

PAUSE_SECONDS = 60  # free tier allows 8K tokens per minute, so let the minute window reset

keys = sys.argv[1:] or ["1", "2", "5"]
graph = build_graph("v2")
for i, key in enumerate(keys):
    if i:
        time.sleep(PAUSE_SECONDS)
    result = investigate(CASES[key], graph=graph)
    print(
        f"case {key}: tokens={result['tokens']} steps={result['steps']} "
        f"stop={result['stop_reason']} confidence={result['diagnosis']['confidence']}"
    )