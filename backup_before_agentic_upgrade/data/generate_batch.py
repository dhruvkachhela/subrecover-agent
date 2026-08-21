# How this works:
# This script generates a synthetic batch of 100 failed subscription payments
# with realistic customer details, failure codes, payment methods, and timestamps.
# The generated records are saved to data/failed_subscriptions.csv for agent processing.

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

# Output path
OUTPUT_PATH = Path(__file__).parent / "failed_subscriptions.csv"

# Realistic failure codes and descriptions
FAILURE_TYPES = [
    ("insufficient_funds", "Insufficient funds in account"),
    ("bank_timeout", "Bank did not respond in time"),
    ("soft_decline", "Temporary decline by issuer"),
    ("card_expired", "Card has expired"),
    ("mandate_revoked", "Customer revoked the mandate"),
    ("issuer_unavailable", "Issuer system temporarily unavailable"),
    ("do_not_honor", "Do not honor"),
    ("invalid_account", "Invalid account details"),
]

PAYMENT_METHODS = ["upi", "card", "netbanking"]
FIRST_NAMES = ["Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan", "Krishna", "Ishaan",
               "Ananya", "Aadhya", "Pari", "Anika", "Navya", "Diya", "Myra", "Anvi", "Kiara", "Prisha"]
LAST_NAMES = ["Sharma", "Verma", "Patel", "Reddy", "Nair", "Singh", "Kumar", "Gupta", "Mehta", "Joshi"]

def random_phone():
    """Generate a random 10-digit Indian phone number with +91 prefix."""
    return f"+9198{random.randint(10000000, 99999999)}"

def random_email(name):
    """Generate a realistic email address based on customer name."""
    domains = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com"]
    return f"{name.lower().replace(' ', '.')}{random.randint(1,99)}@{random.choice(domains)}"

def generate_batch(num_cases: int = 100):
    """
    Generate synthetic failed subscription records and write to CSV.
    
    Parameters:
        num_cases (int): Number of failed transaction cases to generate.
        
    Returns:
        Path: The file path to the generated CSV file.
    """
    rows = []
    base_time = datetime.now() - timedelta(days=5)

    for i in range(1, num_cases + 1):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        full_name = f"{first} {last}"
        failure_code, failure_desc = random.choice(FAILURE_TYPES)
        method = random.choice(PAYMENT_METHODS)
        amount = random.choice([19900, 29900, 49900, 99900, 149900, 199900, 249900, 499900])  # in paise
        previous_attempts = random.randint(0, 2)
        failed_at = base_time + timedelta(hours=random.randint(0, 100))

        row = {
            "case_id": f"CASE{i:04d}",
            "merchant_id": f"merch_{random.randint(1001, 1050)}",
            "customer_id": f"cust_{i:04d}",
            "customer_name": full_name,
            "customer_phone": random_phone(),
            "customer_email": random_email(full_name),
            "subscription_id": f"sub_{i:04d}",
            "amount": amount,                    # in paise
            "currency": "INR",
            "failed_at": failed_at.isoformat(),
            "failure_code": failure_code,
            "failure_description": failure_desc,
            "payment_method": method,
            "previous_attempts": previous_attempts,
            "last_attempt_at": (failed_at - timedelta(hours=random.randint(1, 48))).isoformat() if previous_attempts > 0 else "",
            "status": "failed_recoverable",
            "recovered_amount": 0,
            "recovery_attempts": 0,
            "last_recovery_action": "",
            "escalated": False,
            "notes": ""
        }
        rows.append(row)

    # Write CSV
    fieldnames = list(rows[0].keys())
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {num_cases} cases -> {OUTPUT_PATH}")
    return OUTPUT_PATH

if __name__ == "__main__":
    generate_batch(100)
