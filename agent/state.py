from typing import TypedDict, Optional, List, Dict, Any, Annotated
from langgraph.graph.message import add_messages
from datetime import datetime

class AgentState(TypedDict):
    # === Case Identification ===
    case_id: str

    # === Current Case Snapshot ===
    case_data: Optional[Dict[str, Any]]

    # === Agent Memory (very important for multi-step reasoning) ===
    history: List[Dict[str, Any]]          # list of previous steps
    # Each item in history will look like:
    # {
    #   "step": 1,
    #   "thought": "...",
    #   "action": "...",
    #   "action_input": {...},
    #   "observation": {...},
    #   "reflection": "..."
    # }

    # === Current Step Data & Cognitive Sub-States ===
    current_thought: Optional[str]
    current_action: Optional[str]
    current_action_input: Optional[Dict[str, Any]]
    current_observation: Optional[Dict[str, Any]]
    current_reflection: Optional[str]
    diagnosis: Optional[Dict[str, Any]]
    message_payload: Optional[Dict[str, Any]]

    # === Control Flags ===
    step_count: int
    max_steps: int
    should_stop: bool
    stop_reason: Optional[str]
    is_recovered: bool
    is_escalated: bool
    final_status: Optional[str]

    # === Optional messages for LangGraph compatibility ===
    messages: Annotated[List[Any], add_messages]
