# How this works:
# This module defines SQLAlchemy ORM models for the database tables:
# 1. FailedSubscription: Stores individual failed recurring transactions and their recovery state.
# 2. AuditLog: Tracks all recovery agent steps, decisions, LLM reasoning, and outcomes.

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, Float
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class FailedSubscription(Base):
    """
    ORM model representing a failed subscription payment record.
    
    Stores customer details, payment method, failure diagnostics,
    retry tracking counts, escalation flags, and recovery status.
    """
    __tablename__ = "failed_subscriptions"

    case_id = Column(String, primary_key=True)
    merchant_id = Column(String, nullable=False)
    customer_id = Column(String, nullable=False)
    customer_name = Column(String)
    customer_phone = Column(String)
    customer_email = Column(String)
    subscription_id = Column(String, nullable=False)
    amount = Column(Integer, nullable=False)          # in paise
    currency = Column(String, default="INR")
    failed_at = Column(DateTime)
    failure_code = Column(String)
    failure_description = Column(String)
    payment_method = Column(String)
    previous_attempts = Column(Integer, default=0)
    last_attempt_at = Column(DateTime, nullable=True)
    status = Column(String, default="failed_recoverable")  # failed_recoverable | recovered | escalated | closed
    recovered_amount = Column(Integer, default=0)
    recovery_attempts = Column(Integer, default=0)
    last_recovery_action = Column(String, default="")
    escalated = Column(Boolean, default=False)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AuditLog(Base):
    """
    ORM model representing an audit log entry for recovery actions.
    
    Records every agent lifecycle stage (detect, diagnose, decide, execute, stop, escalate),
    action taken, detailed context, LLM reasoning logs, and outcome status.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    stage = Column(String)                # detect / diagnose / decide / execute / stop / escalate
    action = Column(String)
    details = Column(Text)
    llm_reasoning = Column(Text, nullable=True)
    outcome = Column(String, nullable=True)
