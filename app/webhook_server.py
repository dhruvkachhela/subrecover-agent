"""
FastAPI Webhook Server for SubRecover Agent
Listens to real Razorpay Webhook events (subscription.charged_failed, payment_link.paid, payment.captured)
and drives the asynchronous agentic recovery lifecycle.
"""

import sys
from pathlib import Path

# Add project root directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import hmac
import hashlib
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, Header, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from app.config import config
from app.database import SessionLocal
from app.models import FailedSubscription, AuditLog
from agent.graph import recovery_graph
from agent.state import AgentState
from agent.tools import log_audit, update_case, get_case

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("subrecover-webhook")

app = FastAPI(
    title="SubRecover Agent Webhook Engine",
    description="Event-Driven Razorpay Subscription Recovery & Settlement Webhook API",
    version="1.0.0"
)

def verify_razorpay_signature(body: bytes, signature: Optional[str], secret: Optional[str]) -> bool:
    """Validate HMAC SHA256 signature from Razorpay."""
    if not secret or not signature:
        # In local test/demo mode, allow unsigned payloads if secret not set
        return True
    try:
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected_signature, signature)
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False

def run_agent_in_background(case_id: str):
    """Execute LangGraph recovery agent in background worker."""
    logger.info(f"Triggering background recovery graph for {case_id}")
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
        logger.info(f"Case {case_id} completed via webhook trigger. Status: {final_state.get('final_status')}")
    except Exception as exc:
        logger.error(f"Error executing recovery graph for {case_id}: {exc}")

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "subrecover-webhook-engine",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/webhook/razorpay")
async def handle_razorpay_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_razorpay_signature: Optional[str] = Header(None)
):
    """
    Main Razorpay Webhook Ingestion Endpoint.
    Handles:
    - subscription.charged_failed / payment.failed (Spawns Agent Recovery)
    - payment_link.paid (Closes Case as Recovered)
    - payment.captured (Reconciles Out-of-Band Payments)
    """
    raw_body = await request.body()
    
    # Optional webhook secret verification
    webhook_secret = getattr(config, "RAZORPAY_WEBHOOK_SECRET", None)
    if not verify_razorpay_signature(raw_body, x_razorpay_signature, webhook_secret):
        raise HTTPException(status_code=400, detail="Invalid Razorpay Webhook Signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = payload.get("event")
    event_id = payload.get("event_id", f"evt_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")
    logger.info(f"Ingested Razorpay webhook event: {event_type} (ID: {event_id})")

    # ==================== EVENT 1: PAYMENT FAILURE INGESTION ====================
    if event_type in ["subscription.charged_failed", "payment.failed", "subscription.cancelled"]:
        sub_entity = payload.get("payload", {}).get("subscription", {}).get("entity", {})
        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        
        sub_id = sub_entity.get("id") or payment_entity.get("subscription_id") or f"sub_{event_id[:8]}"
        amount = payment_entity.get("amount") or sub_entity.get("plan", {}).get("amount", 29900)
        email = payment_entity.get("email") or "customer@example.com"
        phone = payment_entity.get("contact") or "+919876543210"
        err_code = payment_entity.get("error_code") or "bank_timeout"
        err_desc = payment_entity.get("error_description") or "Subscription charge authorization failed at gateway"

        db = SessionLocal()
        try:
            # Find existing or allocate new case
            case = db.query(FailedSubscription).filter(FailedSubscription.subscription_id == sub_id).first()
            if not case:
                # Count cases to generate CASE ID
                count = db.query(FailedSubscription).count() + 1
                case_id = f"CASE{count:04d}"
                case = FailedSubscription(
                    case_id=case_id,
                    merchant_id=payload.get("account_id") or "mer_rzp_subrecover",
                    customer_id=payment_entity.get("customer_id") or f"cust_{sub_id[:10]}",
                    customer_name=email.split("@")[0].capitalize(),
                    customer_phone=phone,
                    customer_email=email,
                    subscription_id=sub_id,
                    amount=amount,
                    failure_code=err_code,
                    failure_description=err_desc,
                    payment_method="card",
                    status="failed_recoverable",
                    notes=f"Ingested from webhook {event_id}"
                )
                db.add(case)
                db.commit()
            else:
                case_id = case.case_id

            log_audit(
                case_id=case_id,
                stage="webhook",
                action=f"webhook_{event_type}",
                details=f"Ingested {event_type} for subscription {sub_id}",
                outcome="case_queued"
            )

            # Trigger recovery graph asynchronously
            background_tasks.add_task(run_agent_in_background, case_id)

            return JSONResponse(
                status_code=200,
                content={
                    "status": "accepted",
                    "event": event_type,
                    "case_id": case_id,
                    "action": "recovery_agent_dispatched"
                }
            )
        finally:
            db.close()

    # ==================== EVENT 2: PAYMENT LINK SETTLED ====================
    elif event_type == "payment_link.paid":
        plink_entity = payload.get("payload", {}).get("payment_link", {}).get("entity", {})
        plink_id = plink_entity.get("id")
        amount_paid = plink_entity.get("amount_paid", 0)
        short_url = plink_entity.get("short_url")
        notes = plink_entity.get("notes", {})

        db = SessionLocal()
        try:
            case = None
            # 1. Direct match by case_id stored in payment_link notes
            if isinstance(notes, dict) and "case_id" in notes:
                case = db.query(FailedSubscription).filter(FailedSubscription.case_id == notes["case_id"]).first()
            # 2. Secondary match by short_url or plink_id in notes/audit logs
            if not case and short_url:
                case = db.query(FailedSubscription).filter(FailedSubscription.notes.like(f"%{short_url}%")).first()
            if not case and plink_id:
                case = db.query(FailedSubscription).filter(FailedSubscription.notes.like(f"%{plink_id}%")).first()

            if case:
                # Idempotency check: If already recovered, return success without duplicate logs
                if case.status == "recovered":
                    return {
                        "status": "already_processed",
                        "event": event_type,
                        "case_id": case.case_id
                    }

                case.status = "recovered"
                case.recovered_amount = amount_paid or case.amount
                case.last_recovery_action = "payment_link_paid_webhook"
                case.notes = f"Settled via Razorpay payment_link {plink_id}"
                db.commit()

                log_audit(
                    case_id=case.case_id,
                    stage="webhook",
                    action="payment_link.paid",
                    details=f"Payment link {plink_id} settled. Recovered ₹{amount_paid/100:.2f}",
                    outcome="recovered"
                )
                return {
                    "status": "success",
                    "event": event_type,
                    "case_id": case.case_id,
                    "reconciliation": "payment_link_recovered"
                }
            else:
                return {
                    "status": "unmatched",
                    "event": event_type,
                    "details": f"No active case mapped to link {plink_id}"
                }
        finally:
            db.close()

    # ==================== EVENT 3: OUT-OF-BAND PAYMENT CAPTURED ====================
    elif event_type in ["payment.captured", "subscription.charged"]:
        pay_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        sub_id = pay_entity.get("subscription_id")
        email = pay_entity.get("email")
        amt = pay_entity.get("amount", 0)

        db = SessionLocal()
        try:
            # 1. Primary match by unique subscription_id
            if sub_id:
                case = db.query(FailedSubscription).filter(FailedSubscription.subscription_id == sub_id).first()
            
            # 2. Secondary match by case_id stored in Razorpay payment notes
            notes = pay_entity.get("notes", {})
            if not case and isinstance(notes, dict) and "case_id" in notes:
                case = db.query(FailedSubscription).filter(FailedSubscription.case_id == notes["case_id"]).first()

            # 3. Fallback match by email ONLY if exact payment amount matches the failed subscription amount
            if not case and email:
                case = db.query(FailedSubscription).filter(
                    FailedSubscription.customer_email == email,
                    FailedSubscription.amount == amt,
                    FailedSubscription.status == "failed_recoverable"
                ).first()

            if case:
                # Idempotency check: If already recovered, return early
                if case.status == "recovered":
                    return {
                        "status": "already_processed",
                        "event": event_type,
                        "case_id": case.case_id
                    }

                case.status = "recovered"
                case.recovered_amount = amt or case.amount
                case.last_recovery_action = "out_of_band_webhook_sync"
                case.notes = f"Settled via gateway {event_type} pay_id: {pay_entity.get('id')}"
                db.commit()

                log_audit(
                    case_id=case.case_id,
                    stage="webhook",
                    action=f"webhook_{event_type}",
                    details=f"Payment captured externally ({event_type}). Reconciled ₹{amt/100:.2f}",
                    outcome="recovered"
                )
                return {
                    "status": "reconciled",
                    "event": event_type,
                    "case_id": case.case_id,
                    "reconciliation": "out_of_band_settlement"
                }
            return {
                "status": "ignored",
                "event": event_type,
                "details": "No pending recoverable case matched"
            }
        finally:
            db.close()

    # Default fallback for unhandled Razorpay events
    return {
        "status": "ignored",
        "event": event_type,
        "message": "Event received but no action required."
    }

if __name__ == "__main__":
    import uvicorn
    print("Starting SubRecover Webhook Engine on http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
