# engines/compute_nj.py
from typing import Dict, List

def compute_nj(taxpayer: Dict, w2s: List[Dict]) -> Dict[str, float]:
    """
    NJ computation engine (stub for testing only).

    Assumptions matched to your samples:
      - W-2 CSV has columns: wages, nj_withheld
      - Taxpayer CSV may have 'exemptions' (number).  We give $1,000 per exemption.
      - Flat 3% tax on (wages - exemption_amount), floor at 0.
    """

    # Sum wages and NJ withholding from all W-2s
    wages = sum(float(w.get("wages", 0) or 0) for w in w2s)
    withheld = sum(float(w.get("nj_withheld", 0) or 0) for w in w2s)

    # Optional exemptions from taxpayer CSV
    exemptions = float(taxpayer.get("exemptions", 0) or 0)
    exemption_amount = 1000.0 * exemptions

    taxable = max(wages - exemption_amount, 0.0)

    # Placeholder tax: flat 3% of taxable income
    tax = taxable * 0.03

    refund = max(withheld - tax, 0.0)
    balance_due = max(tax - withheld, 0.0)

    # Keys chosen to match the summary logic in run_nj.py
    return {
        "wages": wages,
        "taxable_income": taxable,
        "exemptions": exemptions,
        "withheld": withheld,
        "tax": tax,
        "refund": refund,
        "balance_due": balance_due,
    }


