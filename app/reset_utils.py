from app.database import SessionLocal
from app.models import FailedSubscription, AuditLog
from typing import List, Optional

def reset_cases(
    status: Optional[str] = None,
    limit: Optional[int] = None,
    case_ids: Optional[List[str]] = None,
    clear_audit: bool = False
):
    """
    Clean utility to reset cases.
    
    Examples:
        reset_cases()                          → reset ALL cases
        reset_cases(status="escalated")        → reset only escalated
        reset_cases(status="recovered")        → reset only recovered
        reset_cases(limit=20)                  → reset first 20 cases
        reset_cases(case_ids=["CASE0001"])     → reset specific cases
    """
    db = SessionLocal()
    try:
        query = db.query(FailedSubscription)

        if case_ids:
            query = query.filter(FailedSubscription.case_id.in_(case_ids))
        elif status:
            query = query.filter(FailedSubscription.status == status)
        
        if limit:
            query = query.limit(limit)

        cases = query.all()
        count = 0

        for case in cases:
            case.status = "failed_recoverable"
            case.recovered_amount = 0
            case.recovery_attempts = 0
            case.last_recovery_action = ""
            case.escalated = False
            case.notes = ""
            count += 1

        if clear_audit:
            db.query(AuditLog).delete()

        db.commit()
        print(f"Successfully reset {count} cases.")
        return count

    finally:
        db.close()

def reset_all(clear_audit: bool = False):
    """Reset every case back to failed_recoverable"""
    return reset_cases(clear_audit=clear_audit)

def reset_open_only():
    """Only reset cases that are still open (usually not needed)"""
    return reset_cases(status="failed_recoverable")
