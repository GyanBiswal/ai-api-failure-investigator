"""Everything the agent remembers while investigating one failure."""
import operator
from typing import Annotated, Optional

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class InvestigationState(TypedDict):
    failure: dict                                  # what the user submitted
    messages: Annotated[list, add_messages]        # conversation with the LLM (new messages are appended)
    tool_log: Annotated[list, operator.add]        # every tool call + result (new entries are appended)
    steps: int                                     # how many times the agent node has run
    error: Optional[str]                           # set if the LLM call failed
    stop_reason: Optional[str]                     # enough_evidence | step_limit | error
    diagnosis: Optional[dict]                      # the final report