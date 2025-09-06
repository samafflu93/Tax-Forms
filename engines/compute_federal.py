"""
Federal 1040 computation engine (stub for testing).
Later you’ll expand this to full line-by-line logic.
"""

from typing import Dict, List

def compute_federal(taxpayer: Dict, w2s: List[Dict]) -> Dict[str, float]:
    """
    Very simple placeholder:
      - Sum wages (Box 1) from all W-2s
      - Compute flat tax = 10% of wages
      - Compare against withheld (Box 2) from all W-2s
    """
    wages = sum(float(w.get("wages_box1", 0) or 0) for w in w2s)
    withheld = sum(float(w.get("fed_withheld_box2", 0) or 0) for w in w2s)

    # Fake tax: 10% flat
    tax = wages * 0.10

    refund = max(withheld - tax, 0)
    amount_owed = max(tax - withheld, 0)

    return {
        "1z": wages,        # Wages
        "2b": 0,            # Interest
        "3a": 0,            # Qualified dividends
        "3b": 0,            # Ordinary dividends
        "8": 0,             # Unemployment
        "11": wages,        # Pretend AGI = wages
        "12": 13850,        # Pretend standard deduction
        "15": max(wages - 13850, 0),
        "16": tax,
        "25d": withheld,
        "27": 0,            # EITC placeholder
        "34": refund,
        "37": amount_owed,
    }
