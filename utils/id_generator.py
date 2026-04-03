"""
Unique ID generators for accounts, transactions, and loans.
All IDs include timestamps + random suffix to prevent collisions.
"""

import random
import string
from datetime import datetime


def _random_suffix(length: int = 6) -> str:
    """Generate a random alphanumeric suffix (uppercase)."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def generate_account_number() -> str:
    """
    Format: ACC-YYYY-XXXXXX
    Example: ACC-2024-A3B7K2
    """
    year = datetime.utcnow().year
    return f"ACC-{year}-{_random_suffix(6)}"


def generate_txn_id() -> str:
    """
    Format: TXN-YYYYMMDD-XXXXXX
    Example: TXN-20240315-X9K2P1
    """
    date_str = datetime.utcnow().strftime("%Y%m%d")
    return f"TXN-{date_str}-{_random_suffix(6)}"


def generate_loan_id() -> str:
    """
    Format: LN-YYYY-XXXXXX
    Example: LN-2024-M3P9Q1
    """
    year = datetime.utcnow().year
    return f"LN-{year}-{_random_suffix(6)}"
