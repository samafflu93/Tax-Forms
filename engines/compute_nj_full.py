"""
New Jersey NJ-1040 computation — Phase 2+
Coverage:
- NJ wages (W-2), unemployment, 1099-NEC net, interest, dividends, pensions (1099-R)
- SSA excluded from NJ tax
- Personal + dependent exemptions (simple)
- Property tax / rent support:
   * Homeowner: actual property tax paid
   * Tenant: 18% of rent treated as "property-tax-equivalent"
   * Engine chooses better of: deducting PT-equivalent vs a small flat credit
- NJ EITC = % of federal EITC (configurable)
- Pension exclusion (simplified) if age >= 62 and income under threshold

Outputs (NJ-ish lines):
  "1z" wages, "11" NJ gross income, "12" exemptions (+ maybe PT deduction),
  "15" taxable, "16" tax, "25d" withholding, "34" refund, "37" owed
"""

from typing import Dict, List
import datetime

# You can tune all constants here (or move to a constants module)
NJ_BRACKETS = [
    (20000, 0.0140),
    (35000, 0.0175),
    (40000, 0.0350),
    (75000, 0.05525),
    (500000, 0.0637),
    (10**12, 0.0897),
]

NJ_PERSONAL_EXEMPTION = {
    "single": 1000.0,
    "married_joint": 2000.0,
    "married_separate": 1000.0,
    "head_household": 1000.0,
    "qual_widow": 2000.0,
}
NJ_DEP_EXEMPTION = 1500.0

# Property tax / rent
RENT_TO_PROP_FACTOR = 0.18
PROP_DED_CAP = 15000.0
FLAT_PT_CREDIT = 50.0      # alternative to deduction (nonrefundable)
PT_CREDIT_REFUNDABLE = False

# NJ EITC % of federal
NJ_EITC_RATE = 0.40

# Pension exclusion (very simplified)
PENSION_EXCLUSION_MAX = {
    "single": 75000.0,
    "married_joint": 150000.0,
    "married_separate": 75000.0,
    "head_household": 75000.0,
    "qual_widow": 150000.0,
}
PENSION_EXCLUSION_INCOME_LIMIT = 100000.0  # NJ gross income ceiling to qualify (simplified)
PENSION_EXCLUSION_MIN_AGE = 62

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

def tax_from_brackets(taxable: float) -> float:
    taxable = max(0.0, taxable)
    prev = 0.0
    tax = 0.0
    for cap, rate in NJ_BRACKETS:
        chunk = max(0.0, min(taxable, cap - prev))
        tax += chunk * rate
        taxable -= chunk
        prev = cap
        if taxable <= 0:
            break
    return max(0.0, tax)

# ----------------------------- MAIN -------------------------------------
def compute_nj(taxpayer: Dict, w2s: List[Dict]) -> Dict[str, float]:
    tax_year = 2024  # adjust yearly

    filing_status = taxpayer.get("filing_status", "single")

    # Build NJ gross income (SSA excluded)
    nj_wages = sum(safe_float(w.get("nj_wages", w.get("wages", 0.0))) for w in w2s)
    interest = safe_float(taxpayer.get("interest"))
    dividends = safe_float(taxpayer.get("dividends"))
    unemployment = safe_float(taxpayer.get("unemployment"))
    nec_income = safe_float(taxpayer.get("nec_income"))
    nec_expenses = safe_float(taxpayer.get("nec_expenses"))
    nec_net = max(0.0, nec_income - nec_expenses)
    pensions = safe_float(taxpayer.get("pension_distributions"))
    # SSA benefits (excluded in NJ)
    # ssa_total = safe_float(taxpayer.get("ssa_benefits"))

    nj_gi_pre_exclusions = nj_wages + interest + dividends + unemployment + nec_net + pensions

    # Exemptions
    pers_ex = NJ_PERSONAL_EXEMPTION.get(filing_status, NJ_PERSONAL_EXEMPTION["single"])
    dep_count = len(taxpayer.get("dependents") or [])
    dep_ex = NJ_DEP_EXEMPTION * dep_count
    base_exemptions = pers_ex + dep_ex

    # Pension exclusion (simplified): require age >= 62 and NJ GI under limit
    taxpayer_age = age_on(taxpayer.get("dob",""), tax_year)
    pension_exclusion = 0.0
    if taxpayer_age >= PENSION_EXCLUSION_MIN_AGE and nj_gi_pre_exclusions <= PENSION_EXCLUSION_INCOME_LIMIT:
        pension_exclusion = min(PENSION_EXCLUSION_MAX.get(filing_status, 75000.0), pensions)

    # Property tax / rent → equivalent and choose deduction vs flat credit
    status = (taxpayer.get("housing_status") or "").lower()  # homeowner | tenant | ""
    prop_tax_paid = safe_float(taxpayer.get("property_tax_paid"))
    rent_paid = safe_float(taxpayer.get("rent_paid"))
    prop_equiv = 0.0
    if status == "homeowner":
        prop_equiv = prop_tax_paid
    elif status == "tenant":
        prop_equiv = RENT_TO_PROP_FACTOR * rent_paid

    prop_equiv = min(PROP_DED_CAP, max(0.0, prop_equiv))

    # Path A: deduction of property-tax-equivalent
    taxable_a = max(0.0, nj_gi_pre_exclusions - base_exemptions - pension_exclusion - prop_equiv)
    tax_a = tax_from_brackets(taxable_a)
    credit_a = 0.0  # no PT credit when taking deduction
    net_tax_a = max(0.0, tax_a - credit_a)

    # Path B: no PT deduction; take flat credit
    taxable_b = max(0.0, nj_gi_pre_exclusions - base_exemptions - pension_exclusion)
    tax_b = tax_from_brackets(taxable_b)
    pt_credit = FLAT_PT_CREDIT
    if not PT_CREDIT_REFUNDABLE:
        pt_credit = min(pt_credit, tax_b)
    net_tax_b = max(0.0, tax_b - pt_credit)

    # Choose better (lower tax)
    if net_tax_a <= net_tax_b:
        taxable = taxable_a
        nj_tax = net_tax_a
        used_pt_ded = prop_equiv
        used_pt_credit = 0.0
    else:
        taxable = taxable_b
        nj_tax = net_tax_b
        used_pt_ded = 0.0
        used_pt_credit = pt_credit

    # NJ EITC = % of federal EITC (if present in federal lines, wizard pipeline can pass it later)
    # For now, recompute EITC roughly from federal inputs if helper is available.
    nj_eitc = 0.0
    try:
        from federal_eitc import compute_eitc as _eitc
        earned_income = nj_wages + nec_net
        # Reconstruct a minimal AGI proxy (NJ GI is close enough for thresholding in many cases)
        agi_proxy = nj_gi_pre_exclusions
        investment_income = interest + dividends
        num_kids = dep_count  # crude (assumes all dependents are qualifying children)
        fed_eitc = _eitc(tax_year=tax_year, filing_status=filing_status,
                         earned_income=earned_income, agi=agi_proxy,
                         num_qual_children=num_kids, investment_income=investment_income)
        nj_eitc = NJ_EITC_RATE * fed_eitc
        # Apply as refundable or nonrefundable? NJ EITC is refundable → subtract from liability after brackets
        refund_component = nj_eitc
    except Exception:
        refund_component = 0.0
        nj_eitc = 0.0

    # Withholding
    nj_withheld = sum(safe_float(w.get("nj_withheld")) for w in w2s)

    # Settlement: NJ EITC is refundable (add to refund after liability & withholding)
    refund = max(0.0, nj_withheld - nj_tax) + refund_component
    owed = max(0.0, nj_tax - nj_withheld)  # NJ EITC won't increase tax owed

    return {
        "1z": nj_wages,
        "2b": interest,
        "3a": dividends,
        "7": unemployment,
        "8": nec_net,
        "11": nj_gi_pre_exclusions,
        "12": base_exemptions + pension_exclusion + used_pt_ded,  # what reduced taxable income
        "15": taxable,
        "16": nj_tax,
        "25d": nj_withheld,
        "34": refund,
        "37": owed,
        # debug & transparency
        "_pt_equiv": prop_equiv,
        "_pt_ded_used": used_pt_ded,
        "_pt_credit_used": used_pt_credit,
        "_pension_exclusion": pension_exclusion,
        "_nj_eitc": nj_eitc,
    }

