"""Checks that Groq works and that the model can call a tool."""
from langchain_core.tools import tool

from investigator.llm import get_llm


@tool
def add_numbers(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


llm = get_llm()

print("1) Plain reply:")
print(llm.invoke("Reply with exactly: ready").content)

print("\n2) Tool calling:")
response = llm.bind_tools([add_numbers]).invoke("What is 17 plus 25? Use the tool.")
print("tool_calls:", response.tool_calls)