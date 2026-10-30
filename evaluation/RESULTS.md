# Evaluation results

## Setup

- **Model:** `openai/gpt-oss-120b` on Groq's free tier, temperature 0.
- **Dataset:** 18 failures of the sample API (`evaluation/cases.json`): 9 with a full traceback, 4 with no log, 2 with a truncated log, 1 "silent" failure with no exception, and 2 unexplainable failures where the right answer is low confidence.
- **Prompts compared:** v1 (basic rules) and v2 (explicit workflow and evidence rules). The agent, tools, step limit (6) and model are identical.
- **Protocol:** one run per case per prompt, on 2026-10-29 and 2026-10-30. Raw results are in `evaluation/results/`; `v1_first_attempt.json` is the original v1 run before two infrastructure failures were retried.
- **Scoring:** deterministic Python, no LLM judge (`evaluation/metrics.py`).

| Metric | What it means |
|---|---|
| Root-cause accuracy | The report cites the expected file and line (±1) in verified evidence and its root-cause sentence contains the expected keywords. Counted over the 16 cases with a known cause. |
| Tool-selection correctness | The agent used the kinds of tools the case needed (for example, read the code, run the request validator). |
| Cited location exists | Of the file and line citations in reports, the share that exist on disk. |
| Evidence verified | Of all evidence items, the share matched to a real tool result by the verifier. |
| Uncertainty handling | On unexplainable cases, the report says low confidence. |
| Overconfident and wrong | High confidence with a wrong answer (or high confidence on an unexplainable case). |

## Results

| Metric | v1 | v2 |
|---|---|---|
| Root-cause accuracy | 93.8% (15 of 16) | 93.8% (15 of 16) |
| Tool-selection correctness | 72.2% | 94.4% |
| Cited location exists | 100% | 97.3% |
| Evidence verified | 89.6% | 97.0% |
| Uncertainty handling | 100% (2 of 2) | 50% (1 of 2) |
| Overconfident and wrong | 0 | 0 |
| Step-limit hits | 2 | 1 |
| Average steps | 4.2 | 4.4 |
| Average tokens per investigation | 6,391 | 8,058 |

## What the results show

- **Accuracy is the same.** Both prompts got 15 of 16 known-cause cases right, and neither was ever overconfident and wrong.
- **v2 follows its workflow and grounds its evidence better** (tool selection 94.4% vs 72.2%, evidence verified 97.0% vs 89.6%), at about 26% more tokens.
- **The tool-selection metric favours v2 by construction.** v2's prompt tells the agent to read the source code, and the metric requires it. In full-log cases, v1 often answered correctly from the traceback alone.
- **v1 handled the unexplainable timeout case better** (low confidence vs medium). That is a single case, not a pattern.
- **v2 cited one location that does not exist** (`order_controller.py:22`, a file with 21 lines), which the verifier flagged. It appears to be a line number from a stored log mistaken for a source line.
- Cases where the two prompts differed: `post-orders-null-quantity` and `post-orders-quantity-is-a-dict` (v1 medium confidence because it never read the code, v2 high), and `unknown-user-timeout-504` (v1 low, v2 medium).

## Failures

| Case | Prompt | What happened |
|---|---|---|
| `no-log-post-orders-missing-quantity` | v1 and v2 | No log was submitted. Both leaned on a stored log from a different incident (a null quantity), never read the source code, and reported a `TypeError` instead of a `KeyError`. Confidence was capped at medium by the verifier. |
| `unknown-user-timeout-504` | v2 | Hit the step limit and reported medium confidence with a speculative cause (an upstream call that nothing in the code shows). |

## Process notes

- **The scorer was fixed after the first results.** Keyword matching was too strict (it missed phrasings like "does not include" and a non-breaking hyphen), and infrastructure errors were scored as wrong answers. Both are fixed; infrastructure errors are now excluded from accuracy and counted separately. The agent, prompts, tools and dataset were not changed.
- **Two v1 cases failed on Groq errors during report generation** ("Failed to parse tool call arguments as JSON" and "Tool choice is required, but model did not call a tool"). Each was retried once and completed. Wrong answers were never retried.

## Limitations

- 18 cases, one run each. One case is worth 6.25 points of accuracy, so a difference of one case is noise.
- The cases come from the same small sample service the agent was developed against, so results are optimistic for unseen systems.
- Keyword matching is approximate. The location check is the strict part.
- The verifier proves a cited location was shown to the agent, not that the explanation is correct.
- Groq's free-tier limits (8K tokens per minute, 200K per day) shaped the design: the runner is paced and resumable, and each prompt version needs most of a day's quota.

## Future improvements

- Cap confidence at low when the step limit is hit.
- Do not let stored logs steer the diagnosis when the user submitted none; require reading the code first.
- Retry the report-generation step once on Groq structured-output errors.
- More cases, repeated runs to measure variance, and cases from outside the development set.

## Reproduce

```bash
python -m evaluation.run_evaluation run v2 --token-budget 100000
python -m evaluation.run_evaluation run v1 --token-budget 100000
python -m evaluation.run_evaluation report v2
python -m evaluation.run_evaluation compare v1 v2
```