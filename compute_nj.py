# compute_nj.py  (v2)
# NJ-1040 computation for simple filers with W-2 wages, interest/dividends,
# property-tax deduction/credit, and NJ-EITC (as % of federal EITC).
#
# Inputs:
#   taxpayer: dict (see keys used below)
#   w2s: list[dict]  (state_wages_box16, state_withheld_box17, etc.)
#
# Outputs:
#   {"lines": {...}, "summary": {...}}
#   lines keys are NJ-1040 line numbers as strings (e.g., "15","16a","17","27","43","55","66","67","68","80")

from typing import Dict, List, Tuple

# ----------------- CONFIG (edit per tax year) -----------------

# Exemptions (2024)
EXEMPT_PERSONAL_EACH        = 1000
EXEMPT_DEPENDENT_EACH       = 1500
EXEMPT_OVER65_EACH          = 1000
EXEMPT_BLIND_DISABLED_EACH  = 1000
EXEMPT_VETERAN_EACH         = 6000

# Property tax deduction vs. credit (simple model)
# - Deduction: up to LIMIT reduces taxable income (Line 41)
# - Credit: flat amount reduces tax directly (falls into credits bucket)
PROPERTY_TAX_DED_LIMIT      = 15000     # set to the annual limit for deduction
PROPERTY_TAX_CREDIT_AMOUNT  = 50        # flat credit alternative (per return, simple MVP)

# NJ EITC as % of Federal EITC (edit to official % each year)
NJ_EITC_RATE                = 0.40      # e.g., 40% of federal EITC (update when you confirm for the year)

# NJ Brackets (lightweight; enough for ≤ ~100k)
BRACKETS_SINGLE_MFS = [
    (20000,   0.0140),
    (35000,   0.0175),
    (40000,   0.0350),
    (75000,   0.05525),
    (500000,  0.0637),
    (5_000_000, 0.0897),
    (float("inf"), 0.1075),
]
BRACKETS_MFJ = [
    (20000,   0.0140),
    (50000,   0.0175),
    (70000,   0.0245),
    (80000,   0.0350),
    (150000,  0.05525),
    (500000,  0.0637),
    (5_000_000, 0.0897),
    (float("inf"), 0.1075),
]

# ----------------- HELPERS -----------------

def _safe_num(x, default=0.0):
    try:
        if x is None or str(x).strip() == "":
            return float(default)
        return float(str(x).replace("$","").replace(",",""))
    except Exception:
        return float(default)

def _round_dollar(x: float) -> int:
    return int(round(float(x)))

def _sum(values):
    return _round_dollar(sum(_safe_num(v, 0.0) for v in values))

def _get_brackets(filing_status: str):
    fs = (filing_status or "").upper()
    return BRACKETS_MFJ if fs == "MFJ" else BRACKETS_SINGLE_MFS

def _tax_from_brackets(taxable: float, brackets) -> float:
    if taxable <= 0: return 0.0
    tax = 0.0
    last = 0.0
    remain = taxable
    for cap, rate in brackets:
        step = min(remain, cap - last)
        if step > 0:
            tax += step * rate
            remain -= step
            last = cap
        if remain <= 0: break
    return tax

# ----------------- EXEMPTIONS -----------------

def calculate_exemptions(data: Dict) -> int:
    total = 0
    fs = (data.get("filing_status") or "").upper()

    # Personal
    total += EXEMPT_PERSONAL_EACH
    if fs in ("MFJ","MFS","QW"):
        total += EXEMPT_PERSONAL_EACH

    # Dependents
    dep = int(_safe_num(data.get("exempt_dependent_count"), 0))
    total += dep * EXEMPT_DEPENDENT_EACH

    # Age 65+
    if data.get("exempt_taxpayer_over65"): total += EXEMPT_OVER65_EACH
    if fs in ("MFJ","MFS","QW") and data.get("exempt_spouse_over65"): total += EXEMPT_OVER65_EACH

    # Blind/Disabled
    if data.get("exempt_taxpayer_blind_disabled"): total += EXEMPT_BLIND_DISABLED_EACH
    if fs in ("MFJ","MFS","QW") and data.get("exempt_spouse_blind_disabled"): total += EXEMPT_BLIND_DISABLED_EACH

    # Veterans
    if data.get("exempt_taxpayer_veteran"): total += EXEMPT_VETERAN_EACH
    if fs in ("MFJ","MFS","QW") and data.get("exempt_spouse_veteran"): total += EXEMPT_VETERAN_EACH

    return _round_dollar(total)

# ----------------- MAIN -----------------

def compute_nj(taxpayer: Dict, w2s: List[Dict]) -> Dict[str, int]:
    """
    Returns dict with:
      - lines: NJ-1040 line map (whole-dollar ints)
      - summary: convenient summary fields
    Supports:
      * W-2 wages (Box 16 to Line 15)
      * Taxable interest (Line 16a), dividends (Line 17)
      * Exemptions → Line 13 → Line 30
      * Property-tax deduction (Line 41) vs. credit (into credits bucket)
      * NJ-EITC (as % of federal EITC)
    """

    fs = (taxpayer.get("filing_status") or "").upper()

    # ---- Income (W-2 + interest/dividends) ----
    line15_w2_nj_wages = _sum([w.get("state_wages_box16", 0) for w in w2s])  # Line 15

    line16a_interest = _round_dollar(_safe_num(taxpayer.get("interest_taxable"), 0))
    line17_dividends = _round_dollar(_safe_num(taxpayer.get("dividends_taxable"), 0))

    # Line 27 = sum of supported income lines in our MVP
    line27_total_income = line15_w2_nj_wages + line16a_interest + line17_dividends

    # Line 28c exclusions (none in MVP)
    line28c_exclusions = 0
    line29_nj_gross_income = max(0, line27_total_income - line28c_exclusions)

    # ---- Exemptions (Line 13 → Line 30) ----
    line13_total_exemptions = calculate_exemptions(taxpayer)
    line30_exemption_amount = line13_total_exemptions

    # For MVP, treat Line 38 as just Line 30 (no other deductions 31–37c)
    line38_total_exemptions_and_deductions = line30_exemption_amount

    # ---- Taxable income before property tax deduction ----
    line39_taxable_income = max(0, line29_nj_gross_income - line38_total_exemptions_and_deductions)

    # ---- Property tax: choose deduction vs credit (whichever yields lower tax) ----
    property_tax_paid = _round_dollar(_safe_num(taxpayer.get("property_tax_paid"), 0))
    prop_deduction = min(property_tax_paid, PROPERTY_TAX_DED_LIMIT)

    # Compute two scenarios:
    brackets = _get_brackets(fs)

    # (A) Deduction route: reduce taxable income at Line 41
    line41_property_tax_deduction = prop_deduction
    nj_taxable_via_ded = max(0, line39_taxable_income - line41_property_tax_deduction)
    tax_via_ded = _round_dollar(_tax_from_brackets(nj_taxable_via_ded, brackets))
    credits_via_ded = 0  # credits bucket if we don't take the flat credit

    # (B) Credit route: no Line 41 deduction; take a flat credit later
    nj_taxable_via_credit = line39_taxable_income
    tax_via_credit = _round_dollar(_tax_from_brackets(nj_taxable_via_credit, brackets))
    credits_via_credit = PROPERTY_TAX_CREDIT_AMOUNT if property_tax_paid > 0 else 0

    # Choose better (lower final tax before withholdings)
    if (tax_via_ded - credits_via_ded) <= (tax_via_credit - credits_via_credit):
        # take deduction
        chosen_line41 = line41_property_tax_deduction
        precredit_tax = tax_via_ded
        extra_credits = 0
        line42_nj_taxable_income = nj_taxable_via_ded
    else:
        # take credit
        chosen_line41 = 0
        precredit_tax = tax_via_credit
        extra_credits = credits_via_credit
        line42_nj_taxable_income = nj_taxable_via_credit

    # ---- NJ-EITC (as % of federal EITC) ----
    federal_eitc = _round_dollar(_safe_num(taxpayer.get("federal_eitc_amount"), 0))
    line_eitc_nj = _round_dollar(federal_eitc * NJ_EITC_RATE)

    # ---- Build tax lines ----
    line43_tax = precredit_tax

    # Credits bucket (44–49): include NJ-EITC and (if chosen) property-tax credit
    # We’ll park them on synthetic slots and net them into Line 50.
    other_credits = extra_credits + line_eitc_nj

    line50_balance_of_tax = max(0, line43_tax - other_credits)

    # Add-ons (keep zero in MVP)
    line51_use_tax = 0
    line52_interest_penalties = 0
    line53c_srp = 0
    line54_total_tax_due = line50_balance_of_tax + line51_use_tax + line52_interest_penalties + line53c_srp

    # Withholding/payments
    line55_total_w2_withholding = _sum([w.get("state_withheld_box17", 0) for w in w2s])
    line56_to_65_other_payments = 0  # not used in MVP
    line66_total_withholdings_and_payments = line55_total_w2_withholding + line56_to_65_other_payments

    # Amount due vs overpayment
    if line66_total_withholdings_and_payments < line54_total_tax_due:
        line67_amount_you_owe = line54_total_tax_due - line66_total_withholdings_and_payments
        line68_overpayment = 0
    else:
        line67_amount_you_owe = 0
        line68_overpayment = line66_total_withholdings_and_payments - line54_total_tax_due

    # Treat overpayment as refund (skip contributions in MVP)
    line79_balance_after_contributions = line68_overpayment
    line80_refund = line79_balance_after_contributions

    # ---- Build result map ----
    lines = {
        "15":  line15_w2_nj_wages,
        "16a": line16a_interest,
        "17":  line17_dividends,

        "27":  line27_total_income,
        "28c": line28c_exclusions,
        "29":  line29_nj_gross_income,

        "13":  line13_total_exemptions,
        "30":  line30_exemption_amount,
        "38":  line38_total_exemptions_and_deductions,
        "39":  line39_taxable_income,

        "41":  chosen_line41,
        "42":  line42_nj_taxable_income,
        "43":  line43_tax,

        # We don’t assign concrete sub-lines for credits in MVP; they’re netted into Line 50.
        "50":  line50_balance_of_tax,
        "51":  line51_use_tax,
        "52":  line52_interest_penalties,
        "53c": line53c_srp,
        "54":  line54_total_tax_due,

        "55":  line55_total_w2_withholding,
        "66":  line66_total_withholdings_and_payments,

        "67":  line67_amount_you_owe,
        "68":  line68_overpayment,
        "79":  line79_balance_after_contributions,
        "80":  line80_refund,
    }

    summary = {
        "nj_income":    line27_total_income,
        "nj_taxable":   line42_nj_taxable_income,
        "nj_tax":       line43_tax,
        "nj_eitc":      line_eitc_nj,
        "prop_tax_ded": chosen_line41,
        "prop_tax_credit_used": (chosen_line41 == 0 and extra_credits > 0),
        "nj_withheld":  line55_total_w2_withholding,
        "amount_due":   line67_amount_you_owe,
        "refund":       line80_refund,
    }

    return {"lines": lines, "summary": summary}
