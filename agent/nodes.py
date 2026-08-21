# How this works:
# Defines the individual functional nodes in the LangGraph workflow:
# 1. load_case_node: Loads case records from SQLite database into AgentState.
# 2. diagnose_node: Prompts NVIDIA NIM LLM to determine root cause and recoverability.
# 3. decide_intervention_node: Prompts LLM to select channel, message body, and action.
# 4. execute_node: Calls deterministic tools (Razorpay link, message dispatch, retry schedule).
# 5. check_stop_node: Evaluates safety stopping boundaries and escalates if max limits exceeded.

import json
from datetime import datetime
from typing import Dict, Any
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import config
from agent.tools import (
    get_case, update_case, log_audit,
    create_payment_link, send_message,
    mark_recovered, escalate_case,
    schedule_retry, check_stopping_rules
)
from agent.state import AgentState

# Initialize LLM (NVIDIA NIM)
llm = ChatNVIDIA(
    model=config.NVIDIA_MODEL,
    api_key=config.NVIDIA_API_KEY,
    temperature=0.3
)

def load_case_node(state: AgentState) -> AgentState:
    """
    Load case details from the SQLite database into the agent state.
    
    Parameters:
        state (AgentState): Current graph state containing case_id.
        
    Returns:
        AgentState: Updated state populated with case_data dictionary.
    """
    case = get_case(state["case_id"])
    if not case:
        state["should_stop"] = True
        state["stop_reason"] = "Case not found"
        state["final_status"] = "error"
        return state

    state["case_data"] = {
        "case_id": case.case_id,
        "customer_name": case.customer_name,
        "customer_phone": case.customer_phone,
        "customer_email": case.customer_email,
        "amount": case.amount,
        "amount_rupees": case.amount / 100,
        "failure_code": case.failure_code,
        "failure_description": case.failure_description,
        "payment_method": case.payment_method,
        "previous_attempts": case.previous_attempts,
        "recovery_attempts": case.recovery_attempts,
        "status": case.status,
        "subscription_id": case.subscription_id
    }
    state["should_stop"] = False
    state["is_recovered"] = False
    state["is_escalated"] = False
    return state

def diagnose_node(state: AgentState) -> AgentState:
    """
    Diagnose the underlying root cause of the subscription payment failure using LLM.
    
    Parameters:
        state (AgentState): Current graph state containing case_data.
        
    Returns:
        AgentState: Updated state containing structured diagnosis JSON.
    """
    case = state["case_data"]

    system_prompt = """You are an expert payment recovery specialist working for an Indian fintech.
                        Your job is to diagnose why a subscription payment failed.

                        Respond ONLY with valid JSON in this exact format:
                        {
                        "root_cause": "one of: insufficient_funds | bank_issue | soft_decline | hard_decline | mandate_issue | expired_instrument | technical_error | unknown",
                        "severity": "high | medium | low",
                        "is_recoverable": true/false,
                        "recommended_strategy": "short recommendation",
                        "reasoning": "brief explanation"
                        }
                        """

    human_prompt = f"""
        Diagnose this failed subscription payment:

        Customer: {case['customer_name']}
        Amount: Rs.{case['amount_rupees']}
        Payment Method: {case['payment_method']}
        Failure Code: {case['failure_code']}
        Failure Description: {case['failure_description']}
        Previous attempts: {case['previous_attempts']}
        Recovery attempts so far: {case['recovery_attempts']}
        """

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ])
        content = response.content.strip()

        # Clean possible markdown
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        diagnosis = json.loads(content)
        state["diagnosis"] = diagnosis

        log_audit(
            case_id=state["case_id"],
            stage="diagnose",
            action="root_cause_analysis",
            details=json.dumps(diagnosis),
            llm_reasoning=diagnosis.get("reasoning"),
            outcome="success"
        )
    except Exception as e:
        state["diagnosis"] = {
            "root_cause": "unknown",
            "confidence": "low",
            "is_recoverable": True,
            "recommended_strategy": "retry with payment link",
            "reasoning": f"LLM error: {str(e)}"
        }
        log_audit(
            case_id=state["case_id"],
            stage="diagnose",
            action="root_cause_analysis",
            details=str(e),
            outcome="fallback"
        )

    return state

def decide_intervention_node(state: AgentState) -> AgentState:
    """
    Select the optimal recovery action, communication channel, and message template using LLM.
    
    Parameters:
        state (AgentState): Current graph state with case_data and diagnosis.
        
    Returns:
        AgentState: Updated state containing structured decision JSON.
    """
    case = state["case_data"]
    diagnosis = state.get("diagnosis", {})

    system_prompt = """You are an expert subscription recovery agent.
                        Based on the diagnosis, decide the single best next action.

                        You must respond ONLY with valid JSON in this exact format:
                        {
                        "action": "one of: send_whatsapp | send_sms | send_email | create_and_send_link | schedule_retry | escalate | mark_unrecoverable",
                        "channel": "whatsapp | sms | email | none",
                        "message_tone": "polite | urgent | helpful",
                        "message_body": "the exact message to send to the customer (in simple English or Hinglish if appropriate)",
                        "retry_delay_hours": 0,
                        "reasoning": "why you chose this action"
                        }

                        Rules you must respect:
                        - Prefer WhatsApp for Indian customers when possible.
                        - If hard decline or mandate_revoked -> lean toward asking customer to update payment method.
                        - If soft decline or insufficient_funds -> payment link + polite reminder is good.
                        - If too many attempts already -> escalate.
                        - Keep message short and clear.
                        """

    human_prompt = f"""
                        Case details:
                        {json.dumps(case, indent=2)}

                        Diagnosis:
                        {json.dumps(diagnosis, indent=2)}

Decide the best next intervention.
"""

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ])
        content = response.content.strip()

        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        decision = json.loads(content)
        state["decision"] = decision

        log_audit(
            case_id=state["case_id"],
            stage="decide",
            action="choose_intervention",
            details=json.dumps(decision),
            llm_reasoning=decision.get("reasoning"),
            outcome="success"
        )
    except Exception as e:
        # Safe fallback
        state["decision"] = {
            "action": "create_and_send_link",
            "channel": "whatsapp",
            "message_tone": "polite",
            "message_body": f"Hi {case['customer_name'].split()[0]}, your subscription payment of Rs.{case['amount_rupees']} failed. Please complete it using the link we are sending.",
            "retry_delay_hours": 0,
            "reasoning": f"Fallback due to LLM error: {str(e)}"
        }
        log_audit(
            case_id=state["case_id"],
            stage="decide",
            action="choose_intervention",
            details=str(e),
            outcome="fallback"
        )

    return state

def execute_node(state: AgentState) -> AgentState:
    """
    Execute the intervention strategy decided by the agent using deterministic tools.
    
    Parameters:
        state (AgentState): Current graph state containing decision details.
        
    Returns:
        AgentState: Updated state with execution_result dictionary.
    """
    case_id = state["case_id"]
    decision = state.get("decision", {})
    action = decision.get("action", "create_and_send_link")
    channel = decision.get("channel", "whatsapp")
    message_body = decision.get("message_body", "Please complete your pending subscription payment.")

    result = {"success": False, "action": action}

    try:
        if action in ["create_and_send_link", "send_whatsapp", "send_sms", "send_email"]:
            # Create payment link first
            link_res = create_payment_link(case_id)
            payment_url = link_res.get("short_url") if link_res.get("success") else None

            # Send message
            msg_res = send_message(
                case_id=case_id,
                channel=channel if channel != "none" else "whatsapp",
                message=message_body,
                payment_link=payment_url
            )

            # NEW: Simulate whether customer actually paid
            from agent.tools import simulate_customer_payment
            payment_sim = simulate_customer_payment(case_id)

            result = {
                "success": msg_res.get("success", False),
                "action": action,
                "payment_link": payment_url,
                "message_result": msg_res,
                "payment_simulation": payment_sim
            }

            if payment_sim.get("paid"):
                state["is_recovered"] = True
                state["final_status"] = "recovered"

        elif action == "schedule_retry":
            delay = decision.get("retry_delay_hours", 24)
            result = schedule_retry(case_id, delay_hours=delay)

        elif action == "escalate":
            reason = decision.get("reasoning", "LLM decided to escalate")
            result = escalate_case(case_id, reason)
            state["is_escalated"] = True
            state["should_stop"] = True
            state["stop_reason"] = "Escalated by agent"
            state["final_status"] = "escalated"

        elif action == "mark_unrecoverable":
            result = escalate_case(case_id, "Marked unrecoverable by agent")
            state["is_escalated"] = True
            state["should_stop"] = True
            state["final_status"] = "unrecoverable"

        else:
            # Default safe action
            link_res = create_payment_link(case_id)
            msg_res = send_message(case_id, "whatsapp", message_body, link_res.get("short_url"))
            result = {"success": True, "action": "fallback_send_link", "details": msg_res}

    except Exception as e:
        result = {"success": False, "error": str(e)}
        log_audit(case_id, "execute", action, str(e), outcome="failed")

    state["execution_result"] = result
    return state

def check_stop_node(state: AgentState) -> AgentState:
    """
    Apply stopping rule boundaries (attempt limits, timeframe checks) and auto-escalate if needed.
    
    Parameters:
        state (AgentState): Current graph state.
        
    Returns:
        AgentState: Updated state with should_stop and stop_reason flags.
    """
    if state.get("should_stop"):
        return state

    stop_check = check_stopping_rules(state["case_id"])
    if stop_check["should_stop"]:
        state["should_stop"] = True
        state["stop_reason"] = stop_check["reason"]

        # Auto escalate if max attempts reached
        if "Max attempts" in stop_check["reason"] or "Max days" in stop_check["reason"]:
            escalate_case(state["case_id"], stop_check["reason"])
            state["is_escalated"] = True
            state["final_status"] = "escalated"
    else:
        state["should_stop"] = False

    return state
