# How this works:
# This module provides database engine creation, session management, and utility functions:
# 1. init_db: Creates SQLite tables according to SQLAlchemy ORM models.
# 2. load_csv_to_db: Imports synthetic failed subscription records from CSV into SQLite.
# 3. get_all_recoverable_cases: Queries all cases pending recovery.
# 4. get_case_by_id: Retrieves a single failed subscription case by its unique ID.

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import config
from app.models import Base, FailedSubscription, AuditLog
import pandas as pd
from datetime import datetime
from pathlib import Path

engine = create_engine(config.DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """
    Create all database tables defined in the ORM schema.
    
    Binds the metadata to the configured database engine.
    """
    Base.metadata.create_all(bind=engine)
    print("Database tables created.")

def ensure_db_initialized():
    """Ensure tables exist and seed sample CSV if empty."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        count = db.query(FailedSubscription).count()
        if count == 0:
            load_csv_to_db()
    except Exception:
        load_csv_to_db()
    finally:
        db.close()

def get_db():
    """
    Generator that provides a transactional database session.
    
    Yields:
        Session: Active SQLAlchemy session, safely closed on completion.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def load_csv_to_db(csv_path: str = "data/failed_subscriptions.csv"):
    """
    Load synthetic failed subscription records from CSV into the database.
    
    Parameters:
        csv_path (str): Relative or absolute path to the source CSV file.
    """
    df = pd.read_csv(csv_path)

    db = SessionLocal()
    try:
        # Clear existing data (for clean runs)
        db.query(AuditLog).delete()
        db.query(FailedSubscription).delete()
        db.commit()

        for _, row in df.iterrows():
            case = FailedSubscription(
                case_id=row["case_id"],
                merchant_id=row["merchant_id"],
                customer_id=row["customer_id"],
                customer_name=row["customer_name"],
                customer_phone=row["customer_phone"],
                customer_email=row["customer_email"],
                subscription_id=row["subscription_id"],
                amount=int(row["amount"]),
                currency=row["currency"],
                failed_at=datetime.fromisoformat(row["failed_at"]) if pd.notna(row["failed_at"]) else None,
                failure_code=row["failure_code"],
                failure_description=row["failure_description"],
                payment_method=row["payment_method"],
                previous_attempts=int(row["previous_attempts"]),
                last_attempt_at=datetime.fromisoformat(row["last_attempt_at"]) if pd.notna(row["last_attempt_at"]) and row["last_attempt_at"] != "" else None,
                status=row["status"],
                recovered_amount=int(row["recovered_amount"]),
                recovery_attempts=int(row.get("recovery_attempts", 0)),
                last_recovery_action=row.get("last_recovery_action", ""),
                escalated=bool(row.get("escalated", False)),
                notes=row.get("notes", "")
            )
            db.add(case)
        db.commit()
        print(f"Loaded {len(df)} cases into database.")
    finally:
        db.close()

def get_all_recoverable_cases():
    """
    Retrieve all failed subscription cases currently marked as recoverable.
    
    Returns:
        list[FailedSubscription]: List of failed subscription ORM records.
    """
    db = SessionLocal()
    try:
        return db.query(FailedSubscription).filter(
            FailedSubscription.status == "failed_recoverable"
        ).all()
    finally:
        db.close()

def get_case_by_id(case_id: str):
    """
    Retrieve a specific subscription failure record by its unique case_id.
    
    Parameters:
        case_id (str): The unique case identifier (e.g., 'CASE0001').
        
    Returns:
        FailedSubscription | None: The matching ORM record, or None if not found.
    """
    db = SessionLocal()
    try:
        return db.query(FailedSubscription).filter(
            FailedSubscription.case_id == case_id
        ).first()
    finally:
        db.close()
