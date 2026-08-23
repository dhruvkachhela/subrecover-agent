import json
from datetime import datetime
from agent.graph import recovery_graph
from agent.state import AgentState
from app.database import SessionLocal, get_all_recoverable_cases
from app.models import FailedSubscription, AuditLog
from collections import Counter, defaultdict

def run_recovery_for_case(case_id: str) -> dict:
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

    try:
        final_state = recovery_graph.invoke(initial_state)
        return {
            "case_id": case_id,
            "success": True,
            "is_recovered": final_state.get("is_recovered", False),
            "is_escalated": final_state.get("is_escalated", False),
            "final_status": final_state.get("final_status"),
            "stop_reason": final_state.get("stop_reason"),
            "steps": final_state.get("step_count", 0),
            "history": final_state.get("history", []),
            "case_data": final_state.get("case_data")
        }
    except Exception as e:
        return {
            "case_id": case_id,
            "success": False,
            "error": str(e)
        }

def calculate_metrics(results: list):
    db = SessionLocal()
    try:
        all_cases = db.query(FailedSubscription).all()
        total_cases = len(all_cases)
        total_at_risk = sum(c.amount for c in all_cases) / 100
        recovered_cases = [c for c in all_cases if c.status == "recovered"]
        escalated_cases = [c for c in all_cases if c.status == "escalated"]
        open_cases = [c for c in all_cases if c.status == "failed_recoverable"]

        total_recovered = sum(c.recovered_amount for c in recovered_cases) / 100
        recovery_rate = (len(recovered_cases) / total_cases * 100) if total_cases else 0

        # From this batch
        batch_recovered = sum(1 for r in results if r.get("is_recovered"))
        batch_escalated = sum(1 for r in results if r.get("is_escalated"))
        batch_steps = [r.get("steps", 0) for r in results if r.get("success")]
        avg_steps = sum(batch_steps) / len(batch_steps) if batch_steps else 0

        failure_breakdown = Counter(c.failure_code for c in all_cases)

        return {
            "total_cases_in_db": total_cases,
            "total_revenue_at_risk_inr": round(total_at_risk, 2),
            "recovered_cases": len(recovered_cases),
            "total_recovered_inr": round(total_recovered, 2),
            "recovery_rate_percent": round(recovery_rate, 2),
            "escalated_cases": len(escalated_cases),
            "still_open": len(open_cases),
            "batch_processed": len(results),
            "batch_recovered": batch_recovered,
            "batch_escalated": batch_escalated,
            "batch_avg_steps": round(avg_steps, 2),
            "failure_code_breakdown": dict(failure_breakdown)
        }
    finally:
        db.close()

def print_report(metrics: dict):
    print("\n" + "="*70)
    print("SUBRECOVER AGENT - LARGE BATCH REPORT")
    print("="*70)
    print(f"Processed in this run     : {metrics['batch_processed']}")
    print(f"Batch Recovered           : {metrics['batch_recovered']}")
    print(f"Batch Escalated           : {metrics['batch_escalated']}")
    print(f"Average Steps per case    : {metrics['batch_avg_steps']}")
    print("-"*70)
    print(f"Total Cases in System     : {metrics['total_cases_in_db']}")
    print(f"Total Revenue at Risk     : Rs. {metrics['total_revenue_at_risk_inr']:,.2f}")
    print(f"Successfully Recovered    : Rs. {metrics['total_recovered_inr']:,.2f}")
    print(f"Overall Recovery Rate     : {metrics['recovery_rate_percent']}%")
    print(f"Escalated (total)         : {metrics['escalated_cases']}")
    print(f"Still Open                : {metrics['still_open']}")
    print("\nFailure Code Breakdown:")
    for code, count in metrics["failure_code_breakdown"].items():
        print(f"  - {code:<25} : {count}")
    print("="*70)

def main(limit: int = 40):
    print(f"\nStarting LARGE batch recovery (limit={limit})...")
    print(f"Time: {datetime.now().isoformat()}")

    cases = get_all_recoverable_cases()
    cases_to_process = cases[:limit]

    print(f"Found {len(cases)} recoverable cases. Processing first {len(cases_to_process)}...\n")

    results = []
    for i, case in enumerate(cases_to_process, 1):
        print(f"[{i}/{len(cases_to_process)}] {case.case_id} | {case.customer_name} | Rs. {case.amount/100:.2f} | {case.failure_code}")
        result = run_recovery_for_case(case.case_id)
        results.append(result)

        if result.get("success"):
            status = "RECOVERED" if result.get("is_recovered") else ("ESCALATED" if result.get("is_escalated") else "STOPPED")
            print(f"         -> {status} | Steps: {result.get('steps')}")
        else:
            print(f"         -> ERROR: {result.get('error')}")

    metrics = calculate_metrics(results)
    print_report(metrics)

    # Save full results
    with open("large_batch_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "run_at": datetime.now().isoformat(),
            "metrics": metrics,
            "results": results
        }, f, indent=2, default=str)

    print("\nFull results saved to large_batch_results.json")
    return metrics

if __name__ == "__main__":
    main(limit=20)
