# engines/compute_nj_full.py
from typing import Dict, List

def compute_nj(taxpayer: Dict, w2s: List[Dict]) -> Dict[str, float]:
    """
    NJ-1040 computation engine (Phase 2+).
    Handles wages, dependents, property tax credit, etc.
    """

    # --- Robust dependents handling (accept list or int) ---
    deps = taxpayer.get("dependents", [])
    if isinstance(deps, int):
        deps = [{"first": "", "last": "", "ssn": "", "digits": []} for _ in range(deps)]
    elif not isinstance(deps, list):
        deps = []
    num_dependents = len(deps)

    # --- Income sources ---
    nj_wages = sum(float(w.get("nj_wages", 0) or 0) for w in w2s)
    nj_withheld = sum(float(w.get("nj_withheld", 0) or 0) for w in w2s)

    other_income = float(taxpayer.get("other_income", 0) or 0)
    total_income = nj_wages + other_income

    # --- Exemptions ---
    base_exemption = 1000
    dep_exemption = 1500 * num_dependents
    exemptions = base_exemption + dep_exemption

    taxable_income = max(total_income - exemptions, 0)

    # --- Simple NJ tax rate stub ---
    tax = taxable_income * 0.03

    # --- NJ property tax credit ---
    property_tax_paid = float(taxpayer.get("property_tax_paid", 0) or 0)
    rent_paid = float(taxpayer.get("rent_paid", 0) or 0)
    months = int(taxpayer.get("months_at_property", 0) or 0)

    property_credit = 0
    if rent_paid > 0:
        property_credit = min(rent_paid * 0.18, 50)  # placeholder rule
    elif property_tax_paid > 0:
        property_credit = min(property_tax_paid * 0.18, 50)

    total_tax = max(tax - property_credit, 0)

    # --- Balance ---
    refund = max(nj_withheld - total_tax, 0)
    amount_owed = max(total_tax - nj_withheld, 0)

    return {
        "1": nj_wages,
        "11": total_income,
        "12": exemptions,
        "15": taxable_income,
        "16": total_tax,
        "19": nj_withheld,
        "65": refund,
        "66": amount_owed,
    }

