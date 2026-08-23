
from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.nodes import (
    load_case_node,
    diagnose_node,
    craft_message_node,
    act_node,
    reflect_node,
    check_stop_node
)

def create_recovery_graph():
    """
    SubRecover Multi-Agent Cyclic StateGraph.
    
    Cognitive Stages:
    1. Ingestion & Pre-Action Reconciliation (load_case_node)
    2. Financial & Gateway Root-Cause Diagnosis (diagnose_node)
    3. Personalized Communication & Localization (craft_message_node)
    4. Deterministic Tool Execution (act_node)
    5. Observation & Reflection (reflect_node)
    6. Safety Circuit Breaker & Loop Evaluation (check_stop_node)
    """
    workflow = StateGraph(AgentState)

    # Register Nodes
    workflow.add_node("load_case", load_case_node)
    workflow.add_node("diagnose", diagnose_node)
    workflow.add_node("craft_message", craft_message_node)
    workflow.add_node("act", act_node)
    workflow.add_node("reflect", reflect_node)
    workflow.add_node("check_stop", check_stop_node)

    # 1. Entry point & early reconciliation stop check
    workflow.set_entry_point("load_case")

    def check_early_stop(state: AgentState):
        if state.get("should_stop"):
            return "end"
        return "continue"

    workflow.add_conditional_edges(
        "load_case",
        check_early_stop,
        {
            "continue": "diagnose",
            "end": END
        }
    )

    # 2. Diagnostic routing: if sending a link, route through craft_message; else route to act
    def route_after_diagnosis(state: AgentState):
        action = state.get("current_action", "create_and_send_link")
        if action == "create_and_send_link":
            return "craft_message"
        return "act"

    workflow.add_conditional_edges(
        "diagnose",
        route_after_diagnosis,
        {
            "craft_message": "craft_message",
            "act": "act"
        }
    )

    workflow.add_edge("craft_message", "act")
    workflow.add_edge("act", "reflect")
    workflow.add_edge("reflect", "check_stop")

    # 3. Cyclic loop or termination
    def should_continue(state: AgentState):
        """Decide whether to cycle back to diagnose or terminate"""
        if state.get("should_stop") or state.get("is_recovered") or state.get("is_escalated"):
            return "end"
        
        if state.get("step_count", 0) >= state.get("max_steps", 5):
            return "end"
            
        return "continue"

    workflow.add_conditional_edges(
        "check_stop",
        should_continue,
        {
            "continue": "diagnose",
            "end": END
        }
    )

    return workflow.compile()

# Compiled graph
recovery_graph = create_recovery_graph()
