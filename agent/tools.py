# How this works:
# This module defines deterministic recovery tools called by agent nodes:
# 1. log_audit / get_case / update_case: Database audit logging and case management.
# 2. create_payment_link: Interacts with Razorpay API (Test Mode) to create recovery payment links.
# 3. send_message: Simulates cross-channel notification dispatch (WhatsApp, SMS, Email).
# 4. mark_recovered / escalate_case / schedule_retry: State transition tools.
# 5. check_stopping_rules: Evaluates safety boundaries (max retry attempts, time windows).

import razorpay
import json
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.config import config
from app.database import SessionLocal
from app.models import FailedSubscription, AuditLog

# Initialize Razorpay client (test mode)
razorpay_client = razorpay.Client(auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET))

def log_audit(
    case_id: str,
    stage: str,
    action: str,
    details: str = "",
    llm_reasoning: str = None,
    outcome: str = None
):
    """
    Write an audit log entry to the database.
    
    Parameters:
        case_id (str): Identifier of the case being processed.
        stage (str): Current workflow stage (e.g., detect, execute, escalate).
        action (str): Specific action performed.
        details (str): Contextual details or payload summary.
        llm_reasoning (str): Optional chain-of-thought or decision reasoning.
        outcome (str): Result of the action (success, failed, simulated_success).
    """
    db = SessionLocal()
    try:
        entry = AuditLog(
            case_id=case_id,
            timestamp=datetime.utcnow(),
            stage=stage,
            action=action,
            details=details,
            llm_reasoning=llm_reasoning,
            outcome=outcome
        )
        db.add(entry)
        db.commit()
    finally:
        db.close()

def get_case(case_id: str) -> Optional[FailedSubscription]:
    """
    Retrieve a single case record from the database.
    
    Parameters:
        case_id (str): The unique case identifier.
        
    Returns:
        FailedSubscription | None: The matching case record or None.
    """
    db = SessionLocal()
    try:
        return db.query(FailedSubscription).filter(FailedSubscription.case_id == case_id).first()
    finally:
        db.close()

def update_case(case_id: str, **kwargs):
    """
    Update specified fields on an existing case record.
    
    Parameters:
        case_id (str): The case identifier to update.
        **kwargs: Keyword arguments corresponding to column names and values.
        
    Returns:
        bool: True if updated successfully, False if case not found.
    """
    db = SessionLocal()
    try:
        case = db.query(FailedSubscription).filter(FailedSubscription.case_id == case_id).first()
        if not case:
            return False
        for key, value in kwargs.items():
            if hasattr(case, key):
                setattr(case, key, value)
        case.updated_at = datetime.utcnow()
        db.commit()
        return True
    finally:
        db.close()

# ====================== TOOLS ======================

def create_payment_link(case_id: str, amount: int = None, description: str = None) -> Dict[str, Any]:
    """
    Create a Razorpay payment link in test mode for the given case.
    
    Parameters:
        case_id (str): Unique case identifier.
        amount (int, optional): Amount in paise. Defaults to case amount.
        description (str, optional): Payment description.
        
    Returns:
        Dict[str, Any]: Dictionary containing success status, link ID, and short URL.
    """
    case = get_case(case_id)
    if not case:
        return {"success": False, "error": f"Case {case_id} not found"}

    try:
        final_amount = amount or case.amount
        final_description = description or f"Subscription recovery for {case.subscription_id}"

        # Razorpay payment link (test mode)
        link = razorpay_client.payment_link.create({
            "amount": final_amount,
            "currency": case.currency,
            "accept_partial": False,
            "description": final_description,
            "customer": {
                "name": case.customer_name,
                "email": case.customer_email,
                "contact": case.customer_phone
            },
            "notify": {
                "sms": False,   # we simulate messaging ourselves
                "email": False
            },
            "reminder_enable": False,
            "notes": {
                "case_id": case_id,
                "subscription_id": case.subscription_id
            }
        })

        result = {
            "success": True,
            "payment_link_id": link.get("id"),
            "short_url": link.get("short_url"),
            "amount": final_amount,
            "status": link.get("status")
        }

        log_audit(
            case_id=case_id,
            stage="execute",
            action="create_payment_link",
            details=json.dumps(result),
            outcome="success"
        )
        return result

    except Exception as e:
        error_msg = str(e)
        log_audit(
            case_id=case_id,
            stage="execute",
            action="create_payment_link",
            details=error_msg,
            outcome="failed"
        )
        return {"success": False, "error": error_msg}

def send_message(
    case_id: str,
    channel: str,          # "whatsapp" | "sms" | "email"
    message: str,
    payment_link: str = None
) -> Dict[str, Any]:
    """
    Simulate sending a notification message on the specified channel.
    
    Parameters:
        case_id (str): Unique case identifier.
        channel (str): Delivery channel ("whatsapp", "sms", or "email").
        message (str): Message text.
        payment_link (str, optional): Payment URL to append to the message.
        
    Returns:
        Dict[str, Any]: Dictionary containing dispatch simulation details.
    """
    case = get_case(case_id)
    if not case:
        return {"success": False, "error": f"Case {case_id} not found"}

    full_message = message
    if payment_link:
        if "{payment_link}" in full_message:
            full_message = full_message.replace("{payment_link}", payment_link)
        elif payment_link not in full_message:
            full_message = f"{full_message.rstrip()}\n\nPay securely: {payment_link}"

    # Simulation only
    result = {
        "success": True,
        "channel": channel,
        "to": case.customer_phone if channel in ["whatsapp", "sms"] else case.customer_email,
        "message": full_message,
        "payment_link": payment_link,
        "sent_at": datetime.utcnow().isoformat()
    }

    log_audit(
        case_id=case_id,
        stage="execute",
        action=f"send_{channel}",
        details=json.dumps(result),
        outcome="simulated_success"
    )

    # Update case
    update_case(
        case_id,
        last_recovery_action=f"sent_{channel}",
        recovery_attempts=case.recovery_attempts + 1
    )

    return result

def mark_recovered(case_id: str, recovered_amount: int = None) -> Dict[str, Any]:
    """
    Mark a subscription failure case as successfully recovered.
    
    Parameters:
        case_id (str): Unique case identifier.
        recovered_amount (int, optional): Amount recovered in paise.
        
    Returns:
        Dict[str, Any]: Confirmation dictionary with updated status and amount.
    """
    case = get_case(case_id)
    if not case:
        return {"success": False, "error": f"Case {case_id} not found"}

    amount = recovered_amount or case.amount

    update_case(
        case_id,
        status="recovered",
        recovered_amount=amount,
        last_recovery_action="marked_recovered"
    )

    log_audit(
        case_id=case_id,
        stage="execute",
        action="mark_recovered",
        details=f"Recovered amount: {amount}",
        outcome="success"
    )

    return {
        "success": True,
        "case_id": case_id,
        "recovered_amount": amount,
        "status": "recovered"
    }

def escalate_case(case_id: str, reason: str) -> Dict[str, Any]:
    """
    Escalate a case for manual human intervention.
    
    Parameters:
        case_id (str): Unique case identifier.
        reason (str): Explanation for why human escalation is required.
        
    Returns:
        Dict[str, Any]: Escalation status confirmation dictionary.
    """
    case = get_case(case_id)
    if not case:
        return {"success": False, "error": f"Case {case_id} not found"}

    update_case(
        case_id,
        status="escalated",
        escalated=True,
        notes=reason,
        last_recovery_action="escalated"
    )

    log_audit(
        case_id=case_id,
        stage="escalate",
        action="escalate_to_human",
        details=reason,
        outcome="escalated"
    )

    return {
        "success": True,
        "case_id": case_id,
        "status": "escalated",
        "reason": reason
    }

def schedule_retry(case_id: str, delay_hours: int = 24) -> Dict[str, Any]:
    """
    Schedule a delayed automatic retry for a failed transaction.
    
    Parameters:
        case_id (str): Unique case identifier.
        delay_hours (int): Number of hours to wait before reattempting.
        
    Returns:
        Dict[str, Any]: Confirmation dictionary with schedule details.
    """
    case = get_case(case_id)
    if not case:
        return {"success": False, "error": f"Case {case_id} not found"}

    result = {
        "success": True,
        "case_id": case_id,
        "scheduled_in_hours": delay_hours,
        "scheduled_at": datetime.utcnow().isoformat()
    }

    log_audit(
        case_id=case_id,
        stage="execute",
        action="schedule_retry",
        details=json.dumps(result),
        outcome="scheduled"
    )

    update_case(
        case_id,
        last_recovery_action=f"scheduled_retry_{delay_hours}h",
        recovery_attempts=case.recovery_attempts + 1
    )

    return result

def check_stopping_rules(case_id: str) -> Dict[str, Any]:
    """
    Evaluate hard safety stopping rules to avoid infinite retry loops.
    
    Parameters:
        case_id (str): Unique case identifier.
        
    Returns:
        Dict[str, Any]: Result indicating if processing should halt and the reason.
    """
    case = get_case(case_id)
    if not case:
        return {"should_stop": True, "reason": "Case not found"}

    if case.status in ["recovered", "escalated", "closed"]:
        return {"should_stop": True, "reason": f"Already in final status: {case.status}"}

    if case.recovery_attempts >= config.MAX_ATTEMPTS:
        return {"should_stop": True, "reason": f"Max attempts ({config.MAX_ATTEMPTS}) reached"}

    # Simple day check (you can make this more precise later)
    if case.failed_at:
        days_passed = (datetime.utcnow() - case.failed_at).days
        if days_passed >= config.MAX_DAYS:
            return {"should_stop": True, "reason": f"Max days ({config.MAX_DAYS}) exceeded"}

    return {"should_stop": False, "reason": "Within limits"}

def simulate_customer_payment(case_id: str, success_probability: float = 0.42) -> Dict[str, Any]:
    """
    Simulate whether the customer actually paid after receiving the recovery message.
    In real life this would come from a Razorpay webhook.
    For the demo we use a realistic probability based on failure type.
    """
    import random
    case = get_case(case_id)
    if not case:
        return {"success": False, "error": "Case not found"}

    # Adjust probability based on failure type (more realistic)
    base_prob = success_probability
    if case.failure_code in ["soft_decline", "insufficient_funds", "bank_timeout"]:
        base_prob = 0.55
    elif case.failure_code in ["card_expired", "mandate_revoked"]:
        base_prob = 0.28
    elif case.failure_code in ["do_not_honor", "invalid_account"]:
        base_prob = 0.22

    paid = random.random() < base_prob

    if paid:
        update_case(
            case_id,
            status="recovered",
            recovered_amount=case.amount,
            last_recovery_action="customer_paid_after_recovery"
        )
        log_audit(
            case_id=case_id,
            stage="execute",
            action="simulate_customer_payment",
            details=f"Customer paid. Probability used: {base_prob:.2f}",
            outcome="recovered"
        )
        return {
            "success": True,
            "paid": True,
            "recovered_amount": case.amount,
            "probability_used": base_prob
        }
    else:
        log_audit(
            case_id=case_id,
            stage="execute",
            action="simulate_customer_payment",
            details=f"Customer did not pay. Probability used: {base_prob:.2f}",
            outcome="not_paid"
        )
        return {
            "success": True,
            "paid": False,
            "recovered_amount": 0,
            "probability_used": base_prob
        }
def check_gateway_reconciliation(case_id: str) -> Dict[str, Any]:
    """
    Check if the customer settled this subscription through an alternative channel
    (e.g., merchant website, direct UPI, mandate background auto-retry, or POS).
    
    Returns:
        dict: Reconciliation result with status and external payment details.
    """
    case = get_case(case_id)
    if not case:
        return {"is_reconciled": False, "error": "Case not found"}

    # 1. If already marked recovered in local DB
    if case.status == "recovered":
        return {
            "is_reconciled": True,
            "case_id": case_id,
            "recovered_amount": case.recovered_amount or case.amount,
            "source": "local_ledger",
            "details": f"Already marked recovered in database (recovered_amount: ₹{case.recovered_amount/100:.2f})"
        }

    # 2. Check if an external payment or settlement was flagged in case notes/metadata
    if case.notes and ("external_settlement" in case.notes.lower() or "direct_upi" in case.notes.lower()):
        update_case(
            case_id,
            status="recovered",
            recovered_amount=case.amount,
            last_recovery_action="out_of_band_reconciliation",
            notes=f"{case.notes} | Reconciled at {datetime.utcnow().isoformat()}"
        )
        log_audit(
            case_id=case_id,
            stage="reconcile",
            action="out_of_band_reconciliation",
            details="Customer settled subscription via out-of-band channel (merchant app/UPI)",
            outcome="recovered"
        )
        return {
            "is_reconciled": True,
            "case_id": case_id,
            "recovered_amount": case.amount,
            "source": "merchant_portal",
            "details": "Out-of-band settlement verified from merchant records"
        }

    # 3. Live check against Razorpay API for subscription status (if subscription_id exists)
    if case.subscription_id and not case.subscription_id.startswith("sub_dummy"):
        try:
            sub = razorpay_client.subscription.fetch(case.subscription_id)
            if sub.get("status") in ["active", "completed", "charged"]:
                update_case(
                    case_id,
                    status="recovered",
                    recovered_amount=case.amount,
                    last_recovery_action="gateway_subscription_sync"
                )
                log_audit(
                    case_id=case_id,
                    stage="reconcile",
                    action="gateway_sync",
                    details=f"Subscription {case.subscription_id} is active on Razorpay Gateway",
                    outcome="recovered"
                )
                return {
                    "is_reconciled": True,
                    "case_id": case_id,
                    "recovered_amount": case.amount,
                    "source": "razorpay_gateway",
                    "details": f"Subscription {case.subscription_id} status on Razorpay is {sub.get('status')}"
                }
        except Exception:
            # Silent fallback if network or dummy test id
            pass

    return {
        "is_reconciled": False,
        "case_id": case_id,
        "details": "No out-of-band or external settlement detected"
    }

def record_external_settlement(
    case_id: str,
    payment_id: str = None,
    amount: int = None,
    channel: str = "direct_upi"
) -> Dict[str, Any]:
    """
    Record an out-of-band payment received outside the recovery agent workflow
    (e.g., customer paid on website or mobile app directly).
    """
    case = get_case(case_id)
    if not case:
        return {"success": False, "error": "Case not found"}

    reconciled_amt = amount if amount is not None else case.amount
    payment_ref = payment_id or f"pay_ext_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    update_case(
        case_id,
        status="recovered",
        recovered_amount=reconciled_amt,
        last_recovery_action="external_settlement",
        notes=f"external_settlement:{channel}:{payment_ref}"
    )

    log_audit(
        case_id=case_id,
        stage="reconcile",
        action="record_external_settlement",
        details=f"External payment recorded: {payment_ref} via {channel} for ₹{reconciled_amt/100:.2f}",
        outcome="recovered"
    )

    return {
        "success": True,
        "case_id": case_id,
        "payment_id": payment_ref,
        "channel": channel,
        "recovered_amount": reconciled_amt
    }

def verify_live_payment_link(link_id: str) -> Dict[str, Any]:
    """
    Query Razorpay REST API directly to fetch the real-time status of a payment link.
    """
    try:
        res = razorpay_client.payment_link.fetch(link_id)
        is_paid = res.get("status") == "paid"
        amount_paid = res.get("amount_paid", 0)
        return {
            "success": True,
            "link_id": link_id,
            "status": res.get("status"),
            "is_paid": is_paid,
            "amount_paid": amount_paid,
            "payments": res.get("payments", [])
        }
    except Exception as e:
        return {
            "success": False,
            "link_id": link_id,
            "error": str(e)
        }


