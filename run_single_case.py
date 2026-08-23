from agent.graph import recovery_graph
from agent.state import AgentState
import json
from pprint import pprint

def run_recovery_for_case(case_id: str):
    print(f"\n{'='*70}")
    print(f"AGENTIC RECOVERY RUN -> {case_id}")
    print('='*70)

    initial_state: AgentState = {
        "case_id": case_id,
        "case_data": None,
        "history": [],
        "current_thought": None,
        "current_action": None,
        "current_action_input": None,
        "current_observation": None,
        "current_reflection": None,
        "step_count": 0,
        "max_steps": 5,
        "should_stop": False,
        "stop_reason": None,
        "is_recovered": False,
        "is_escalated": False,
        "final_status": None,
        "messages": []
    }

    final_state = recovery_graph.invoke(initial_state)

    print("\n----- FINAL STATUS -----")
    print(f"Recovered     : {final_state.get('is_recovered')}")
    print(f"Escalated     : {final_state.get('is_escalated')}")
    print(f"Final Status  : {final_state.get('final_status')}")
    print(f"Stop Reason   : {final_state.get('stop_reason')}")
    print(f"Total Steps   : {final_state.get('step_count')}")

    print("\n----- FULL AGENT HISTORY (Think -> Act -> Reflect) -----")
    history = final_state.get("history", [])
    if not history:
        print("No history recorded.")
    else:
        for step in history:
            print(f"\nStep {step.get('step')}:")
            print(f"  Thought     : {step.get('thought')}")
            print(f"  Action      : {step.get('action')}")
            act_in = step.get('action_input') or {}
            if act_in.get('message_body'):
                clean_msg = str(act_in.get('message_body')).encode('ascii', 'ignore').decode('ascii')
                print(f"  Copy (Witty): {clean_msg}")
            print(f"  Observation : {json.dumps(step.get('observation'), indent=4)[:300]}...")
            print(f"  Reflection  : {step.get('reflection')}")

    return final_state

if __name__ == "__main__":
    # Use a case that has not been heavily processed yet
    # Change this number if needed
    run_recovery_for_case("CASE0002")
