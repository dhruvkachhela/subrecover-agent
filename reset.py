from app.reset_utils import reset_all, reset_cases
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset recovery cases")
    parser.add_argument("--all", action="store_true", help="Reset all cases")
    parser.add_argument("--status", type=str, help="Reset cases with specific status")
    parser.add_argument("--limit", type=int, help="Reset only first N cases")
    parser.add_argument("--clear-audit", action="store_true", help="Also clear audit logs")

    args = parser.parse_args()

    if args.all:
        reset_all(clear_audit=args.clear_audit)
    elif args.status:
        reset_cases(status=args.status, clear_audit=args.clear_audit)
    elif args.limit:
        reset_cases(limit=args.limit, clear_audit=args.clear_audit)
    else:
        print("Usage examples:")
        print("  python reset.py --all")
        print("  python reset.py --status escalated")
        print("  python reset.py --status recovered")
        print("  python reset.py --limit 20")
        print("  python reset.py --all --clear-audit")
