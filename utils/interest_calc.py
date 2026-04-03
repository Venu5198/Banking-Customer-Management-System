"""
Interest calculation utilities.

EMI Formula (standard amortization):
  EMI = P * r * (1+r)^n / ((1+r)^n - 1)
  where:
    P = principal (in paise)
    r = monthly interest rate (annual_rate / 12 / 100)
    n = tenure in months

FD Rates (by tenure):
  6 months:  6.50% p.a.
  12 months: 7.00% p.a.
  24 months: 7.25% p.a.
  36 months: 7.50% p.a.
  60 months: 7.50% p.a.

Savings rate: 3.5% p.a. (interest accrued daily, credited monthly)
"""

import math
from typing import List, Dict

# FD interest rates in basis points by tenure (months)
FD_RATES_BPS: Dict[int, int] = {
    6:  650,   # 6.50%
    12: 700,   # 7.00%
    24: 725,   # 7.25%
    36: 750,   # 7.50%
    60: 750,   # 7.50%
}

# Savings account interest rate in basis points
SAVINGS_RATE_BPS = 350   # 3.50% p.a.


def get_fd_rate(tenure_months: int) -> int:
    """
    Return FD interest rate in basis points for a given tenure.
    Uses the closest supported tenure.
    """
    if tenure_months not in FD_RATES_BPS:
        # Round to nearest supported tenure
        supported = sorted(FD_RATES_BPS.keys())
        closest = min(supported, key=lambda x: abs(x - tenure_months))
        return FD_RATES_BPS[closest]
    return FD_RATES_BPS[tenure_months]


def calculate_emi(principal_paise: int, annual_rate_bps: int, tenure_months: int) -> int:
    """
    Calculate monthly EMI in paise using standard amortization formula.
    Returns integer (floors sub-paisa amounts).
    
    For 0% interest (e.g., special schemes): returns principal / tenure.
    """
    if annual_rate_bps == 0:
        return math.ceil(principal_paise / tenure_months)

    # Monthly rate as decimal
    r = (annual_rate_bps / 100) / (12 * 100)
    n = tenure_months
    P = principal_paise

    # EMI = P * r * (1+r)^n / ((1+r)^n - 1)
    factor = (1 + r) ** n
    emi = P * r * factor / (factor - 1)
    return int(math.ceil(emi))   # Always round up to avoid underpayment


def calculate_amortization_schedule(
    principal_paise: int,
    annual_rate_bps: int,
    tenure_months: int,
    emi_paise: int
) -> List[Dict]:
    """
    Generate full amortization schedule.
    Returns list of dicts: {emi_number, principal_component, interest_component, balance}
    All values in paise.
    """
    r = (annual_rate_bps / 100) / (12 * 100)
    balance = principal_paise
    schedule = []

    for i in range(1, tenure_months + 1):
        interest_component = int(balance * r)
        principal_component = emi_paise - interest_component

        # Last EMI adjustment: clear remaining balance
        if i == tenure_months:
            principal_component = balance
            emi_paise_actual = principal_component + interest_component
        else:
            emi_paise_actual = emi_paise

        balance -= principal_component
        if balance < 0:
            balance = 0

        schedule.append({
            "emi_number": i,
            "emi_amount_paise": emi_paise_actual,
            "principal_component_paise": principal_component,
            "interest_component_paise": interest_component,
            "balance_after_paise": balance,
        })

    return schedule


def calculate_daily_interest(balance_paise: int, annual_rate_bps: int) -> int:
    """
    Calculate one day's interest accrual in paise.
    Daily rate = annual_rate / 365
    """
    daily_rate = (annual_rate_bps / 100) / (365 * 100)
    return int(balance_paise * daily_rate)


def calculate_fd_premature_penalty(principal_paise: int) -> int:
    """
    Penalty for premature FD withdrawal: 1% of principal.
    """
    return int(principal_paise * 0.01)
