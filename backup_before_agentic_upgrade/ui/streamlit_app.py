# How this works:
# Internal enterprise dashboard for the SubRecover Agent.
# 1. Imports project path and database models to load transaction records.
# 2. Renders high-level KPI cards for risk, recovered capital, and case volume.
# 3. Organizes four core operational workflows: Overview, Run Agent, Cases, and Audit Log.
# 4. Connects directly to SQLite and the compiled LangGraph recovery graph.

import sys
from pathlib import Path

# Add project root directory to sys.path so 'app' and 'agent' modules can be resolved
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import pandas as pd
from datetime import datetime
from app.database import SessionLocal
from app.models import FailedSubscription, AuditLog
from agent.graph import recovery_graph
from agent.state import AgentState

# Page configuration
st.set_page_config(
    page_title="Subscription Recovery Engine",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Global layout styling
st.markdown("""
<style>
    .reportview-container {
        background-color: #fbfcfd;
    }
    h1, h2, h3 {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        color: #0f172a;
        font-weight: 600;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
        border-bottom: 1px solid #e2e8f0;
        margin-bottom: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        padding-top: 10px;
        padding-bottom: 10px;
        font-size: 14px;
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.title("Subscription Recovery Engine")
st.caption("Autonomous payment failure diagnostics, adaptive messaging, and retry orchestration.")
st.write("")

# ====================== DATA ACCESS ======================

def load_case_metrics():
    """
    Query database and compute core financial and operational recovery metrics.
    
    Returns:
        tuple[dict, pd.DataFrame]: Metric dictionary and normalized cases dataframe.
    """
    db = SessionLocal()
    try:
        query = """
            SELECT 
                case_id, merchant_id, customer_id, customer_name, customer_phone, customer_email,
                subscription_id, amount/100.0 AS amount_inr, currency, failed_at,
                failure_code, failure_description, payment_method, previous_attempts,
                status, recovered_amount/100.0 AS recovered_inr, recovery_attempts,
                last_recovery_action, escalated, notes, updated_at
            FROM failed_subscriptions
        """
        dataframe = pd.read_sql(query, db.bind)
        
        total_volume = len(dataframe)
        revenue_at_risk = dataframe["amount_inr"].sum() if total_volume > 0 else 0.0
        
        recovered_df = dataframe[dataframe["status"] == "recovered"]
        escalated_df = dataframe[dataframe["status"] == "escalated"]
        open_df = dataframe[dataframe["status"] == "failed_recoverable"]
        
        recovered_amount = recovered_df["recovered_inr"].sum() if len(recovered_df) > 0 else 0.0
        recovery_rate = (len(recovered_df) / total_volume * 100.0) if total_volume > 0 else 0.0
        
        metrics = {
            "total_cases": total_volume,
            "revenue_at_risk": revenue_at_risk,
            "recovered_cases": len(recovered_df),
            "recovered_amount": recovered_amount,
            "recovery_rate": recovery_rate,
            "escalated_cases": len(escalated_df),
            "open_cases": len(open_df)
        }
        return metrics, dataframe
    finally:
        db.close()

def load_audit_records():
    """
    Query audit trail records ordered chronologically.
    
    Returns:
        pd.DataFrame: Formatted audit trail dataframe.
    """
    db = SessionLocal()
    try:
        logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(250).all()
        rows = []
        for log in logs:
            rows.append({
                "Timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S") if log.timestamp else "",
                "Case ID": log.case_id,
                "Stage": log.stage,
                "Action": log.action,
                "Outcome": log.outcome,
                "Details": log.details,
                "Reasoning": log.llm_reasoning or ""
            })
        return pd.DataFrame(rows)
    finally:
        db.close()

metrics, cases_df = load_case_metrics()

# ====================== TOP KPI METRIC CARDS ======================
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="Revenue at Risk",
        value=f"₹{metrics['revenue_at_risk']:,.2f}",
        border=True
    )

with col2:
    st.metric(
        label="Recovered Revenue",
        value=f"₹{metrics['recovered_amount']:,.2f}",
        delta=f"{metrics['recovery_rate']:.1f}% conversion",
        border=True
    )

with col3:
    st.metric(
        label="Open Cases",
        value=f"{metrics['open_cases']} / {metrics['total_cases']}",
        border=True
    )

with col4:
    st.metric(
        label="Escalated to Human",
        value=metrics["escalated_cases"],
        border=True
    )

st.write("")

# ====================== CORE WORKFLOW TABS ======================
tab_overview, tab_runner, tab_cases, tab_audit = st.tabs([
    "Overview",
    "Run Agent",
    "Cases",
    "Audit Log"
])

# ----------------- TAB 1: OVERVIEW -----------------
with tab_overview:
    col_chart_left, col_chart_right = st.columns(2)
    
    with col_chart_left:
        st.markdown("##### Portfolio Status")
        status_counts = cases_df["status"].value_counts()
        st.bar_chart(status_counts, height=260)
        
    with col_chart_right:
        st.markdown("##### Failure Code Distribution")
        failure_counts = cases_df["failure_code"].value_counts()
        st.bar_chart(failure_counts, height=260)

    st.write("")
    st.markdown("##### Recovery Performance by Failure Type")
    
    summary_table = []
    for code, group in cases_df.groupby("failure_code"):
        total = len(group)
        rec = len(group[group["status"] == "recovered"])
        rate = (rec / total * 100) if total > 0 else 0
        total_vol = group["amount_inr"].sum()
        rec_vol = group["recovered_inr"].sum()
        summary_table.append({
            "Failure Code": code,
            "Total Cases": total,
            "Recovered Cases": rec,
            "Recovery Rate (%)": round(rate, 1),
            "Volume at Risk (INR)": round(total_vol, 2),
            "Volume Recovered (INR)": round(rec_vol, 2)
        })
        
    df_summary = pd.DataFrame(summary_table).sort_values(by="Recovery Rate (%)", ascending=False)
    st.dataframe(df_summary, use_container_width=True, hide_index=True)

# ----------------- TAB 2: RUN AGENT -----------------
with tab_runner:
    st.markdown("##### Interactive Case Execution")
    st.caption("Trigger diagnosis, channel decision, and payment link generation on a specific case.")
    
    col_input, col_action = st.columns([2, 1])
    with col_input:
        available_ids = cases_df["case_id"].tolist()
        target_case_id = st.selectbox("Select Case ID", available_ids)
    
    selected_row = cases_df[cases_df["case_id"] == target_case_id].iloc[0]
    
    # Case summary container
    with st.container(border=True):
        col_c1, col_c2, col_c3, col_c4 = st.columns(4)
        col_c1.write(f"**Customer:** {selected_row['customer_name']}")
        col_c2.write(f"**Amount:** ₹{selected_row['amount_inr']:,.2f}")
        col_c3.write(f"**Payment Method:** {selected_row['payment_method'].upper()}")
        col_c4.write(f"**Status:** `{selected_row['status']}`")
        
        col_c5, col_c6 = st.columns([1, 3])
        col_c5.write(f"**Failure Code:** `{selected_row['failure_code']}`")
        col_c6.write(f"**Description:** {selected_row['failure_description']}")

    st.write("")
    if st.button("Execute Recovery Agent", type="primary"):
        with st.spinner("Processing diagnosis and recovery workflow..."):
            initial_state: AgentState = {
                "case_id": target_case_id,
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
                
                st.success("Workflow completed successfully.")
                
                # Diagnosis Panel
                with st.container(border=True):
                    st.markdown("##### 1. Diagnosis")
                    diag = final_state.get("diagnosis", {})
                    col_d1, col_d2, col_d3 = st.columns(3)
                    col_d1.write(f"**Root Cause:** `{diag.get('root_cause', 'N/A')}`")
                    col_d2.write(f"**Severity:** `{diag.get('severity', 'N/A')}`")
                    col_d3.write(f"**Recoverable:** `{diag.get('is_recoverable', 'N/A')}`")
                    st.write(f"**Reasoning:** {diag.get('reasoning', 'N/A')}")

                # Decision Panel
                with st.container(border=True):
                    st.markdown("##### 2. Strategic Intervention")
                    dec = final_state.get("decision", {})
                    col_dec1, col_dec2, col_dec3 = st.columns(3)
                    col_dec1.write(f"**Action:** `{dec.get('action', 'N/A')}`")
                    col_dec2.write(f"**Channel:** `{dec.get('channel', 'N/A')}`")
                    col_dec3.write(f"**Tone:** `{dec.get('message_tone', 'N/A')}`")
                    st.text_area("Message Content", dec.get("message_body", ""), height=70, disabled=True)

                # Execution Results Panel
                with st.container(border=True):
                    st.markdown("##### 3. Execution & Payment Link")
                    exec_res = final_state.get("execution_result", {})
                    link = exec_res.get("payment_link")
                    if link:
                        st.write(f"**Razorpay Test Link:** [{link}]({link})")
                        
                    sim = exec_res.get("payment_simulation", {})
                    if sim:
                        if sim.get("paid"):
                            st.write(f"**Payment Status:** `PAID` (Recovered ₹{sim.get('recovered_amount', 0)/100:,.2f})")
                        else:
                            st.write("**Payment Status:** `PENDING` (Customer reminder queued)")

            except Exception as exc:
                st.error(f"Execution failed: {str(exc)}")

# ----------------- TAB 3: CASES -----------------
with tab_cases:
    col_f1, col_f2, col_f3 = st.columns([1, 1, 2])
    with col_f1:
        selected_status = st.selectbox("Status Filter", ["All"] + list(cases_df["status"].unique()))
    with col_f2:
        selected_code = st.selectbox("Failure Code Filter", ["All"] + list(cases_df["failure_code"].unique()))
    with col_f3:
        search_term = st.text_input("Search Case ID or Customer Name", "")

    filtered_df = cases_df.copy()
    if selected_status != "All":
        filtered_df = filtered_df[filtered_df["status"] == selected_status]
    if selected_code != "All":
        filtered_df = filtered_df[filtered_df["failure_code"] == selected_code]
    if search_term:
        filtered_df = filtered_df[
            filtered_df["customer_name"].str.contains(search_term, case=False, na=False) |
            filtered_df["case_id"].str.contains(search_term, case=False, na=False)
        ]

    st.dataframe(
        filtered_df[[
            "case_id", "customer_name", "amount_inr", "failure_code",
            "payment_method", "status", "recovery_attempts", "recovered_inr", "last_recovery_action"
        ]],
        use_container_width=True,
        hide_index=True
    )
    
    st.download_button(
        label="Export Cases (CSV)",
        data=filtered_df.to_csv(index=False).encode("utf-8"),
        file_name="subscription_cases.csv",
        mime="text/csv"
    )

# ----------------- TAB 4: AUDIT LOG -----------------
with tab_audit:
    audit_data = load_audit_records()
    
    if not audit_data.empty:
        col_af1, col_af2 = st.columns([1, 2])
        with col_af1:
            stage_choice = st.selectbox("Stage Filter", ["All"] + list(audit_data["Stage"].unique()))
        with col_af2:
            audit_query = st.text_input("Search Case ID in Audit Trail", "")
            
        filtered_audit = audit_data.copy()
        if stage_choice != "All":
            filtered_audit = filtered_audit[filtered_audit["Stage"] == stage_choice]
        if audit_query:
            filtered_audit = filtered_audit[filtered_audit["Case ID"].str.contains(audit_query, case=False, na=False)]
            
        st.dataframe(filtered_audit, use_container_width=True, hide_index=True)
        
        st.download_button(
            label="Export Audit Trail (CSV)",
            data=filtered_audit.to_csv(index=False).encode("utf-8"),
            file_name="recovery_audit_log.csv",
            mime="text/csv"
        )
    else:
        st.info("No audit records available.")
