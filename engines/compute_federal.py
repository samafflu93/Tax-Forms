"""
Federal 1040 computation engine (stub for testing).
Later you’ll expand this to full line-by-line logic.
"""

# engines/compute_federal.py
from typing import Dict, List

def compute_federal(taxpayer: Dict, w2s: List[Dict]) -> Dict[str, float]:
    """
    Federal 1040 computation engine (stub for testing).
    Uses wages + federal_withheld from your sample CSVs.
    """

    wages = sum(float(w.get("wages", 0) or 0) for w in w2s)
    withheld = sum(float(w.get("federal_withheld", 0) or 0) for w in w2s)

    tax = wages * 0.10  # TEMP: 10% flat tax
    refund = max(withheld - tax, 0)
    amount_owed = max(tax - withheld, 0)

    return {
        "1z": wages,         # Wages
        "11": wages,         # Pretend AGI = wages
        "12": 13850,         # Pretend standard deduction
        "15": max(wages - 13850, 0),
        "16": tax,           # total tax
        "25d": withheld,     # fed tax withheld
        "34": refund,        # refund
        "37": amount_owed,   # amount owed
    }
