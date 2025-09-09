"""
Federal 1040 computation engine — Phase 2+
Coverage:
- W-2 wages (multiple)
- Other income: interest, dividends, unemployment, 1099-NEC (net), Social Security (SSA-1099), pensions/IRA (1099-R, no basis yet)
- Above-the-line adjustments (simple): student loan interest (cap), IRA, HSA
- Standard deduction by filing status
- 2024-ish bracket model by filing status (approx; tune constants as needed)
- Child Tax Credit (nonrefundable) + Additional CTC (refundable, 15% rule)
- EITC: uses federal_eitc.py if present; otherwise falls back to 0
- Refund/amount owed using W-2 federal withholding

Outputs (key 1040-like lines):
  "1z" wages, "11" AGI, "12" standard deduction, "15" taxable income,
  "16" tax before nonrefundable credits,
  "19" nonrefundable CTC used, "25d" withholding, "27" refundable credits (ACTC),
  "34" refund, "37" amount owed
"""

from typing import Dict, List
import datetime

# ----------------------- TRY OPTIONAL EITC HELPER -----------------------
EITC_AVAILABLE = False
def _compute_eitc_fallback(**kwargs) -> float:
    # If federal_eitc module isn't present, return 0 (safe default).
    return 0.0

try:
    from federal_eitc import compute_eitc as _eitc
    EITC_AVAILABLE = True
except Exception:
    _eitc = _compute_eitc_fallback

# ----------------------------- CONSTANTS --------------------------------
TAX_YEAR = 2024  # adjust yearly (you can pass this in later)

STD_DED = {
    "single": 14600,
    "married_joint": 29200,
    "married_separate": 14600,
    "head_household": 21900,
    "qual_widow": 29200,
}

# 2024-ish brackets (approx). Each status -> list of (cap, rate) cumulative caps.
BRACKETS = {
    "single": [
        (11600, 0.10), (47150, 0.12), (100525, 0.22), (191950, 0.24),
        (243725, 0.32), (609350, 0.35), (10**12, 0.37),
    ],
    "married_joint": [
        (23200, 0.10), (94300, 0.12), (201050, 0.22), (383900, 0.24),
        (487450, 0.32), (731200, 0.35), (10**12, 0.37),
    ],
    "married_separate": [
        (11600, 0.10), (47150, 0.12), (100525, 0.22), (191950, 0.24),
        (243725, 0.32), (365600, 0.35), (10**12, 0.37),
    ],
    "head_household": [
        (16550, 0.10), (63100, 0.12), (100500, 0.22), (191950, 0.24),
        (243700, 0.32), (609350, 0.35), (10**12, 0.37),
    ],
    "qual_widow": [
        (23200, 0.10), (94300, 0.12), (201050, 0.22), (383900, 0.24),
        (487450, 0.32), (731200, 0.35), (10**12, 0.37),
    ],
}

# CTC / ACTC assumptions (tune to the year)
CTC_PER_CHILD = 2000.0
ACTC_REFUNDABLE_LIMIT_PER_CHILD = 1600.0
ACTC_EARNED_INCOME_FLOOR = 2500.0
ACTC_RATE = 0.15

# CTC phaseout thresholds (AGI)
CTC_PHASEOUT_START = {
    "single": 200000,
    "head_household": 200000,
    "married_joint": 400000,
    "married_separate": 200000,
    "qual_widow": 400000,
}
CTC_PHASEOUT_STEP = 50.0  # $50 per $1,000 over threshold

# Social Security taxation thresholds (base/additional) by status
SSA_THRESHOLDS = {
    # (base, additional) provisional income thresholds
    "single": (25000.0, 34000.0),
    "head_household": (25000.0, 34000.0),
    "qual_widow": (32000.0, 44000.0),      # widow generally follows MFJ thresholds; using (32k,44k) is safer
    "married_joint": (32000.0, 44000.0),
    "married_separate": (0.0, 0.0),         # if lived with spouse any time in year, essentially 0 thresholds
}

# ----------------------------- HELPERS ----------------------------------
def safe_float(x, default=0.0):
    try:
        if x is None: return float(default)
        if isinstance(x, (int, float)): return float(x)
        s = str(x).strip()
        return float(s) if s else float(default)
    except Exception:
        return float(default)

def age_on(dob: str, year: int) -> int:
    if not dob: return 99
    try:
        y, m, d = [int(p) for p in dob.split("-")]
        born = datetime.date(y, m, d)
        end = datetime.date(year, 12, 31)
        return end.year - born.year - ((end.month, end.day) < (born.month, born.day))
    except Exception:
        return 99

def tax_from_brackets(taxable: float, filing_status: str) -> float:
    slabs = BRACKETS.get(filing_status, BRACKETS["single"])
    prev_cap = 0.0
    remaining = max(0.0, taxable)
    tax = 0.0
    for cap, rate in slabs:
        chunk = max(0.0, min(remaining, cap - prev_cap))
        tax += chunk * rate
        remaining -= chunk
        prev_cap = cap
        if remaining <= 0:
            break
    return max(0.0, tax)

def taxable_ssa(agi_excl_ssa: float, ssa_total: float, filing_status: str) -> float:
    """Compute taxable portion of Social Security using simplified IRS method."""
    if ssa_total <= 0:
        return 0.0
    base, addl = SSA_THRESHOLDS.get(filing_status, SSA_THRESHOLDS["single"])
    provisional = agi_excl_ssa + 0.5 * ssa_total

    if filing_status == "married_separate":
        # Lived with spouse → effectively 85% taxable (conservative)
        return min(0.85 * ssa_total, agi_excl_ssa + 0.5 * ssa_total)

    if provisional <= base:
        return 0.0
    elif provisional <= addl:
        return min(0.5 * ssa_total, 0.5 * (provisional - base))
    else:
        # Over the additional threshold
        # Taxable = lesser of 85% of SSA or 85%*(provisional-addl) + min(50% SSA, 50%*(addl-base))
        part1 = 0.85 * (provisional - addl)
        part2 = min(0.5 * ssa_total, 0.5 * (addl - base))
        return min(0.85 * ssa_total, part1 + part2)

# ----------------------------- MAIN -------------------------------------
def compute_federal(taxpayer: Dict, w2s: List[Dict]) -> Dict[str, float]:
    filing_status = taxpayer.get("filing_status", "single")
    std_ded = STD_DED.get(filing_status, STD_DED["single"])

    # Earned income
    wages = sum(safe_float(w.get("wages")) for w in w2s)
    nec_income = safe_float(taxpayer.get("nec_income"))
    nec_expenses = safe_float(taxpayer.get("nec_expenses"))
    nec_net = max(0.0, nec_income - nec_expenses)
    earned_income = wages + nec_net

    # Other income
    interest = safe_float(taxpayer.get("interest"))
    dividends = safe_float(taxpayer.get("dividends"))
    unemployment = safe_float(taxpayer.get("unemployment"))
    ssa_total = safe_float(taxpayer.get("ssa_benefits"))  # wizard may not ask yet; safe default 0
    pensions = safe_float(taxpayer.get("pension_distributions"))  # 1099-R simple include

    # Above-the-line adjustments (simple)
    stu_loan = min(2500.0, safe_float(taxpayer.get("student_loan_interest")))
    ira_contrib = safe_float(taxpayer.get("ira_contrib"))
    hsa_contrib = safe_float(taxpayer.get("hsa_contrib"))
    above_line = stu_loan + ira_contrib + hsa_contrib

    # Build AGI
    agi_excl_ssa = max(0.0, earned_income + interest + dividends + unemployment + pensions - above_line)
    ssa_tax = taxable_ssa(agi_excl_ssa, ssa_total, filing_status)
    agi = agi_excl_ssa + ssa_tax

    # Taxable income
    taxable_income = max(0.0, agi - std_ded)

    # Base tax
    tax_before_credits = tax_from_brackets(taxable_income, filing_status)

    # Dependents and CTC
    deps = taxpayer.get("dependents") or []
    qualifying_children = 0
    for d in deps:
        if str(d.get("relationship","child")).lower() == "child" and age_on(str(d.get("dob","")), TAX_YEAR) < 17:
            qualifying_children += 1

    # CTC phaseout
    ctc_total_cap = CTC_PER_CHILD * qualifying_children
    ctc_phase_start = CTC_PHASEOUT_START.get(filing_status, CTC_PHASEOUT_START["single"])
    over = max(0.0, agi - ctc_phase_start)
    ctc_phaseout = (int(over // 1000.0)) * CTC_PHASEOUT_STEP
    ctc_after_phase = max(0.0, ctc_total_cap - ctc_phaseout)

    # Nonrefundable CTC used
    nonref_ctc_used = min(ctc_after_phase, tax_before_credits)
    tax_after_nonref = max(0.0, tax_before_credits - nonref_ctc_used)

    # Refundable ACTC
    earned_for_actc = earned_income  # wages + nec_net
    actc_income_base = max(0.0, earned_for_actc - ACTC_EARNED_INCOME_FLOOR)
    actc_earned_amount = ACTC_RATE * actc_income_base
    actc_per_child_cap = ACTC_REFUNDABLE_LIMIT_PER_CHILD * qualifying_children
    ctc_remaining = max(0.0, ctc_after_phase - nonref_ctc_used)
    refundable_ctc = min(actc_earned_amount, actc_per_child_cap, ctc_remaining)

    # EITC (if helper available)
    # You can extend the wizard to ask "lived-in-US > 6 months?" etc. For now, basic calc.
    investment_income = interest + dividends  # simple proxy for investment-income cap
    eitc = _eitc(
        tax_year=TAX_YEAR,
        filing_status=filing_status,
        earned_income=earned_income,
        agi=agi,
        num_qual_children=qualifying_children,
        investment_income=investment_income
    ) if EITC_AVAILABLE else 0.0

    # Withholding
    withheld = sum(safe_float(w.get("federal_withheld")) for w in w2s)

    # Final settlement
    refundable_credits = refundable_ctc + eitc
    net_tax = tax_after_nonref
    refund = max(0.0, withheld + refundable_credits - net_tax)
    owed = max(0.0, net_tax - (withheld + refundable_credits))

    return {
        "1z": wages,
        "2b": interest,
        "3a": dividends,
        "5b": ssa_tax,            # taxable Social Security (for reference)
        "7": unemployment,
        "8": nec_net,             # Schedule 1-ish placeholder
        "11": agi,
        "12": std_ded,
        "15": taxable_income,
        "16": tax_before_credits,
        "19": nonref_ctc_used,
        "25d": withheld,
        "27": refundable_ctc + eitc,   # refundable bucket (ACTC + EITC)
        "34": refund,
        "37": owed,
        # Debug helpers
        "_ref_eitc_used": eitc,
        "_ref_refundable_ctc": refundable_ctc,
        "_ref_ctc_after_phase": ctc_after_phase,
    }

