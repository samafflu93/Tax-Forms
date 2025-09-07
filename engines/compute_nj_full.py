# engines/compute_nj_full.py
from typing import Dict, List, Tuple

"""
Prototype NJ-1040 calculator (simplified)
- Uses NJ wages (W-2 Box 16) as income
- Personal exemptions: filer + spouse (if MFJ) + dependents (editable constants)
- Progressive NJ brackets (approx 2024)
- Small demo Rent Credit (e.g., 1% of rent paid, capped) to illustrate state credits
Edit the CONSTANTS below to refine amounts/rates.
"""

# -----------------------
# CONSTANTS / PARAMETERS
# -----------------------

# Personal exemptions (prototype)
NJ_EXEMPT_TAXPAYER = 1000.0
NJ_EXEMPT_SPOUSE = 1000.0          # when filing MFJ
NJ_EXEMPT_DEPENDENT = 1500.0       # each dependent

# NJ progressive brackets (approx; single and joint differ mainly in thresholds)
# Format: [(limit, rate), ...], last uses inf
NJ_BRACKETS_SINGLE = [
    (20000, 0.014),
    (35000, 0.0175),
    (40000, 0.035),
    (75000, 0.05525),
    (500000, 0.0637),
    (1000000, 0.0897),  # top surcharge bracket demo
    (float("inf"), 0.1075),
]

NJ_BRACKETS_MFJ = [
    (20000, 0.014),
    (50000, 0.0175),
    (70000, 0.0245),
    (80000, 0.035),
    (150000, 0.05525),
    (500000, 0.0637),
    (1000000, 0.0897),
    (float("inf"), 0.1075),
]

# Demo rent/property credit logic (very simplified)
RENT_CREDIT_RATE = 0.01      # 1% of rent paid
RENT_CREDIT_CAP = 50.0       # cap credit at $50 for demo


def _coerce_float(x, default=0.0) -> float:
    if x is None:
        return default
    if isinstance(x, (int, float)):
        return float(x)
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return default


def _sum_key(rows: List[Dict], key: str) -> float:
    return sum(_coerce_float(r.get(key)) for r in rows)


def tax_from_brackets(taxable: float, brackets: List[Tuple[float, float]]) -> float:
    tax = 0.0
    prev = 0.0
    r = taxable
    for limit, rate in brackets:
        chunk = min(r, limit - prev)
        if chunk > 0:
            tax += chunk * rate
            r -= chunk
            prev = limit
        if r <= 0:
            break
    return max(tax, 0.0)


def compute_nj(taxpayer: Dict, w2s: List[Dict]) -> Dict[str, float]:
    """
    Inputs:
      taxpayer: wizard dict (filing_status, dependents, rent info, etc.)
      w2s: list of W2 dicts (nj_wages_box16, nj_withheld_box17)
    Output:
      simplified NJ-1040 mapping
    """
    status = (taxpayer.get("filing_status") or "single").strip().lower()
    is_mfj = (status == "married_filing_jointly")

    nj_wages = _sum_key(w2s, "nj_wages_box16")
    nj_withheld = _sum_key(w2s, "nj_withheld_box17")

    # Exemptions
    dependents = taxpayer.get("dependents", [])
    num_deps = len(dependents) if isinstance(dependents, list) else 0

    exemptions = NJ_EXEMPT_TAXPAYER
    if is_mfj:
        exemptions += NJ_EXEMPT_SPOUSE
    exemptions += num_deps * NJ_EXEMPT_DEPENDENT

    taxable_income = max(0.0, nj_wages - exemptions)

    brackets = NJ_BRACKETS_MFJ if is_mfj else NJ_BRACKETS_SINGLE
    regular_tax = tax_from_brackets(taxable_income, brackets)

    # Demo rent/property credit (optional)
    rent_paid = _coerce_float(taxpayer.get("nj_rent_paid"), 0.0)
    rent_credit = 0.0
    if rent_paid > 0:
        rent_credit = min(RENT_CREDIT_RATE * rent_paid, RENT_CREDIT_CAP)

    total_tax = max(0.0, regular_tax - rent_credit)
    refund = max(0.0, nj_withheld - total_tax)
    amount_owed = max(0.0, total_tax - nj_withheld)

    return {
        "nj_income": nj_wages,
        "exemptions": exemptions,
        "taxable_income": taxable_income,
        "regular_tax": regular_tax,
        "rent_credit": rent_credit,
        "total_tax": total_tax,
        "withheld": nj_withheld,
        "refund": refund,
        "amount_owed": amount_owed,
        # example line slots
        "11": nj_wages,        # income
        "12": exemptions,      # exemptions
        "15": taxable_income,  # taxable
        "24": total_tax,       # total tax (prototype)
        "25d": nj_withheld,    # NJ withholding
        "34": refund,          # refund
        "37": amount_owed,     # balance due
    }

