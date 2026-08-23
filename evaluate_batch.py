import json
from collections import defaultdict, Counter
from pathlib import Path

RESULTS_FILE = "large_batch_results.json"

HARD_FAILURES = {"mandate_revoked", "invalid_account", "card_expired", "do_not_honor"}
SOFT_FAILURES = {"bank_timeout", "insufficient_funds", "soft_decline", "issuer_unavailable"}

def load_results():
    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["results"], data.get("metrics", {})

def evaluate(results):
    total = len(results)
    recovered = 0
    escalated = 0
    errors = 0

    hard_total = 0
    hard_early_escalated = 0          # escalated in <= 2 steps
    soft_total = 0
    soft_with_channel_switch = 0
    repeated_action_cases = 0
    max_steps_violations = 0
    audit_incomplete = 0

    for r in results:
        if not r.get("success"):
            errors += 1
            continue

        if r.get("is_recovered"):
            recovered += 1
        if r.get("is_escalated"):
            escalated += 1

        steps = r.get("steps", 0)
        history = r.get("history", [])
        case_data = r.get("case_data") or {}
        failure_code = case_data.get("failure_code", "unknown")

        # Max steps check
        if steps > 5:
            max_steps_violations += 1

        # Audit completeness
        for h in history:
            if not (h.get("thought") and h.get("action") and h.get("observation") is not None):
                audit_incomplete += 1
                break

        # Repeated same action check
        actions = [h.get("action") for h in history]
        for i in range(1, len(actions)):
            if actions[i] == actions[i-1] and actions[i] in ["schedule_retry", "create_and_send_link"]:
                # Allow one repeat only if channel changed (simplified check)
                repeated_action_cases += 1
                break

        # Hard failure rule
        if failure_code in HARD_FAILURES:
            hard_total += 1
            if r.get("is_escalated") and steps <= 2:
                hard_early_escalated += 1

        # Soft failure rule – did it try more than one step or different approach?
        if failure_code in SOFT_FAILURES:
            soft_total += 1
            channels = set()
            for h in history:
                inp = h.get("action_input") or {}
                ch = inp.get("channel")
                if ch:
                    channels.add(ch)
            if len(channels) >= 2 or steps >= 2:
                soft_with_channel_switch += 1

    report = {
        "total_processed": total,
        "recovered": recovered,
        "escalated": escalated,
        "errors": errors,
        "recovery_rate_batch": round(recovered / total * 100, 1) if total else 0,
        "hard_failures": hard_total,
        "hard_early_escalation_rate": round(hard_early_escalated / hard_total * 100, 1) if hard_total else 0,
        "soft_failures": soft_total,
        "soft_adaptive_rate": round(soft_with_channel_switch / soft_total * 100, 1) if soft_total else 0,
        "repeated_action_cases": repeated_action_cases,
        "max_steps_violations": max_steps_violations,
        "audit_incomplete_cases": audit_incomplete,
    }
    return report

def print_evaluation(report, metrics):
    print("\n" + "="*70)
    print("SUBRECOVER AGENT - RULE-BASED EVALUATION REPORT")
    print("="*70)

    print("\n1. BUSINESS OUTCOMES")
    print(f"   Batch Recovery Rate          : {report['recovery_rate_batch']}%")
    print(f"   Cases Recovered              : {report['recovered']}")
    print(f"   Cases Escalated              : {report['escalated']}")
    print(f"   Revenue Recovered (system)   : Rs. {metrics.get('total_recovered_inr', 0):,.2f}")

    print("\n2. DECISION QUALITY & SAFETY (Rule-based)")
    print(f"   Hard failures handled early  : {report['hard_early_escalation_rate']}%  ({report['hard_failures']} hard cases)")
    print(f"   Soft failures showed adaptation: {report['soft_adaptive_rate']}%  ({report['soft_failures']} soft cases)")
    print(f"   Cases with repeated actions  : {report['repeated_action_cases']}")
    print(f"   Max steps violations         : {report['max_steps_violations']}")
    print(f"   Audit incomplete cases       : {report['audit_incomplete_cases']}")

    print("\n3. SAFETY SUMMARY")
    safety_ok = (
        report['max_steps_violations'] == 0 and
        report['audit_incomplete_cases'] == 0
    )
    print(f"   Safety rules respected       : {'YES' if safety_ok else 'NO'}")
    print("="*70)

if __name__ == "__main__":
    results, metrics = load_results()
    report = evaluate(results)
    print_evaluation(report, metrics)

    # Save evaluation
    with open("evaluation_report.json", "w", encoding="utf-8") as f:
        json.dump({"evaluation": report, "metrics": metrics}, f, indent=2)
    print("\nEvaluation saved to evaluation_report.json")
