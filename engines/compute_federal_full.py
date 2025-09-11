# engines/compute_federal_full.py
from typing import Dict, List

def compute_federal(taxpayer: Dict, w2s: List[Dict]) -> Dict[str, float]:
    """
    Federal 1040 computation engine (Phase 2+).
    Handles wages, dependents, credits, other income, etc.
    """

    # --- Robust dependents handling (accept list or int) ---
    deps = taxpayer.get("dependents", [])
    if isinstance(deps, int):
        # Coerce to a list of empty dependent shells with that length
        deps = [{"first": "", "last": "", "ssn": "", "digits": []} for _ in range(deps)]
    elif not isinstance(deps, list):
        deps = []
    num_dependents = len(deps)

    # --- Income sources ---
    wages = sum(float(w.get("wages", 0) or 0) for w in w2s)
    fed_withheld = sum(float(w.get("federal_withheld", 0) or 0) for w in w2s)

    interest = float(taxpayer.get("interest", 0) or 0)
    dividends = float(taxpayer.get("dividends", 0) or 0)
    unemployment = float(taxpayer.get("unemployment", 0) or 0)
    nec_income = float(taxpayer.get("nec_income", 0) or 0)
    nec_expenses = float(taxpayer.get("nec_expenses", 0) or 0)
    nec_net = max(nec_income - nec_expenses, 0)
    ssa_benefits = float(taxpayer.get("ssa_benefits", 0) or 0)
    pension = float(taxpayer.get("pension", 0) or 0)

    # Total income
    total_income = wages + interest + dividends + unemployment + nec_net + ssa_benefits + pension

    # --- Adjustments ---
    student_loan_int = float(taxpayer.get("student_loan_interest", 0) or 0)
    ira_contrib = float(taxpayer.get("ira_contributions", 0) or 0)
    hsa_contrib = float(taxpayer.get("hsa_contributions", 0) or 0)
    adjustments = student_loan_int + ira_contrib + hsa_contrib

    agi = total_income - adjustments

    # --- Standard deduction ---
    filing_status = taxpayer.get("filing_status", "single")
    std_deductions = {
        "single": 13850,
        "married_joint": 27700,
        "married_separate": 13850,
        "head_household": 20800,
        "qual_widow": 27700,
    }
    deduction = std_deductions.get(filing_status, 13850)

    taxable_income = max(agi - deduction, 0)

    # --- Tax calculation (simple bracket stub) ---
    tax = taxable_income * 0.10  # Replace with real brackets later

    # --- Credits ---
    child_credit = num_dependents * 2000
    earned_income_credit = 0  # placeholder

    total_tax = max(tax - (child_credit + earned_income_credit), 0)

    # --- Balance ---
    refund = max(fed_withheld - total_tax, 0)
    amount_owed = max(total_tax - fed_withheld, 0)

    return {
        "1z": wages,
        "2b": interest,
        "3b": dividends,
        "7": unemployment,
        "8": nec_net,
        "11": agi,
        "12": deduction,
        "15": taxable_income,
        "16": total_tax,
        "25d": fed_withheld,
        "34": refund,
        "37": amount_owed,
    }

