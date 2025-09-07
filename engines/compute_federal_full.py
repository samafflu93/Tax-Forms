# engines/compute_federal_full.py
from typing import Dict, List, Tuple

"""
Prototype Federal 1040 calculator (simplified, 2024-ish)
- Supports: wages, interest, dividends (optional), dependents, filing status
- Uses standard deduction only (no itemized)
- Progressive brackets
- Basic Child Tax Credit (nonrefundable portion only, $2,000 per child under 17,
  phase-out starts at $200k Single/HoH/MFS and $400k MFJ)
- Result lines: minimal mapping to help your PDF-mapper later
Edit the CONSTANTS below to update amounts.
"""

# -----------------------
# CONSTANTS / PARAMETERS
# -----------------------

STD_DED = {
    "single": 14600.0,
    "married_filing_jointly": 29200.0,
    "married_filing_separately": 14600.0,
    "head_of_household": 21900.0,
    "qualifying_widow": 29200.0,
}

# Progressive tax brackets (2024-ish). Each status maps to a list of (limit, rate).
# "limit" is the top of the bracket; last bracket uses float("inf")
BRACKETS_2024 = {
    "single": [
        (11600, 0.10),
        (47150, 0.12),
        (100525, 0.22),
        (191950, 0.24),
        (243725, 0.32),
        (609350, 0.35),
        (float("inf"), 0.37),
    ],
    "married_filing_jointly": [
        (23200, 0.10),
        (94300, 0.12),
        (201050, 0.22),
        (383900, 0.24),
        (487450, 0.32),
        (731200, 0.35),
        (float("inf"), 0.37),
    ],
    "married_filing_separately": [
        (11600, 0.10),
        (47150, 0.12),
        (100525, 0.22),
        (191950, 0.24),
        (243725, 0.32),
        (365600, 0.35),
        (float("inf"), 0.37),
    ],
    "head_of_household": [
        (16550, 0.10),
        (63100, 0.12),
        (100500, 0.22),
        (191950, 0.24),
        (243700, 0.32),
        (609350, 0.35),
        (float("inf"), 0.37),
    ],
    "qualifying_widow": [  # treat same as MFJ for simplicity
        (23200, 0.10),
        (94300, 0.12),
        (201050, 0.22),
        (383900, 0.24),
        (487450, 0.32),
        (731200, 0.35),
        (float("inf"), 0.37),
    ],
}

# Child Tax Credit (simplified nonrefundable portion)
CTC_PER_CHILD = 2000.0
CTC_PHASEOUT = {
    "single": 200000.0,
    "married_filing_jointly": 400000.0,
    "married_filing_separately": 200000.0,
    "head_of_household": 200000.0,
    "qualifying_widow": 400000.0,
}
CTC_PHASEOUT_REDUCTION_PER_1000 = 50.0  # $50 reduction per $1,000 over threshold


def _coerce_float(x, default=0.0) -> float:
    if x is None:
        return default
    if isinstance(x, (int, float)):
        return float(x)
    # strings like "12,345.67"
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return default


def _sum_key(rows: List[Dict], key: str) -> float:
    return sum(_coerce_float(r.get(key)) for r in rows)


def tax_from_brackets(taxable: float, brackets: List[Tuple[float, float]]) -> float:
    """Compute tax using piecewise brackets. 'brackets' = [(limit, rate), ...]."""
    tax = 0.0
    prev_limit = 0.0
    remaining = taxable
    for limit, rate in brackets:
        chunk = min(remaining, limit - prev_limit)
        if chunk > 0:
            tax += chunk * rate
            remaining -= chunk
            prev_limit = limit
        if remaining <= 0:
            break
    return max(tax, 0.0)


def compute_federal(taxpayer: Dict, w2s: List[Dict]) -> Dict[str, float]:
    """
    Inputs:
      taxpayer: dict from wizard (filing_status, dependents (list), etc.)
      w2s: list of W2 dicts (wages_box1, fed_withheld_box2, etc.)
    Output:
      dict of simplified 1040 lines + helpful fields
    """
    status = (taxpayer.get("filing_status") or "single").strip().lower()

    # Income
    wages = _sum_key(w2s, "wages_box1")
    interest = _coerce_float(taxpayer.get("interest"), 0.0)
    dividends = _coerce_float(taxpayer.get("dividends"), 0.0)
    agi = wages + interest + dividends  # prototype AGI

    # Standard deduction
    std_ded = STD_DED.get(status, STD_DED["single"])
    taxable_income = max(0.0, agi - std_ded)

    # Regular tax from brackets
    brackets = BRACKETS_2024.get(status, BRACKETS_2024["single"])
    regular_tax = tax_from_brackets(taxable_income, brackets)

    # Child Tax Credit (nonrefundable portion only, simplified)
    dependents = taxpayer.get("dependents", [])
    num_ctc_kids = 0
    for d in dependents if isinstance(dependents, list) else []:
        # very light check: treat children under 17 as CTC-eligible if dob provided & year >= 2008-ish
        dob = str(d.get("dob", ""))
        # if no DOB, still count as child for prototype when relationship looks like 'son/daughter'
        rel = (d.get("relationship") or "").lower()
        is_kid = ("son" in rel or "daughter" in rel or "child" in rel)
        if is_kid or dob:
            num_ctc_kids += 1

    ctc_threshold = CTC_PHASEOUT.get(status, 200000.0)
    over = max(0.0, agi - ctc_threshold)
    phaseout_reduction = (over // 1000.0) * CTC_PHASEOUT_REDUCTION_PER_1000
    tentative_ctc = max(0.0, num_ctc_kids * CTC_PER_CHILD - phaseout_reduction)
    nonrefundable_ctc = min(regular_tax, tentative_ctc)

    # Withholding
    federal_withheld = _sum_key(w2s, "fed_withheld_box2")

    # Final tax / refund
    total_tax = max(0.0, regular_tax - nonrefundable_ctc)
    refund = max(0.0, federal_withheld - total_tax)
    amount_owed = max(0.0, total_tax - federal_withheld)

    # Minimal 1040-like map
    return {
        # helpful extras
        "agi": agi,
        "std_deduction": std_ded,
        "taxable_income": taxable_income,
        "regular_tax": total_tax + nonrefundable_ctc,  # tax before nonrefundable credits
        "child_tax_credit_nonrefundable": nonrefundable_ctc,
        "total_tax": total_tax,
        "withheld": federal_withheld,
        "refund": refund,
        "amount_owed": amount_owed,
        # example line slots you can map to PDF later
        "11": agi,                 # AGI
        "12": std_ded,             # Std deduction
        "15": taxable_income,      # Taxable income
        "24": total_tax,           # Total tax (prototype)
        "25d": federal_withheld,   # Fed withholding
        "34": refund,              # Refund
        "37": amount_owed,         # Amount you owe
    }
