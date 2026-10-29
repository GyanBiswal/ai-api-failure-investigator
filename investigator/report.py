"""The structured report the agent must produce."""
from typing import List, Literal

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    source: Literal["log", "code", "request_validation", "user_input"] = Field(
        description="Where this evidence came from"
    )
    file: str = Field(default="", description="File path exactly as returned by a tool, or empty string")
    line: int = Field(default=0, description="Line number exactly as returned by a tool, or 0 if none")
    detail: str = Field(description="What this evidence shows, in one sentence")


class Diagnosis(BaseModel):
    root_cause: str = Field(description="The most likely root cause, in one or two sentences")
    confidence: Literal["high", "medium", "low"] = Field(description="How well the evidence supports the root cause")
    evidence: List[Evidence] = Field(description="Supporting evidence taken only from tool results or user input")
    recommended_fix: str = Field(description="A suggested fix. It has NOT been applied or tested.")
    verification_test: str = Field(description="A test that would confirm the fix works")
    missing_information: List[str] = Field(description="What is unknown or would raise confidence. Empty list if nothing.")
    assumptions: List[str] = Field(description="Things you infer that the evidence does not directly show. Empty list if none.")


def diagnosis_to_dict(diagnosis: Diagnosis) -> dict:
    """Turn empty file / zero line placeholders back into None."""
    data = diagnosis.model_dump()
    for item in data["evidence"]:
        item["file"] = item["file"] or None
        item["line"] = item["line"] or None
    return data


def fallback_report(reason: str) -> dict:
    """Safe report used when the investigation cannot be completed."""
    return {
        "root_cause": "Investigation could not be completed.",
        "confidence": "low",
        "evidence": [],
        "recommended_fix": "",
        "verification_test": "",
        "missing_information": [reason],
        "assumptions": [],
        "confidence_notes": [],
    }