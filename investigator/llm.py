"""Single place where the LLM is created.

The model name comes from .env so a retired model is a one-line fix.
"""
import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()


def get_llm(temperature: float = 0.0) -> ChatGroq:
    api_key = os.getenv("GROQ_API_KEY", "")
    model = os.getenv("GROQ_MODEL", "")

    if not api_key or api_key.startswith("your_"):
        raise RuntimeError("GROQ_API_KEY is missing. Add your key to .env")
    if not model or model.startswith("choose_"):
        raise RuntimeError("GROQ_MODEL is not set. Pick a model and add it to .env")

    # temperature 0 keeps diagnoses as repeatable as possible
    return ChatGroq(model=model, temperature=temperature, max_retries=2, timeout=30)