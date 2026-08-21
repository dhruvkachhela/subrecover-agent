# How this works:
# This script executes batch recovery across multiple failed subscription cases.
# It invokes the compiled LangGraph agent for each case in sequence,
# calculates high-level metrics (revenue at risk, escalations, failure breakdown),
# displays a structured console recovery report, and exports results to batch_results.json.

import json
from datetime import datetime
from agent.graph import recovery_graph
from agent.state import AgentState
from app.database import SessionLocal, get_all_recoverable_cases
from app.models import FailedSubscription, AuditLog
from agent.tools import get_case

def run_recovery_for_case(case_id: str) -> dict:
    """
    Run the full LangGraph recovery workflow for a single case.
    
    Parameters:
        case_id (str): The unique case identifier.
        
    Returns:
        dict: Summary dictionary containing execution status, diagnosis, decision, and results.
    """
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

    try:
        final_state = recovery_graph.invoke(initial_state)
        return {
            "case_id": case_id,
            "success": True,
            "diagnosis": final_state.get("diagnosis"),
            "decision": final_state.get("decision"),
            "execution_result": final_state.get("execution_result"),
            "final_status": final_state.get("final_status"),
            "is_escalated": final_state.get("is_escalated", False)
        }
    except Exception as e:
        return {
            "case_id": case_id,
            "success": False,
            "error": str(e)
        }

def calculate_metrics():
    """
    Calculate summary recovery metrics from the SQLite database.
    
    Returns:
        dict: Aggregated dictionary of totals, amounts at risk, recovery and escalation counts.
    """
    db = SessionLocal()
    try:
        all_cases = db.query(FailedSubscription).all()

        total_cases = len(all_cases)
        total_at_risk = sum(c.amount for c in all_cases) / 100          # in Rs.
        recovered_cases = [c for c in all_cases if c.status == "recovered"]
        escalated_cases = [c for c in all_cases if c.status == "escalated"]
        still_open = [c for c in all_cases if c.status == "failed_recoverable"]

        total_recovered = sum(c.recovered_amount for c in recovered_cases) / 100
        recovery_rate = (len(recovered_cases) / total_cases * 100) if total_cases > 0 else 0

        # Breakdown by failure code
        from collections import Counter
        failure_breakdown = Counter(c.failure_code for c in all_cases)

        return {
            "total_cases": total_cases,
            "total_revenue_at_risk_inr": round(total_at_risk, 2),
            "recovered_cases": len(recovered_cases),
            "total_recovered_inr": round(total_recovered, 2),
            "recovery_rate_percent": round(recovery_rate, 2),
            "escalated_cases": len(escalated_cases),
            "still_open_cases": len(still_open),
            "failure_code_breakdown": dict(failure_breakdown)
        }
    finally:
        db.close()

def print_report(metrics: dict, processed: int):
    """
    Print a structured batch recovery performance report to the console.
    
    Parameters:
        metrics (dict): Aggregated performance metrics dictionary.
        processed (int): Number of cases processed in the current batch run.
    """
    print("\n" + "="*70)
    print("SUBRECOVER AGENT - BATCH RECOVERY REPORT")
    print("="*70)
    print(f"Processed cases this run : {processed}")
    print(f"Total cases in system    : {metrics['total_cases']}")
    print(f"Total Revenue at Risk    : Rs.{metrics['total_revenue_at_risk_inr']:,.2f}")
    print(f"Successfully Recovered   : Rs.{metrics['total_recovered_inr']:,.2f}")
    print(f"Recovery Rate            : {metrics['recovery_rate_percent']}%")
    print(f"Escalated to Human       : {metrics['escalated_cases']}")
    print(f"Still Open               : {metrics['still_open_cases']}")
    print("\nFailure Code Breakdown:")
    for code, count in metrics["failure_code_breakdown"].items():
        print(f"  * {code:<25} : {count}")
    print("="*70)

def main(limit: int = 20):
    """
    Run the recovery agent on a batch of recoverable cases up to the specified limit.
    
    Parameters:
        limit (int): Maximum number of cases to process in this run.
        
    Returns:
        dict: Final calculated metrics dictionary.
    """
    print(f"\nStarting batch recovery (limit={limit})...")
    print(f"Time: {datetime.now().isoformat()}")

    cases = get_all_recoverable_cases()
    cases_to_process = cases[:limit]

    print(f"Found {len(cases)} recoverable cases. Processing first {len(cases_to_process)}...\n")

    results = []
    for i, case in enumerate(cases_to_process, 1):
        print(f"[{i}/{len(cases_to_process)}] Processing {case.case_id} | {case.customer_name} | Rs.{case.amount/100:.2f} | {case.failure_code}")
        result = run_recovery_for_case(case.case_id)
        results.append(result)

        if result.get("success"):
            action = result.get("decision", {}).get("action", "unknown")
            print(f"         -> Action: {action}")
        else:
            print(f"         -> ERROR: {result.get('error')}")

    # Calculate final metrics
    metrics = calculate_metrics()
    print_report(metrics, processed=len(cases_to_process))

    # Save detailed results
    with open("batch_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "run_at": datetime.now().isoformat(),
            "metrics": metrics,
            "results": results
        }, f, indent=2, default=str)

    print("\nDetailed results saved to batch_results.json")
    return metrics

if __name__ == "__main__":
    # Start with 15 cases for first test
    main(limit=15)
