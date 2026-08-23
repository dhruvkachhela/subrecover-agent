"""
SubRecover Agent - Enterprise Recovery Dashboard
Production-grade operational console for subscription failure diagnostics,
multi-step cognitive recovery execution, system architecture visualization, and immutable audit inspection.
"""

import sys
from pathlib import Path

# Add project root directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json
from datetime import datetime
from app.database import SessionLocal
from app.models import FailedSubscription, AuditLog
from agent.graph import recovery_graph
from agent.state import AgentState
from agent.tools import verify_live_payment_link, check_gateway_reconciliation, update_case, log_audit

# Page configuration
st.set_page_config(
    page_title="SubRecover Agent | Razorpay",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Minimal, clean fintech typography and component styling
st.markdown("""
<style>
    /* Clean layout and typography */
    .block-container {
        padding-top: 1.8rem;
        padding-bottom: 3rem;
        max-width: 1280px;
    }
    
    h1, h2, h3, h4 {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-weight: 600;
        letter-spacing: -0.02em;
    }
    
    /* Clean Tab Navigation */
    .stTabs [data-baseweb="tab-list"] {
        gap: 18px;
        margin-bottom: 24px;
    }
    
    .stTabs [data-baseweb="tab"] {
        padding: 10px 6px;
        font-size: 14px;
        font-weight: 500;
        border-bottom-width: 2px;
    }
    
    .stTabs [aria-selected="true"] {
        color: #0284C7 !important;
        border-bottom-color: #0284C7 !important;
        font-weight: 600;
    }

    /* Metric card refinements */
    div[data-testid="stMetric"] {
        border-radius: 8px;
        padding: 14px 18px;
    }
    
    div[data-testid="stMetricLabel"] {
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }

    div[data-testid="stMetricValue"] {
        font-size: 24px;
        font-weight: 700;
    }

    /* Step card styling */
    .step-card {
        border: 1px solid rgba(148, 163, 184, 0.2);
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 14px;
    }
    
    .step-badge {
        display: inline-block;
        font-size: 11px;
        font-weight: 600;
        font-family: monospace;
        padding: 3px 8px;
        border-radius: 4px;
        background: #0284C7;
        color: #FFFFFF;
        margin-bottom: 8px;
    }

    .meta-label {
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        margin-bottom: 2px;
        opacity: 0.75;
    }
</style>
""", unsafe_allow_html=True)

def render_mermaid(code: str, height: int = 580):
    """Render clean, high-contrast Mermaid.js diagrams directly inside Streamlit with visibility detection and zero clipping."""
    cleaned_code = code.strip()
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
        <style>
            body {{
                margin: 0;
                padding: 16px 24px;
                background: #111827;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                display: flex;
                justify-content: center;
                box-sizing: border-box;
            }}
            #diagram-target {{
                width: 100%;
                display: flex;
                justify-content: center;
                overflow: visible !important;
            }}
            #diagram-target svg {{
                width: 100% !important;
                max-width: 920px !important;
                height: auto !important;
                overflow: visible !important;
            }}
        </style>
    </head>
    <body>
        <div id="diagram-target">
            <span style="color: #94A3B8; font-size: 13px;">Loading architecture diagram...</span>
        </div>
        <script type="text/plain" id="diagram-source">
{cleaned_code}
        </script>
        <script>
            let rendered = false;
            async function triggerRender() {{
                if (rendered) return;
                const target = document.getElementById('diagram-target');
                const source = document.getElementById('diagram-source');
                if (!target || !source) return;
                
                const width = target.getBoundingClientRect().width;
                if (width < 30) return; // Wait until container is visible and has width
                
                try {{
                    mermaid.initialize({{
                        startOnLoad: false,
                        theme: 'dark',
                        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
                        themeVariables: {{
                            darkMode: true,
                            background: '#111827',
                            primaryColor: '#1E293B',
                            primaryTextColor: '#F8FAFC',
                            primaryBorderColor: '#38BDF8',
                            lineColor: '#38BDF8',
                            secondaryColor: '#0F172A',
                            secondaryTextColor: '#F8FAFC',
                            secondaryBorderColor: '#38BDF8',
                            tertiaryColor: '#111827',
                            tertiaryTextColor: '#F8FAFC',
                            tertiaryBorderColor: '#64748B',
                            edgeLabelBackground: '#1E293B',
                            fontSize: '13px'
                        }}
                    }});
                    const sourceText = source.textContent.trim();
                    const id = 'svg_' + Math.random().toString(36).substr(2, 9);
                    const {{ svg }} = await mermaid.render(id, sourceText);
                    target.innerHTML = svg;
                    rendered = true;
                }} catch (err) {{
                    target.innerHTML = '<div style="color: #F87171; font-size: 12px; padding: 12px; border: 1px solid #7F1D1D; border-radius: 6px; background: #450A0A;">Diagram Notice: ' + err.message + '</div>';
                }}
            }}

            window.addEventListener('load', () => {{
                triggerRender();
                // If in hidden tab initially, observe when tab becomes visible
                const observer = new IntersectionObserver((entries) => {{
                    entries.forEach(entry => {{
                        if (entry.isIntersecting && !rendered) {{
                            triggerRender();
                        }}
                    }});
                }}, {{ threshold: 0.1 }});
                
                const target = document.getElementById('diagram-target');
                if (target) observer.observe(target);
                
                // Backup interval for dynamic tab switches
                const interval = setInterval(() => {{
                    if (!rendered) {{
                        triggerRender();
                    }} else {{
                        clearInterval(interval);
                    }}
                }}, 300);
            }});
        </script>
    </body>
    </html>
    """
    components.html(html_code, height=height, scrolling=True)


# App Title & Subtitle
col_title, col_status = st.columns([3, 1])
with col_title:
    st.title("SubRecover Agent")
    st.caption("Autonomous Subscription & Mandate Revenue Recovery Engine")

with col_status:
    st.markdown("<div style='text-align: right; padding-top: 14px;'><span style='font-size: 12px; color: #059669; font-weight: 600;'>● System Active (Razorpay Test Mode)</span></div>", unsafe_allow_html=True)

# ====================== DATA LAYER ======================

@st.cache_data(ttl=5)
def fetch_system_metrics():
    db = SessionLocal()
    try:
        query = """
            SELECT 
                case_id, customer_name, customer_phone, customer_email,
                subscription_id, amount/100.0 AS amount_inr,
                failure_code, failure_description, payment_method, previous_attempts,
                status, recovered_amount/100.0 AS recovered_inr, recovery_attempts,
                last_recovery_action, escalated, notes, failed_at, updated_at
            FROM failed_subscriptions
        """
        df = pd.read_sql(query, db.bind)
        
        total_cases = len(df)
        total_risk = df["amount_inr"].sum() if total_cases > 0 else 0.0
        
        recovered_df = df[df["status"] == "recovered"]
        escalated_df = df[df["status"] == "escalated"]
        open_df = df[df["status"] == "failed_recoverable"]
        
        total_recovered = recovered_df["recovered_inr"].sum() if len(recovered_df) > 0 else 0.0
        recovery_rate = (len(recovered_df) / total_cases * 100.0) if total_cases > 0 else 0.0
        
        metrics = {
            "total_cases": total_cases,
            "total_risk": total_risk,
            "recovered_cases": len(recovered_df),
            "total_recovered": total_recovered,
            "recovery_rate": recovery_rate,
            "escalated_cases": len(escalated_df),
            "open_cases": len(open_df)
        }
        return metrics, df
    finally:
        db.close()

def fetch_audit_trail(limit=300):
    db = SessionLocal()
    try:
        logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()
        rows = []
        for log in logs:
            rows.append({
                "Timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S") if log.timestamp else "",
                "Case ID": log.case_id,
                "Stage": log.stage,
                "Action": log.action,
                "Outcome": log.outcome,
                "Reasoning": log.llm_reasoning or "",
                "Details": log.details or ""
            })
        return pd.DataFrame(rows)
    finally:
        db.close()

metrics, cases_df = fetch_system_metrics()

# ====================== TOP KPI STRIP ======================
kpi1, kpi2, kpi3, kpi4 = st.columns(4)

with kpi1:
    st.metric(
        label="Revenue at Risk",
        value=f"₹{metrics['total_risk']:,.2f}"
    )

with kpi2:
    st.metric(
        label="Recovered Revenue",
        value=f"₹{metrics['total_recovered']:,.2f}",
        delta=f"{metrics['recovery_rate']:.1f}% rate"
    )

with kpi3:
    st.metric(
        label="Open Cases",
        value=f"{metrics['open_cases']} / {metrics['total_cases']}"
    )

with kpi4:
    st.metric(
        label="Escalated to Human",
        value=f"{metrics['escalated_cases']}"
    )

st.write("")

# ====================== WORKSPACE TABS ======================
tab_overview, tab_runner, tab_arch, tab_cases, tab_audit = st.tabs([
    "Overview & Portfolio",
    "Agentic Case Runner",
    "System Architecture",
    "Cases Explorer",
    "Audit Log"
])

# ----------------- TAB 1: OVERVIEW & PORTFOLIO -----------------
with tab_overview:
    col_chart_1, col_chart_2 = st.columns(2)
    
    with col_chart_1:
        st.markdown("#### Case Status Distribution")
        if not cases_df.empty:
            status_summary = cases_df["status"].value_counts()
            st.bar_chart(status_summary, height=240)

    with col_chart_2:
        st.markdown("#### Failure Code Breakdown")
        if not cases_df.empty:
            failure_summary = cases_df["failure_code"].value_counts()
            st.bar_chart(failure_summary, height=240)

    st.write("")
    st.markdown("#### Recovery Performance by Failure Type")
    
    if not cases_df.empty:
        summary_rows = []
        for code, group in cases_df.groupby("failure_code"):
            count = len(group)
            rec = len(group[group["status"] == "recovered"])
            esc = len(group[group["status"] == "escalated"])
            rate = (rec / count * 100) if count > 0 else 0
            risk = group["amount_inr"].sum()
            recovered = group["recovered_inr"].sum()
            
            summary_rows.append({
                "Failure Code": code,
                "Total Cases": count,
                "Recovered": rec,
                "Escalated": esc,
                "Recovery Rate (%)": round(rate, 1),
                "At Risk (INR)": round(risk, 2),
                "Recovered (INR)": round(recovered, 2)
            })
            
        summary_table_df = pd.DataFrame(summary_rows).sort_values(by="Recovery Rate (%)", ascending=False)
        st.dataframe(summary_table_df, use_container_width=True, hide_index=True)

    st.write("")
    st.markdown("#### Enterprise Unit Economics & Financial ROI")
    st.caption("Demonstrating measured net revenue recovery after deducting AI inference and messaging compute costs.")
    
    # Calculate Unit Economics
    recovered_inr = metrics['total_recovered']
    recovered_cases = metrics['recovered_cases']
    total_processed = metrics['total_cases'] - metrics['open_cases']
    
    # Costs
    llm_tokens_cost = max(1, total_processed) * 1.3 * 0.03  # avg 1.3 steps * Rs 0.03 / step
    messaging_cost = max(1, total_processed) * 1.1 * 0.40   # avg 1.1 messages * Rs 0.40 / msg
    total_cost = llm_tokens_cost + messaging_cost
    net_recovered = max(0.0, recovered_inr - total_cost)
    roi_multiplier = (recovered_inr / total_cost) if total_cost > 0 else 0.0

    with st.container(border=True):
        roi_c1, roi_c2, roi_c3, roi_c4 = st.columns(4)
        with roi_c1:
            st.metric(label="Gross Recovered", value=f"₹{recovered_inr:,.2f}")
        with roi_c2:
            st.metric(label="Total AI & SMS Cost", value=f"₹{total_cost:,.2f}")
        with roi_c3:
            st.metric(label="Net Recovered Revenue", value=f"₹{net_recovered:,.2f}", delta=f"{((net_recovered/recovered_inr)*100 if recovered_inr>0 else 0):.1f}% margin")
        with roi_c4:
            st.metric(label="Financial ROI Multiplier", value=f"{roi_multiplier:,.0f}x ROI")

# ----------------- TAB 2: AGENTIC CASE RUNNER -----------------
with tab_runner:
    st.markdown("#### Single Case Agentic Execution & Live Verification")
    st.caption("Triggers the Multi-Agent Cognitive Graph (Diagnosis → Personalized Copywriting → Action → Reflection).")
    
    run_col_select, run_col_btn = st.columns([3, 1])
    with run_col_select:
        case_options = cases_df["case_id"].tolist() if not cases_df.empty else []
        selected_case_id = st.selectbox("Select Case for Execution", case_options)
    
    if selected_case_id:
        case_row = cases_df[cases_df["case_id"] == selected_case_id].iloc[0]
        
        # Case Details Snapshot Card
        with st.container(border=True):
            snap_c1, snap_c2, snap_c3, snap_c4 = st.columns(4)
            snap_c1.markdown(f"<div class='meta-label'>Customer</div><b>{case_row['customer_name']}</b>", unsafe_allow_html=True)
            snap_c2.markdown(f"<div class='meta-label'>Amount</div><b>₹{case_row['amount_inr']:,.2f}</b>", unsafe_allow_html=True)
            snap_c3.markdown(f"<div class='meta-label'>Payment Method</div><b>{str(case_row['payment_method']).upper()}</b>", unsafe_allow_html=True)
            snap_c4.markdown(f"<div class='meta-label'>Current Status</div><b><code>{case_row['status']}</code></b>", unsafe_allow_html=True)
            
            st.divider()
            
            snap_c5, snap_c6 = st.columns([1, 2])
            snap_c5.markdown(f"<div class='meta-label'>Failure Code</div><b><code>{case_row['failure_code']}</code></b>", unsafe_allow_html=True)
            snap_c6.markdown(f"<div class='meta-label'>Failure Description</div>{case_row['failure_description']}", unsafe_allow_html=True)

        st.write("")
        st.markdown("##### Recovery Actions & Out-of-Band Reconciliation")
        st.caption("Test autonomous multi-agent dunning, or simulate out-of-band payments to verify edge-case reconciliation.")
        
        col_run_action, col_ext_sim, col_rec_check = st.columns([2, 2, 2])
        
        with col_run_action:
            trigger_run = st.button("▶ Run Multi-Agent Recovery", type="primary", use_container_width=True, help="Executes the Multi-Agent Cognitive Graph.")
        with col_ext_sim:
            trigger_simulate_ext = st.button("💳 Simulate External Payment", use_container_width=True, help="Simulates customer paying directly on merchant app/UPI outside the agent to test edge-case reconciliation.")
        with col_rec_check:
            trigger_reconcile = st.button("🔄 Sync Gateway Reconciliation", use_container_width=True, help="Queries gateway & ledger to check if customer settled subscription via external channel.")

        # Simulate External Settlement Action
        if trigger_simulate_ext:
            from agent.tools import record_external_settlement
            ext_res = record_external_settlement(selected_case_id, channel="direct_upi")
            if ext_res.get("success"):
                st.success(f"**✓ External Payment Recorded!**\n\n• **Payment Ref:** `{ext_res.get('payment_id')}`\n• **Channel:** `Direct UPI / Merchant App`\n• **Amount:** ₹{ext_res.get('recovered_amount', 0)/100:,.2f}\n\n*The case is now reconciled in the ledger. If you click **▶ Run Multi-Agent Recovery**, the agent will detect this at Step 0 and halt without sending duplicate customer nudges.*")
            else:
                st.error(f"Failed to record external payment: {ext_res.get('error')}")

        # Check Gateway Reconciliation Action
        if trigger_reconcile:
            rec_res = check_gateway_reconciliation(selected_case_id)
            if rec_res.get("is_reconciled"):
                with st.container(border=True):
                    st.markdown("##### 🟢 Gateway Reconciliation Result: RECONCILED")
                    st.markdown(f"• **Source:** `{rec_res.get('source', 'external')}`")
                    st.markdown(f"• **Amount Reconciled:** ₹{rec_res.get('recovered_amount', 0)/100:,.2f}")
                    st.markdown(f"• **Details:** {rec_res.get('details')}")
                    st.markdown("*Status automatically synchronized to `recovered` in database.*")
            else:
                with st.container(border=True):
                    st.markdown("##### 🟡 Gateway Reconciliation Result: NOT RECONCILED")
                    st.markdown("• **Status:** Case remains open for automated agent recovery.")
                    st.markdown("• **Details:** No external or out-of-band settlement detected across merchant app or direct UPI records.")

        # Reset button if case is already closed/recovered/escalated
        if case_row['status'] in ['recovered', 'escalated', 'closed']:
            st.write("")
            if st.button("↺ Reset This Case to Open (Test Recovery Again)", use_container_width=False):
                update_case(selected_case_id, status="failed_recoverable", recovered_amount=0, recovery_attempts=0, notes=None)
                st.rerun()

        if trigger_run:
            with st.spinner("Executing Multi-Agent Cognitive Graph (Diagnosis → Copywriting → Action)..."):
                initial_state: AgentState = {
                    "case_id": selected_case_id,
                    "case_data": None,
                    "history": [],
                    "current_thought": None,
                    "current_action": None,
                    "current_action_input": None,
                    "current_observation": None,
                    "current_reflection": None,
                    "diagnosis": None,
                    "message_payload": None,
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
                    
                    # Execution Summary Banner
                    res_status = final_state.get("final_status", "completed")
                    is_rec = final_state.get("is_recovered", False)
                    is_esc = final_state.get("is_escalated", False)
                    total_steps = final_state.get("step_count", 0)
                    stop_reason = final_state.get("stop_reason", "Workflow complete")
                    
                    if is_rec:
                        st.success(f"**Outcome: RECOVERED** (in {total_steps} step{'s' if total_steps != 1 else ''}) — {stop_reason}")
                    elif is_esc:
                        st.warning(f"**Outcome: ESCALATED TO HUMAN** (in {total_steps} step{'s' if total_steps != 1 else ''}) — {stop_reason}")
                    else:
                        st.info(f"**Outcome: {res_status.upper()}** — {stop_reason}")
                    
                    st.write("")
                    st.markdown("##### Multi-Step Agentic Reasoning Trace")
                    
                    history = final_state.get("history", [])
                    if not history:
                        st.info("No intermediate steps recorded.")
                    else:
                        for step_item in history:
                            step_no = step_item.get("step", 1)
                            action_name = step_item.get("action", "unknown")
                            thought = step_item.get("thought", "")
                            action_input = step_item.get("action_input") or {}
                            obs = step_item.get("observation") or {}
                            reflection = step_item.get("reflection", "")
                            
                            with st.container(border=True):
                                st.markdown(f"<span class='step-badge'>STEP {step_no} &bull; ACTION: {action_name.upper()}</span>", unsafe_allow_html=True)
                                
                                st.markdown(f"**Thought (Diagnostic Analysis):** {thought}")
                                
                                if action_input:
                                    channel = action_input.get("channel")
                                    msg = action_input.get("message_body")
                                    delay = action_input.get("retry_delay_hours")
                                    
                                    col_act1, col_act2 = st.columns([1, 3])
                                    if channel:
                                        col_act1.write(f"**Channel:** `{channel}`")
                                    if delay:
                                        col_act1.write(f"**Delay:** `{delay}h`")
                                    if msg:
                                        col_act2.write(f"**Personalized Message:** _{msg}_")
                                
                                if obs.get("payment_link"):
                                    link = obs.get("payment_link")
                                    st.markdown(f"**Live Razorpay Payment Link:** [{link}]({link})")
                                    
                                    # Live REST API Verifier Button
                                    link_id = link.split("/")[-1]
                                    if st.button(f"🔍 Verify Payment on Razorpay REST API ({link_id})", key=f"verify_{link_id}_{step_no}"):
                                        with st.spinner("Querying Razorpay REST API..."):
                                            verify_res = verify_live_payment_link(link_id)
                                            if verify_res.get("is_paid"):
                                                st.success(f"✓ Payment Verified on Razorpay API! Status: PAID (Amount: ₹{verify_res.get('amount_paid',0)/100:.2f})")
                                                update_case(selected_case_id, status="recovered", recovered_amount=verify_res.get('amount_paid',0))
                                            else:
                                                st.info(f"Razorpay API Status: {verify_res.get('status', 'unpaid')}. Customer has not completed checkout yet.")
                                
                                if obs:
                                    paid_status = obs.get("customer_paid")
                                    sent_status = obs.get("message_sent")
                                    st.markdown(f"**Observation:** Delivery = `{sent_status}` | Customer Paid = `{paid_status}`")
                                    
                                if reflection:
                                    st.markdown(f"**Reflection:** {reflection}")

                except Exception as err:
                    st.error(f"Execution failed with error: {str(err)}")

# ----------------- TAB 3: SYSTEM ARCHITECTURE -----------------
with tab_arch:
    st.markdown("#### System Architecture & Cognitive Runtime Specification")
    st.caption("Clean architectural topography, state machine transitions, and selective hybrid agency model.")

    # 3-Tier Overview Cards
    col_t1, col_t2, col_t3 = st.columns(3)
    with col_t1:
        with st.container(border=True):
            st.markdown("<div class='meta-label'>Layer 1: Presentation & Events</div>", unsafe_allow_html=True)
            st.markdown("##### Operations & Webhooks")
            st.markdown("""
            - Streamlit Executive Dashboard & Case Runner
            - FastAPI Real-Time Webhook Consumer (`/webhook/razorpay`)
            - Event-Driven Trigger for `subscription.charged_failed`
            - Live Razorpay REST API Link Verifier
            """)
    
    with col_t2:
        with st.container(border=True):
            st.markdown("<div class='meta-label'>Layer 2: Multi-Agent Cognition</div>", unsafe_allow_html=True)
            st.markdown("##### LangGraph + NVIDIA NIM")
            st.markdown("""
            - **Sub-Agent 1 (Diagnostic)**: Root-Cause & Routing
            - **Sub-Agent 2 (Copywriter)**: Personalized Localization
            - Out-of-Band Gateway Reconciliation Engine
            - Bounded Circuit Breakers & Invariants ($N \le 5$)
            """)
            
    with col_t3:
        with st.container(border=True):
            st.markdown("<div class='meta-label'>Layer 3: Execution & Ledger</div>", unsafe_allow_html=True)
            st.markdown("##### Deterministic Tools & Storage")
            st.markdown("""
            - Razorpay API Client (`rzp.io` Live Checkout)
            - Omnichannel Dispatch (WhatsApp / SMS / Email)
            - Out-of-Band Payment Settlement Sync
            - Immutable Regulatory Audit Trail (SQLite)
            """)

    st.write("")
    
    # Diagram 1: Top-Level System Architecture
    st.markdown("##### 1. End-to-End System Topography")
    sys_arch_mermaid = """
flowchart TB
    subgraph L1 [Layer 1: Ingestion & Operations]
        DASH[Streamlit Executive Dashboard]
        RUNNER[Case Agentic Runner]
        WEBHOOK[FastAPI Webhook Server]
    end

    subgraph L2 [Layer 2: Multi-Agent Cognitive Engine]
        LOAD[load_case: Reconciliation Check]
        DIAG[Sub-Agent 1: diagnose_node]
        CRAFT[Sub-Agent 2: craft_message_node]
        ACT[act_node: Tool Execution]
        REFLECT[reflect_node: Observe & Reflect]
        CHECK[check_stop_node: Circuit Breaker]
    end

    subgraph L3 [Layer 3: Deterministic Tools & Ledger]
        RZP[Razorpay REST API: rzp.io links]
        MSG[Omnichannel Dispatch: WhatsApp / SMS]
        RECON[Out-of-Band Settlement Sync]
        DB[(SQLite Database)]
        LOGS[(Immutable Regulatory Audit Trail)]
    end

    WEBHOOK --> LOAD
    RUNNER --> LOAD
    LOAD -->|Unpaid| DIAG
    LOAD -->|Settled Externally| RECON
    
    DIAG -->|Send Link| CRAFT
    DIAG -->|Escalate / Stop| ACT
    CRAFT --> ACT
    
    ACT --> REFLECT
    REFLECT --> CHECK
    CHECK -->|Continue Step under 5| DIAG
    CHECK -->|Terminal State| ENDNODE[Case Closed / Recovered / Escalated]

    ACT --> RZP
    ACT --> MSG
    ACT --> RECON
    LOAD --> DB
    ACT --> DB
    ACT --> LOGS
    DIAG --> LOGS
    CRAFT --> LOGS
    REFLECT --> LOGS
    """
    render_mermaid(sys_arch_mermaid, height=640)

    st.write("")
    
    # Diagram 2 & 3 side by side
    arch_col_left, arch_col_right = st.columns(2)
    
    with arch_col_left:
        st.markdown("##### 2. Multi-Agent Cognitive Graph")
        st.caption("Specialized separation of financial diagnosis, personalized copywriting, and bounded reflection.")
        react_mermaid = """
flowchart TD
    A[1. Ingestion: load_case] --> RECC{Reconciled Out-of-Band?}
    RECC -->|Yes| REC[🏁 Recovered Out-of-Band]
    RECC -->|No| B[2. Sub-Agent 1: diagnose_node]
    
    B -->|🔴 Hard Failure: escalate| D_ESC[4a. Execute: Escalate Ticket]
    D_ESC --> ESC[🛑 Outcome: Escalated to Ops]
    
    B -->|🟡 Transient Outage: retry| D_RETRY[4b. Execute: Schedule 24h Retry]
    D_RETRY --> RETRY[⏳ Outcome: Scheduled Retry]
    
    B -->|🟢 Soft Failure: send_link| C[3. Sub-Agent 2: craft_message_node]
    C --> D_LINK[4c. Execute: Dispatch Live Razorpay Link]
    
    D_LINK --> E[5. Observe & Reflect: reflect_node]
    E --> F{6. Safety Guard: check_stop}
    
    F -->|Customer Paid| REC
    F -->|Unpaid & Step under 5| B
    F -->|Max Steps 5 Exceeded| ESC
        """
        render_mermaid(react_mermaid, height=580)

    with arch_col_right:
        st.markdown("##### 3. Finite State Safety Machine")
        st.caption("Hard rules ensuring fast escalation for non-recoverable failures and zero duplicate billing.")
        state_mermaid = """
flowchart TD
    START[Payment Failed Event] --> RECON_CHK{Out-of-Band Paid?}
    
    RECON_CHK -->|Yes| REC_EXT[Immediate Close: Reconciled]
    RECON_CHK -->|No| CLASSIFY{Classify Failure Type}
    
    CLASSIFY -->|Hard: mandate_revoked / invalid_account / card_expired| ESC_INST[Instant Escalation: Step 1]
    CLASSIFY -->|Soft: bank_timeout / insufficient_funds / soft_decline| S1[Step 1: WhatsApp Payment Link]
    
    S1 --> CHK1{Customer Paid?}
    CHK1 -->|Yes| REC_EXT
    CHK1 -->|No: Channel Pivot| S2[Step 2: SMS Payment Link]
    
    S2 --> CHK2{Customer Paid?}
    CHK2 -->|Yes| REC_EXT
    CHK2 -->|No: Alternate Channel| S3[Step 3: Email or Delayed Retry]
    
    S3 --> CHK3{Max Steps Reached?}
    CHK3 -->|Limit Exceeded| ESC_INST
    CHK3 -->|Under Limit| S2
    
    ESC_INST --> ESC_FINAL[Escalated to Human Operations]
        """
        render_mermaid(state_mermaid, height=580)

    st.write("")
    
    # Selective Hybrid Agency Matrix
    st.markdown("##### 4. Selective Hybrid Agency Responsibility Matrix")
    matrix_data = [
        {"Subsystem / Node": "load_case_node", "Agency Type": "Deterministic", "Safety Guardrail": "Direct SQL & Out-of-Band Sync", "Design Rationale": "Prevents hallucinated customer data and stops duplicate billing if already settled."},
        {"Subsystem / Node": "diagnose_node", "Agency Type": "Agentic (LLM)", "Safety Guardrail": "100% Step-1 Hard Decline Rule", "Design Rationale": "Evaluates failure root cause, bank downtime heuristics, and optimal channel selection."},
        {"Subsystem / Node": "craft_message_node", "Agency Type": "Agentic (LLM)", "Safety Guardrail": "Brand Safety & Length Limits", "Design Rationale": "Tailors empathetic, non-accusatory copy in English/Hinglish adapted to channel."},
        {"Subsystem / Node": "act_node", "Agency Type": "Deterministic Tool", "Safety Guardrail": "Pre-Action Reconciliation Check", "Design Rationale": "Restricts financial actions to bounded, auditable tools with exact invoice amounts."},
        {"Subsystem / Node": "reflect_node", "Agency Type": "Agentic (LLM)", "Safety Guardrail": "Bounded History Schema", "Design Rationale": "Evaluates tool observations and customer responses to rotate channels dynamically."},
        {"Subsystem / Node": "check_stop_node", "Agency Type": "Hard Deterministic Guard", "Safety Guardrail": "max_steps <= 5 Assertion", "Design Rationale": "Code assertion guarantees halting; mathematically prevents infinite loops."},
        {"Subsystem / Node": "Audit Engine", "Agency Type": "Deterministic", "Safety Guardrail": "SQLite Transaction Commit", "Design Rationale": "Enforces complete regulatory traceability for every step rationale and outcome."}
    ]
    st.dataframe(pd.DataFrame(matrix_data), use_container_width=True, hide_index=True)

# ----------------- TAB 4: CASES EXPLORER -----------------
with tab_cases:
    st.markdown("#### Portfolio Case Directory")
    
    col_filter_st, col_filter_code, col_search = st.columns([1, 1, 2])
    with col_filter_st:
        status_opts = ["All"] + list(cases_df["status"].unique()) if not cases_df.empty else ["All"]
        selected_status_filter = st.selectbox("Status", status_opts)
    with col_filter_code:
        code_opts = ["All"] + list(cases_df["failure_code"].unique()) if not cases_df.empty else ["All"]
        selected_code_filter = st.selectbox("Failure Code", code_opts)
    with col_search:
        search_query = st.text_input("Search Customer Name or Case ID", "")

    filtered = cases_df.copy()
    if selected_status_filter != "All":
        filtered = filtered[filtered["status"] == selected_status_filter]
    if selected_code_filter != "All":
        filtered = filtered[filtered["failure_code"] == selected_code_filter]
    if search_query:
        filtered = filtered[
            filtered["customer_name"].str.contains(search_query, case=False, na=False) |
            filtered["case_id"].str.contains(search_query, case=False, na=False)
        ]

    display_cols = [
        "case_id", "customer_name", "amount_inr", "failure_code",
        "payment_method", "status", "recovery_attempts", "recovered_inr", "last_recovery_action"
    ]
    
    st.dataframe(
        filtered[display_cols],
        use_container_width=True,
        hide_index=True
    )
    
    st.download_button(
        label="Download Cases (CSV)",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="recovery_cases_export.csv",
        mime="text/csv"
    )

# ----------------- TAB 5: AUDIT LOG -----------------
with tab_audit:
    st.markdown("#### Immutable Regulatory Audit Trail")
    st.caption("Complete event log tracking every reasoning rationale, tool dispatch, and outcome.")
    
    audit_df = fetch_audit_trail()
    
    if not audit_df.empty:
        col_aud_stage, col_aud_search = st.columns([1, 2])
        with col_aud_stage:
            stage_list = ["All"] + list(audit_df["Stage"].unique())
            sel_stage = st.selectbox("Stage Filter", stage_list)
        with col_aud_search:
            aud_search = st.text_input("Filter by Case ID", "")
            
        aud_filtered = audit_df.copy()
        if sel_stage != "All":
            aud_filtered = aud_filtered[aud_filtered["Stage"] == sel_stage]
        if aud_search:
            aud_filtered = aud_filtered[aud_filtered["Case ID"].str.contains(aud_search, case=False, na=False)]
            
        st.dataframe(aud_filtered, use_container_width=True, hide_index=True)
        
        st.download_button(
            label="Download Audit Logs (CSV)",
            data=aud_filtered.to_csv(index=False).encode("utf-8"),
            file_name="subrecover_audit_logs.csv",
            mime="text/csv"
        )
    else:
        st.info("No audit logs recorded.")
