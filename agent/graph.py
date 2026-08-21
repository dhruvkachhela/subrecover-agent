# How this works:
# This module constructs and compiles the LangGraph StateGraph workflow:
# 1. Adds nodes: load_case -> diagnose -> decide -> execute -> check_stop
# 2. Defines execution edges and conditional routing to END.
# 3. Compiles and exports the 'recovery_graph' instance.

from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.nodes import (
    load_case_node,
    diagnose_node,
    decide_intervention_node,
    execute_node,
    check_stop_node
)

def create_recovery_graph():
    """
    Construct and compile the state graph for the subscription recovery agent.
    
    Returns:
        CompiledStateGraph: The compiled executable recovery graph.
    """
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("load_case", load_case_node)
    workflow.add_node("diagnose", diagnose_node)
    workflow.add_node("decide", decide_intervention_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("check_stop", check_stop_node)

    # Define the flow
    workflow.set_entry_point("load_case")
    workflow.add_edge("load_case", "diagnose")
    workflow.add_edge("diagnose", "decide")
    workflow.add_edge("decide", "execute")
    workflow.add_edge("execute", "check_stop")

    # Conditional edge from check_stop
    def should_continue(state: AgentState):
        """
        Evaluate whether the workflow should proceed or terminate.
        
        Parameters:
            state (AgentState): Current agent state.
            
        Returns:
            str: Routing decision string ("end").
        """
        if state.get("should_stop") or state.get("is_escalated") or state.get("is_recovered"):
            return "end"
        return "end"   # For now we do single pass per case. Multi-attempt loop can be added later.

    workflow.add_conditional_edges(
        "check_stop",
        should_continue,
        {
            "end": END
        }
    )

    return workflow.compile()

# Create the compiled graph
recovery_graph = create_recovery_graph()
