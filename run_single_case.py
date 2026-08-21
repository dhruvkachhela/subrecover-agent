# How this works:
# Runner script to execute the full LangGraph recovery workflow for a single case ID.
# Prints the structured diagnosis, decision, tool execution output, and final state.

from agent.graph import recovery_graph
from agent.state import AgentState
import json

def run_recovery_for_case(case_id: str):
    """
    Execute the recovery agent graph for a given subscription case.
    
    Parameters:
        case_id (str): The unique case identifier (e.g., 'CASE0001').
        
    Returns:
        AgentState: The final state dictionary after workflow completion.
    """
    print(f"\n{'='*60}")
    print(f"Running recovery for {case_id}")
    print('='*60)

    initial_state: AgentState = {
        "case_id": case_id,
        "case_data": None,
        "diagnosis": None,
        "decision": None,
        "execution_result": None,
        "should_stop": False,
        "stop_reason": None,
        "is_recovered": False,
        "is_escalated": False,
        "messages": [],
        "final_status": None
    }

    final_state = recovery_graph.invoke(initial_state)

    print("\n--- Diagnosis ---")
    print(json.dumps(final_state.get("diagnosis"), indent=2))

    print("\n--- Decision ---")
    print(json.dumps(final_state.get("decision"), indent=2))

    print("\n--- Execution Result ---")
    print(json.dumps(final_state.get("execution_result"), indent=2))

    print("\n--- Final Control ---")
    print(f"Should stop: {final_state.get('should_stop')}")
    print(f"Stop reason: {final_state.get('stop_reason')}")
    print(f"Escalated: {final_state.get('is_escalated')}")

    return final_state

if __name__ == "__main__":
    # Test with one case
    run_recovery_for_case("CASE0001")
