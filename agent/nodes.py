import json
from datetime import datetime
from typing import Dict, Any, List
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import config
from agent.tools import (
    get_case, update_case, log_audit,
    create_payment_link, send_message,
    mark_recovered, escalate_case,
    schedule_retry, check_stopping_rules,
    simulate_customer_payment, check_gateway_reconciliation
)
from agent.state import AgentState

# Initialize LLM
llm = ChatNVIDIA(
    model=config.NVIDIA_MODEL,
    api_key=config.NVIDIA_API_KEY,
    temperature=0.7
)

# ====================== HELPER ======================

def safe_json_parse(text: str) -> dict:
    """Clean and parse JSON from LLM response"""
    if not text or not isinstance(text, str):
        return {}
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) > 1:
            text = parts[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    try:
        res = json.loads(text)
        return res if isinstance(res, dict) else {}
    except Exception:
        return {}

# ====================== NODES ======================

def load_case_node(state: AgentState) -> AgentState:
    """Load case data and initialize agent memory"""
    case = get_case(state["case_id"])
    if not case:
        state["should_stop"] = True
        state["stop_reason"] = "Case not found"
        state["final_status"] = "error"
        return state

    # ========== OUT-OF-BAND PAYMENT RECONCILIATION ==========
    reconciliation = check_gateway_reconciliation(state["case_id"])
    if reconciliation.get("is_reconciled"):
        state["case_data"] = {
            "case_id": case.case_id,
            "customer_name": case.customer_name,
            "amount_rupees": round(case.amount / 100, 2),
            "failure_code": case.failure_code,
            "status": "recovered",
        }
        state["should_stop"] = True
        state["stop_reason"] = f"Payment reconciled out-of-band ({reconciliation.get('source', 'external')})"
        state["final_status"] = "recovered"
        state["is_recovered"] = True
        state["is_escalated"] = False
        state["history"] = []
        state["step_count"] = 0
        state["max_steps"] = 5
        return state

    # ========== HARD EARLY EXIT ==========
    if case.status in ["recovered", "escalated", "closed"]:
        state["case_data"] = {
            "case_id": case.case_id,
            "customer_name": case.customer_name,
            "amount_rupees": round(case.amount / 100, 2),
            "failure_code": case.failure_code,
            "status": case.status,
        }
        state["should_stop"] = True
        state["stop_reason"] = f"Case already in final status: {case.status}"
        state["final_status"] = case.status
        state["is_recovered"] = case.status == "recovered"
        state["is_escalated"] = case.status == "escalated"
        state["history"] = []
        state["step_count"] = 0
        state["max_steps"] = 5

        log_audit(
            case_id=state["case_id"],
            stage="load",
            action="early_exit_final_status",
            details=f"Refused to run. Existing status: {case.status}",
            outcome="stopped"
        )
        return state
    # =====================================

    state["case_data"] = {
        "case_id": case.case_id,
        "customer_name": case.customer_name,
        "customer_phone": case.customer_phone,
        "customer_email": case.customer_email,
        "amount": case.amount,
        "amount_rupees": round(case.amount / 100, 2),
        "failure_code": case.failure_code,
        "failure_description": case.failure_description,
        "payment_method": case.payment_method,
        "previous_attempts": case.previous_attempts,
        "recovery_attempts": case.recovery_attempts,
        "status": case.status,
        "subscription_id": case.subscription_id
    }

    # Initialize agent memory
    state["history"] = []
    state["step_count"] = 0
    state["max_steps"] = 5
    state["should_stop"] = False
    state["stop_reason"] = None
    state["is_recovered"] = False
    state["is_escalated"] = False
    state["final_status"] = None
    state["current_thought"] = None
    state["current_action"] = None
    state["current_action_input"] = None
    state["current_observation"] = None
    state["current_reflection"] = None

    log_audit(
        case_id=state["case_id"],
        stage="load",
        action="case_loaded",
        details=f"Loaded case {state['case_id']}",
        outcome="success"
    )
    return state

def diagnose_node(state: AgentState) -> AgentState:
    """
    Sub-Agent 1: Financial & Gateway Diagnostic Agent.
    Evaluates failure severity, bank network health, previous attempts, and selects the recovery action & channel.
    """
    case = state.get("case_data") or {}
    if not case:
        state["should_stop"] = True
        state["stop_reason"] = "Case data is missing or uninitialized"
        state["final_status"] = "error"
        return state

    history = state.get("history") or []
    step = state.get("step_count", 0) + 1

    history_text = ""
    used_channels = []
    if history:
        history_text = "\n\nPrevious Recovery Attempts:\n"
        for h in (history or []):
            if not isinstance(h, dict):
                continue
            act_in = h.get('action_input') or {}
            ch = act_in.get('channel') if isinstance(act_in, dict) else None
            if ch:
                used_channels.append(ch)
            obs = h.get('observation') or {}
            paid_str = "PAID" if (obs.get("customer_paid") if isinstance(obs, dict) else False) else "NOT PAID"
            history_text += f"- Step {h.get('step', 1)}: Channel '{ch}' | Customer Status: {paid_str} | Reflection: {h.get('reflection','')}\n"

    system_prompt = """You are a senior Financial Diagnostics & Payment Gateway Recovery Specialist for Razorpay India.

Your role:
1. Diagnose the root cause of recurring subscription payment failures.
2. Determine if the failure is recoverable (soft failure) or non-recoverable (hard failure).
3. Select the best recovery action and channel according to fintech dunning rules.

### Action Options:
- "create_and_send_link": Generate a live Razorpay payment link and dispatch a customer nudge.
- "schedule_retry": Schedule an automated mandate retry (use only for transient bank downtimes/issuer unavailability).
- "escalate": Immediately escalate to human operations (for all hard failures or exhausted attempts).
- "stop": Terminate recovery workflow.

### Strict Fintech Decision Rules:
1. Hard Failures (mandate_revoked, invalid_account, card_expired, do_not_honor):
   - ALWAYS choose action "escalate" at Step 1. Automated nudges cannot fix permanently revoked or invalid mandates.
2. Soft Failures (bank_timeout, insufficient_funds, soft_decline, issuer_unavailable):
   - Step 1: Default to channel "whatsapp" (highest customer engagement in India).
   - Step 2: If previous WhatsApp attempt went unacknowledged, pivot to channel "sms".
   - Step 3: If SMS went unacknowledged, pivot to channel "email" or "schedule_retry".
   - NEVER repeat the same channel consecutively.
3. If step >= max_steps:
   - Choose action "escalate".

### Output Format (Strict JSON ONLY):
{
  "diagnosis": {
    "root_cause": "Plain English description of why payment failed",
    "severity": "hard_failure | soft_failure",
    "is_recoverable": true | false
  },
  "thought": "Clear tactical rationale explaining why this action and channel were chosen",
  "action": "create_and_send_link | schedule_retry | escalate | stop",
  "channel": "whatsapp | sms | email",
  "retry_delay_hours": 0,
  "reason": "Escalation reason if action is escalate"
}
"""

    human_prompt = f"""
Current Case Snapshot:
- Case ID: {case.get('case_id')}
- Customer: {case.get('customer_name')}
- Amount: ₹{case.get('amount_rupees')}
- Failure Code: {case.get('failure_code')}
- Current Step: {step} of maximum {state.get('max_steps', 5)}
- Channels Already Used: {used_channels if used_channels else 'None'}
{history_text}

Perform root-cause diagnosis and output your action decision in JSON.
"""

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ])
        parsed = safe_json_parse(response.content)

        hard_failure_codes = [
            "mandate_revoked", "invalid_account", "card_expired", "do_not_honor",
            "account_closed", "stolen_card", "fraudulent", "invalid_bank"
        ]
        is_hard_failure = case.get("failure_code") in hard_failure_codes
        default_act = "escalate" if is_hard_failure else "create_and_send_link"
        action = parsed.get("action") or default_act
        if is_hard_failure:
            action = "escalate"

        state["diagnosis"] = parsed.get("diagnosis", {})
        state["current_thought"] = parsed.get("thought", "Diagnostic completed")
        state["current_action"] = action
        
        # Enforce channel rotation if duplicate
        decided_channel = parsed.get("channel", "whatsapp")
        if used_channels and decided_channel == used_channels[-1] and action == "create_and_send_link":
            if decided_channel == "whatsapp":
                decided_channel = "sms"
            elif decided_channel == "sms":
                decided_channel = "email"

        state["current_action_input"] = {
            "channel": decided_channel,
            "retry_delay_hours": parsed.get("retry_delay_hours", 0),
            "reason": parsed.get("reason", "Hard failure detected" if is_hard_failure else "")
        }
        state["step_count"] = step

        log_audit(
            case_id=state["case_id"],
            stage="diagnose",
            action="gateway_diagnosis",
            details=json.dumps(parsed),
            llm_reasoning=parsed.get("thought"),
            outcome="success"
        )
    except Exception as e:
        is_hard_failure = case.get("failure_code") in ["mandate_revoked", "invalid_account", "card_expired", "do_not_honor"]
        state["current_thought"] = f"Diagnostic fallback: {str(e)}"
        state["current_action"] = "escalate" if is_hard_failure else "create_and_send_link"
        state["current_action_input"] = {
            "channel": "whatsapp",
            "retry_delay_hours": 0,
            "reason": f"Fallback: {str(e)}"
        }
        state["step_count"] = step
        log_audit(state["case_id"], "diagnose", "gateway_diagnosis", str(e), outcome="fallback")

    return state

def craft_message_node(state: AgentState) -> AgentState:
    """
    Sub-Agent 2: Personalized Customer Communication & Localization Specialist.
    Generates polite, brand-safe, high-converting copy adapted to channel constraints and customer context.
    """
    # Only craft message if action is create_and_send_link
    if state.get("current_action") != "create_and_send_link":
        return state

    case = state.get("case_data") or {}
    action_input = state.get("current_action_input") or {}
    channel = action_input.get("channel", "whatsapp")
    diagnosis = state.get("diagnosis") or {}
    customer_first_name = str(case.get("customer_name", "Customer")).split()[0]
    raw_amount = case.get("amount_rupees", 0)
    amount_str = f"{int(raw_amount)}" if float(raw_amount).is_integer() else f"{raw_amount:.2f}"
    step_num = state.get("step_count", 0) + 1

    system_prompt = """You are an expert Customer Retention & Payment Copywriter for Indian D2C & SaaS brands.

Your objective: Write high-converting, dynamic, witty, and brand-safe recovery messages inspired by top Indian apps (like Zomato, Swiggy, CRED, and Spotify).

### Strict Copy & Variety Rules:
- Dynamic Creativity: Be creative, fresh, and varied EVERY single time. DO NOT repeat the exact same sentence or template.
- Diverse Angles to Try:
  * Angle A (Light Humor): Witty bank network hiccup or tech glitch joke ("Your bank blinked for a second").
  * Angle B (FOMO / Service Value): Remind them what they're missing out on ("Your premium access is paused").
  * Angle C (Helpful Nudge): Quick 1-tap resolution hint.
  * Angle D (Friendly Reminder): Warm, polite D2C check-in.
- DO NOT say "Love, Razorpay" or sign off as Razorpay! Sign off as the brand service team or use no sign-off.
- Clean Currency: Always refer to amount as ₹""" + amount_str + """ (e.g. ₹499).
- Tone: Friendly, witty, non-embarrassing, and supportive. NEVER accusatory or legal.
- Channel Format:
  * "whatsapp": 2 to 3 short lines. Catchy opening, clean subscription context, clear call-to-action with literal "{payment_link}".
  * "sms": Under 160 characters. Crisp, witty, and includes literal "{payment_link}".
  * "email": Friendly subject line and warm 2-paragraph body including literal "{payment_link}".
- URL Rule: DO NOT invent fake URLs. ALWAYS include the literal placeholder "{payment_link}".

### Output Format (Strict JSON ONLY):
{
  "message_body": "Fresh witty copy text including literal {payment_link}",
  "tone": "witty_d2c",
  "language": "en"
}
"""

    human_prompt = f"""
Customer Name: {customer_first_name}
Amount Pending: ₹{amount_str}
Failure Context: {case.get('failure_code')} ({diagnosis.get('root_cause', 'authorization declined')})
Selected Channel: {channel}
Current Recovery Attempt: Step {step_num}

Generate a fresh, unique, high-converting customer recovery message for Step {step_num} using {{payment_link}} as the URL tag.
"""

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ])
        parsed = safe_json_parse(response.content)
        body = parsed.get("message_body", f"Hi {customer_first_name}, your payment of ₹{amount_str} could not be completed. Tap here to resume: {{payment_link}}")
        
        # Ensure {payment_link} is present in body
        if "{payment_link}" not in body:
            body = f"{body.rstrip()}\n\nPay securely: {{payment_link}}"

        state["message_payload"] = parsed
        if not state.get("current_action_input"):
            state["current_action_input"] = {}
        state["current_action_input"]["message_body"] = body

        log_audit(
            case_id=state["case_id"],
            stage="communication",
            action="craft_personalized_copy",
            details=json.dumps(parsed),
            outcome="success"
        )
    except Exception as e:
        fallback_msg = f"Hi {customer_first_name}, your subscription payment of ₹{amount_rupees} was unsuccessful. Please complete payment using this secure link: {{payment_link}}"
        if not state.get("current_action_input"):
            state["current_action_input"] = {}
        state["current_action_input"]["message_body"] = fallback_msg
        log_audit(state["case_id"], "communication", "craft_personalized_copy", str(e), outcome="fallback")

    return state

def act_node(state: AgentState) -> AgentState:
    """Execute the action decided by the LLM"""
    case_id = state["case_id"]
    action = state.get("current_action", "create_and_send_link")
    action_input = state.get("current_action_input") or {}
    case = state.get("case_data") or {}

    # Pre-action out-of-band reconciliation check
    reconciliation = check_gateway_reconciliation(case_id)
    if reconciliation.get("is_reconciled"):
        state["is_recovered"] = True
        state["final_status"] = "recovered"
        state["should_stop"] = True
        state["stop_reason"] = f"Pre-action reconciliation: settled via {reconciliation.get('source', 'external')}"
        state["current_observation"] = {
            "success": True,
            "action": "reconcile",
            "settled_externally": True,
            "details": reconciliation.get("details")
        }
        return state

    observation = {"success": False, "action": action}

    try:
        if action == "create_and_send_link":
            channel = action_input.get("channel", "whatsapp")
            message_body = action_input.get("message_body", "Please complete your pending payment.")

            link_res = create_payment_link(case_id) or {}
            payment_url = link_res.get("short_url") if link_res.get("success") else None

            msg_res = send_message(
                case_id=case_id,
                channel=channel,
                message=message_body,
                payment_link=payment_url
            ) or {}

            if msg_res.get("message") and state.get("current_action_input"):
                state["current_action_input"]["message_body"] = msg_res.get("message")

            # Simulate customer response
            payment_sim = simulate_customer_payment(case_id) or {}

            observation = {
                "success": True,
                "action": action,
                "payment_link": payment_url,
                "message_sent": msg_res.get("success", False),
                "customer_paid": payment_sim.get("paid", False),
                "recovered_amount": payment_sim.get("recovered_amount", 0) if payment_sim.get("paid") else 0
            }

            if payment_sim.get("paid"):
                state["is_recovered"] = True
                state["final_status"] = "recovered"
                state["should_stop"] = True
                state["stop_reason"] = "Customer paid successfully"

        elif action == "schedule_retry":
            delay = action_input.get("retry_delay_hours", 24)
            res = schedule_retry(case_id, delay_hours=delay)
            observation = {"success": True, "action": "schedule_retry", "delay_hours": delay, "details": res}

        elif action == "escalate":
            reason = action_input.get("reason", "Agent decided to escalate")
            res = escalate_case(case_id, reason)
            observation = {"success": True, "action": "escalate", "reason": reason}
            state["is_escalated"] = True
            state["should_stop"] = True
            state["stop_reason"] = "Escalated by agent"
            state["final_status"] = "escalated"

        elif action == "stop":
            observation = {"success": True, "action": "stop", "reason": action_input.get("reason", "Agent decided to stop")}
            state["should_stop"] = True
            state["stop_reason"] = action_input.get("reason", "Agent decided to stop")
            state["final_status"] = "stopped"

        else:
            observation = {"success": False, "error": f"Unknown action: {action}"}

    except Exception as e:
        observation = {"success": False, "error": str(e)}
        log_audit(case_id, "act", action, str(e), outcome="failed")

    state["current_observation"] = observation
    return state

def reflect_node(state: AgentState) -> AgentState:
    """LLM reflects on the observation and decides whether to continue"""
    case = state.get("case_data") or {}
    thought = state.get("current_thought", "")
    action = state.get("current_action", "")
    observation = state.get("current_observation", {})
    step = state.get("step_count", 1)

    # If already marked to stop (e.g. recovered or escalated), record and exit
    if state.get("should_stop"):
        reflection = f"Outcome achieved: {state.get('stop_reason')}"
        state["current_reflection"] = reflection

        # Save to history
        state["history"].append({
            "step": step,
            "thought": thought,
            "action": action,
            "action_input": state.get("current_action_input"),
            "observation": observation,
            "reflection": reflection
        })
        return state

    system_prompt = """You are reflecting on the result of the last recovery action.

Rules for deciding whether to continue:
1. If customer has NOT paid yet, but current step < max steps, and the failure is a soft decline (e.g. bank timeout, insufficient balance), you SHOULD continue so the agent can pivot to another channel (e.g. SMS/Email).
2. Only set should_continue = false if the case is permanently unrecoverable, already paid, or all reasonable channels have been exhausted.

Output JSON ONLY:
{
  "reflection": "Honest assessment of customer response and what channel should be tried next",
  "should_continue": true | false,
  "reason": "Rationale for continuing to next channel or stopping"
}
"""

    human_prompt = f"""
Case: {case.get('customer_name', 'Customer')} | ₹{case.get('amount_rupees', 0)} | Failure: {case.get('failure_code', 'unknown')}
Last Action Taken: {action} on {(state.get('current_action_input') or {}).get('channel', 'unknown')}
Observation: {json.dumps(observation or {}, indent=2)}
Current Step: {step} of maximum {state.get('max_steps', 5)}

Evaluate the outcome and decide whether to continue to the next recovery step.
"""

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ])
        parsed = safe_json_parse(response.content)

        reflection = parsed.get("reflection", "Evaluated observation")
        should_continue = parsed.get("should_continue", True)

        state["current_reflection"] = reflection

        if not should_continue:
            state["should_stop"] = True
            state["stop_reason"] = parsed.get("reason", "Agent decided to stop after reflection")
            if not state.get("final_status"):
                state["final_status"] = "stopped_after_reflection"

        log_audit(
            case_id=state["case_id"],
            stage="reflect",
            action="llm_reflection",
            details=json.dumps(parsed),
            llm_reasoning=reflection,
            outcome="success"
        )
    except Exception as e:
        state["current_reflection"] = f"Reflection evaluated: continuing recovery. ({str(e)})"
        log_audit(state["case_id"], "reflect", "llm_reflection", str(e), outcome="fallback")

    # Always save the full step into history
    state["history"].append({
        "step": step,
        "thought": thought,
        "action": action,
        "action_input": state.get("current_action_input"),
        "observation": observation,
        "reflection": state.get("current_reflection")
    })

    return state

def check_stop_node(state: AgentState) -> AgentState:
    """Hard stopping rules + max steps"""
    if state.get("should_stop"):
        return state

    # Max steps
    if state.get("step_count", 0) >= state.get("max_steps", 5):
        state["should_stop"] = True
        state["stop_reason"] = f"Reached max steps ({state.get('max_steps')})"
        if not state.get("final_status"):
            state["final_status"] = "max_steps_reached"
        return state

    # Existing hard rules from tools
    stop_check = check_stopping_rules(state["case_id"])
    if stop_check["should_stop"]:
        state["should_stop"] = True
        state["stop_reason"] = stop_check["reason"]
        escalate_case(state["case_id"], stop_check["reason"])
        state["is_escalated"] = True
        state["final_status"] = "escalated"

    return state
