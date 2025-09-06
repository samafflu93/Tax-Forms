# engines/compute_nj_full.py
from typing import Dict, List

# ---------------------------
# CONFIG: edit for your tax year
# ---------------------------
# Per-exemption reduction (demo value)
EXEMPTION_AMOUNT = 1000.0

# NJ progressive brackets (DEMO numbers; replace with official year values)
# list of (upper_limit, rate)
NJ_BRACKETS = [
    (20000, 0.014),
    (35000, 0.0175),
    (40000, 0.035),
    (75000, 0.05525),
    (500000, 0.0637),
    (1000000, 0.0897),
    (float("inf"), 0.1075),
]


def _progressive_tax(amount: float, brackets: List[tuple]) -> float:
    tax = 0.0
    prev = 0.0
    for limit, rate in brackets:
        if amount <= prev:
            break
        taxable_here = min(amount, limit) - prev
        if taxable_here > 0:
            tax += taxable_here * rate
        prev = limit
        if amount <= limit:
            break
    return max(tax, 0.0)


def compute_nj(taxpayer: Dict, w2s: List[Dict]) -> Dict[str, float]:
    """
    More complete NJ engine (still simplified and configurable).
    - Sums wages + nj_withheld from W-2s (headers: wages, nj_withheld)
    - Applies per-exemption reduction from taxpayer CSV field 'exemptions'
    - Computes progressive tax using NJ_BRACKETS
    """
    wages = sum(float(w.get("wages", 0) or 0) for w in w2s)
    withheld = sum(float(w.get("nj_withheld", 0) or 0) for w in w2s)

    exemptions = float(taxpayer.get("exemptions", 0) or 0)
    taxable = max(wages - exemptions * EXEMPTION_AMOUNT, 0.0)

    tax = _progressive_tax(taxable, NJ_BRACKETS)
    refund = max(withheld - tax, 0.0)
    balance_due = max(tax - withheld, 0.0)

    return {
        "wages": wages,
        "taxable_income": taxable,
        "exemptions": exemptions,
        "withheld": withheld,
        "tax": tax,
        "refund": refund,
        "balance_due": balance_due,
    }
