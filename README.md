# AI API Failure Investigator

An AI-powered developer tool that investigates failed API requests, identifies likely root causes from logs and source code, and recommends fixes with supporting evidence.

**Status:** Phases 0 to 4 complete (tools, LangGraph agent, evidence verification, evaluation). MCP integration, Streamlit UI and deployment are in progress.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then add your own Groq API key
```

## Budget

Built with free tools only (Groq free tier, GitHub, free hosting).

## Evaluation

18 test failures, two prompt versions, deterministic scoring. Both prompts got 15 of 16 known-cause cases right with no overconfident wrong answers; v2 grounds its evidence better and v1 uses about 26% fewer tokens. Full results, failures and limitations: [evaluation/RESULTS.md](evaluation/RESULTS.md).