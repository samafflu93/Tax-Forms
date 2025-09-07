# engines/compute_federal_full.py
from typing import Dict, List

# ---------------------------
# CONFIG: edit for your tax year
# ---------------------------
# Standard deduction (example values; update to your year)
STD_DEDUCTION = {
    "single": 13850.0,
    "married_filing_jointly": 27700.0,
    "head_of_household": 20800.0,
}

# Progressive brackets by filing status.
# Format: list of (upper_limit, rate). The last tuple may use float("inf").
# NOTE: These are DEMO numbers. Replace with official thresholds for your tax year.
FEDERAL_BRACKETS = {
    "single": [
        (11000, 0.10),
        (44725, 0.12),
        (95375, 0.22),
        (182100, 0.24),
        (231250, 0.32),
        (578125, 0.35),
        (float("inf"), 0.37),
    ],
    "married_filing_jointly": [
        (22000, 0.10),
        (89450, 0.12),
        (190750, 0.22),
        (364200, 0.24),
        (462500, 0.32),
        (693750, 0.35),
        (float("inf"), 0.37),
    ],
    "head_of_household": [
        (15700, 0.10),
        (59850, 0.12),
        (95350, 0.22),
        (182100, 0.24),
        (231250, 0.32),
        (578100, 0.35),
        (float("inf"), 0.37),
    ],
}

# Optional simple credits (keep 0.0 for now; wire up later if you want)
CHILD_TAX_CREDIT_PER_CHILD = 0.0


def _progressive_tax(amount: float, brackets: List[tuple]) -> float:
    """Compute tax using a bracket table [(limit, rate), ...]."""
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


def compute_federal(taxpayer: Dict, w2s: List[Dict]) -> Dict[str, float]:
    """
    More complete federal engine (still simplified and configurable).
    - Supports filing_status (single/married_filing_jointly/head_of_household)
    - Sums wages + withheld from W-2s (expected headers: wages, federal_withheld)
    - AGI = wages + (optional) other incomes in taxpayer CSV: interest, dividends, unemployment
    - Taxable income = max(AGI - standard deduction, 0)
    - Tax computed with progressive brackets table above
    - Very simple credit hook (child tax credit placeholder)
    """
    filing_status = (taxpayer.get("filing_status") or "single").strip().lower()
    std_ded = STD_DEDUCTION.get(filing_status, STD_DEDUCTION["single"])

    wages = sum(float(w.get("wages", 0) or 0) for w in w2s)
    withheld = sum(float(w.get("federal_withheld", 0) or 0) for w in w2s)

    # Optional “other income” fields if you decide to include them in taxpayer CSV
    interest = float(taxpayer.get("interest", 0) or 0)
    qual_div = float(taxpayer.get("qualified_dividends", 0) or 0)
    ord_div = float(taxpayer.get("ordinary_dividends", 0) or 0)
    unemployment = float(taxpayer.get("unemployment", 0) or 0)

    agi = wages + interest + qual_div + ord_div + unemployment
    taxable_income = max(agi - std_ded, 0.0)

    brackets = FEDERAL_BRACKETS.get(filing_status, FEDERAL_BRACKETS["single"])
    gross_tax = _progressive_tax(taxable_income, brackets)

    # placeholder child credit
    dependents = float(taxpayer.get("dependents", 0) or 0)  # <- robust to list/empty
    credits = dependents * CHILD_TAX_CREDIT_PER_CHILD

    net_tax = max(gross_tax - credits, 0.0)
    refund = max(withheld - net_tax, 0.0)
    amount_owed = max(net_tax - withheld, 0.0)

    # Return a minimal line map compatible with your runner’s summary
    return {
        "1z": wages,
        "11": agi,
        "12": std_ded,
        "15": taxable_income,
        "16": net_tax,
        "25d": withheld,
        "34": refund,
        "37": amount_owed,
    }

