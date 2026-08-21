# How this works:
# Defines the AgentState TypedDict schema for the LangGraph workflow.
# It holds the case identification, fetched case data, diagnosis, decision,
# tool execution output, stopping flags, and chat message trails.

from typing import TypedDict, Optional, List, Dict, Any, Annotated
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    """
    State schema definition for the subscription recovery LangGraph agent.
    
    Fields:
        case_id: The unique identifier of the transaction case.
        case_data: Dictionary of loaded case details from the database.
        diagnosis: Structured JSON diagnosis output from the LLM.
        decision: Structured JSON decision output from the LLM.
        execution_result: Results from calling tools (e.g., payment link creation).
        should_stop: Boolean flag indicating if workflow should terminate.
        stop_reason: Text description explaining why execution stopped.
        is_recovered: Flag indicating successful payment recovery.
        is_escalated: Flag indicating manual human escalation.
        messages: LangGraph message list with reducer for reasoning trails.
        final_status: Summary status string of the workflow execution.
    """
    # Case identification
    case_id: str
    
    # Current case data (will be loaded)
    case_data: Optional[Dict[str, Any]]
    
    # Diagnosis result from LLM
    diagnosis: Optional[Dict[str, Any]]
    
    # Decision from LLM
    decision: Optional[Dict[str, Any]]
    
    # Execution results
    execution_result: Optional[Dict[str, Any]]
    
    # Control flags
    should_stop: bool
    stop_reason: Optional[str]
    is_recovered: bool
    is_escalated: bool
    
    # Messages / reasoning trail (optional but useful)
    messages: Annotated[List[Any], add_messages]
    
    # Final status for this run
    final_status: Optional[str]
