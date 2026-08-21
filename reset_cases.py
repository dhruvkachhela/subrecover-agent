# How this works:
# Helper script to reset the first 15 cases in SQLite back to initial failed_recoverable status
# so the batch recovery simulation can be executed cleanly.

from app.database import SessionLocal
from app.models import FailedSubscription, AuditLog

db = SessionLocal()

# Reset the first 15 cases
cases = db.query(FailedSubscription).limit(15).all()
for case in cases:
    case.status = "failed_recoverable"
    case.recovered_amount = 0
    case.recovery_attempts = 0
    case.last_recovery_action = ""
    case.escalated = False
    case.notes = ""

# Optional: clear audit logs for clean demo (or keep them)
# db.query(AuditLog).delete()

db.commit()
db.close()
print("Reset first 15 cases to failed_recoverable")
