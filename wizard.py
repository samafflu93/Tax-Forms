#!/usr/bin/env python3
# US + NJ Tax Wizard (Phase 2+)
# - Friendly prompts (with form box hints)
# - Money parsing accepts $, commas, and (negative) parentheses
# - Saves per-digit arrays for SSNs, ZIPs, DOBs, and *all* money fields
# - Adds per-digit arrays for every numeric engine output line (for PDF mapping)

import os, csv, json, re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

# ------------------------- engine imports -------------------------
USE_STUB_FED = os.getenv("USE_STUB_FED", "0") == "1"
USE_STUB_NJ  = os.getenv("USE_STUB_NJ", "0") == "1"

if USE_STUB_FED:
    from engines.compute_federal import compute_federal as FED
else:
    from engines.compute_federal_full import compute_federal as FED

if USE_STUB_NJ:
    from engines.compute_nj import compute_nj as NJ
else:
    from engines.compute_nj_full import compute_nj as NJ

# ------------------------- output paths ---------------------------
OUT_DIR = Path("out")
(OUT_DIR / "user_inputs").mkdir(parents=True, exist_ok=True)
SESS_DIR = Path("sessions")
SESS_DIR.mkdir(parents=True, exist_ok=True)

# ------------------------- helpers -------------------------------
_DIGITS_RE = re.compile(r"\d")

def fnum(raw: Any, default: float = 0.0) -> float:
    """Flexible money parser: strips $, commas; supports (1,234.56) as negative."""
    try:
        if raw is None:
            return default
        if isinstance(raw, (int, float)):
            return float(raw)
        s = str(raw).strip()
        if s == "":
            return default
        neg = s.startswith("(") and s.endswith(")")
        s = s.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
        v = float(s) if s else 0.0
        return -v if neg else v
    except Exception:
        return default

def digits_from_string(raw: Any) -> List[str]:
    """Return only digits, split into single-character strings."""
    if raw is None:
        return []
    return _DIGITS_RE.findall(str(raw))

def digits_from_money(amount: Any) -> List[str]:
    """Convert numeric amount to whole-dollar digit array (for boxed fields)."""
    try:
        n = int(round(float(amount)))
        return list(str(n))
    except Exception:
        return []

def parse_dob(raw: str) -> Tuple[str, List[str]]:
    """
    Accepts 'YYYY-MM-DD', 'MM/DD/YYYY', 'MM-DD-YYYY', 'YYYY/MM/DD'.
    Returns ('YYYY-MM-DD', ['Y','Y','Y','Y','M','M','D','D']) or ("", []) if invalid.
    """
    s = (raw or "").strip()
    if not s:
        return "", []
    s2 = s.replace(".", "/").replace("-", "/")
    parts = s2.split("/")
    try:
        if len(parts) == 3:
            # Try MM/DD/YYYY if last is 4-digit year
            if len(parts[2]) == 4:
                m, d, y = int(parts[0]), int(parts[1]), int(parts[2])
            else:
                y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            dt = datetime(year=y, month=m, day=d)
        else:
            dt = datetime.strptime(s, "%Y-%m-%d")
        iso = dt.strftime("%Y-%m-%d")
        return iso, list(dt.strftime("%Y%m%d"))
    except Exception:
        return "", []

def money_to_dollars_cents(amount: Any) -> Tuple[List[str], List[str]]:
    """1234.56 -> (['1','2','3','4'], ['5','6']) with rounding; negatives handled by abs()."""
    try:
        val = float(amount)
    except Exception:
        return [], []
    val = abs(val)
    s = f"{val:.2f}"
    d, c = s.split(".")
    return list(d), list(c)

def add_digit_arrays_to_lines(lines: Dict[str, Any]) -> Dict[str, Any]:
    """
    For each numeric value in engine output, add:
      <key>_digits       (dollars array)
      <key>_cents_digits (cents array)
    """
    out = dict(lines)
    for k, v in list(lines.items()):
        try:
            float(v)
            is_num = True
        except Exception:
            is_num = False
        if is_num:
            d, c = money_to_dollars_cents(v)
            out[f"{k}_digits"] = d
            out[f"{k}_cents_digits"] = c
    return out

def yn(prompt: str, default: bool = False) -> bool:
    d = "y" if default else "n"
    ans = input(f"{prompt} (y/n) [{d}]: ").strip().lower()
    if ans == "":
        return default
    return ans.startswith("y")

def ask(prompt: str, default: str = "") -> str:
    s = input(f"{prompt} [{default}]: ").strip()
    return s if s != "" else default

def ask_money(prompt: str, default: float = 0.0) -> float:
    raw = input(f"{prompt} [{default}]: ").strip()
    return fnum(raw, default) if raw != "" else default

def choose_from(title: str, options: List[Tuple[str, str]], default_key: str) -> str:
    print("\n" + title)
    for i, (k, label) in enumerate(options, start=1):
        dmark = " (default)" if k == default_key else ""
        print(f"  {i}) {label}{dmark}")
    valid = {k.lower(): k for k, _ in options}
    while True:
        raw = input(f"Choose 1–{len(options)} or keyword [{default_key}]: ").strip()
        if raw == "":
            return default_key
        if raw.isdigit():
            i = int(raw)
            if 1 <= i <= len(options):
                return options[i-1][0]
        low = raw.lower()
        if low in valid:
            return valid[low]
        print("  Please enter a valid number/keyword.")

# ------------------------- interview sections ---------------------
FILING_OPTS = [
    ("single", "Single"),
    ("married_joint", "Married filing jointly"),
    ("married_separate", "Married filing separately"),
    ("head_household", "Head of household"),
    ("qual_widow", "Qualifying widow(er)"),
]

def gather_personal() -> Dict[str, Any]:
    print("\n=== Personal Info ===")
    first = ask("First name")
    last  = ask("Last name")
    filing_status = choose_from("Filing status:", FILING_OPTS, "single")

    ssn_raw = ask("SSN (###-##-####)")
    ssn_digits = digits_from_string(ssn_raw)

    dob_raw = ask("Date of birth (MM/DD/YYYY or YYYY-MM-DD)")
    dob_iso, dob_digits = parse_dob(dob_raw)

    zip_raw = ask("ZIP code")
    zip_digits = digits_from_string(zip_raw)

    email = ask("Email (optional)", "")
    addr  = ask("Street address", "")
    city  = ask("City", "")
    state = ask("State", "NJ")
    county = ask("NJ County (optional)", "")

    nj_full_year = yn("Are you a full-year New Jersey resident?", True)

    return {
        "first_name": first,
        "last_name": last,
        "filing_status": filing_status,
        "ssn": ssn_raw,
        "ssn_digits": ssn_digits,
        "dob": dob_iso,
        "dob_digits": dob_digits,
        "zip": zip_raw,
        "zip_digits": zip_digits,
        "email": email,
        "address": addr,
        "city": city,
        "state": state,
        "county": county,
        "nj_full_year_resident": "y" if nj_full_year else "n",
    }

def gather_dependents() -> List[Dict[str, Any]]:
    print("\n=== Dependents (optional) ===")
    deps: List[Dict[str, Any]] = []
    if yn("Do you have dependents to claim?", False):
        while True:
            name = ask("  Dependent full name", "")
            if name == "":
                break
            dssn = ask("  Dependent SSN (###-##-####)", "")
            dssn_digits = digits_from_string(dssn)
            ddob_raw = ask("  Dependent DOB (MM/DD/YYYY or YYYY-MM-DD)", "")
            ddob_iso, ddob_digits = parse_dob(ddob_raw)
            relation = ask("  Relationship (child/parent/other)", "child")
            deps.append({
                "name": name,
                "ssn": dssn,
                "ssn_digits": dssn_digits,
                "dob": ddob_iso,
                "dob_digits": ddob_digits,
                "relationship": relation
            })
            if not yn("  Add another dependent?", False):
                break
    return deps

def gather_w2s() -> List[Dict[str, Any]]:
    print("\n=== W-2 Income ===")
    w2s: List[Dict[str, Any]] = []
    if not yn("Do you have any W-2s?", True):
        return w2s
    while True:
        employer = ask("  Employer name")
        wages = ask_money("  Wages (Box 1)", 0.0)
        fed_wh = ask_money("  Federal income tax withheld (Box 2)", 0.0)
        ss_w = ask_money("  Social Security wages (Box 3) [optional]", 0.0)
        ss_t = ask_money("  Social Security tax withheld (Box 4) [optional]", 0.0)
        med_w = ask_money("  Medicare wages (Box 5) [optional]", 0.0)
        med_t = ask_money("  Medicare tax withheld (Box 6) [optional]", 0.0)
        nj_w = ask_money("  NJ wages (Box 16)", 0.0)
        nj_wh = ask_money("  NJ income tax withheld (Box 17)", 0.0)

        w2 = {
            "employer": employer,

            "wages_box1": wages,
            "wages_box1_digits": digits_from_money(wages),

            "fed_withheld_box2": fed_wh,
            "fed_withheld_box2_digits": digits_from_money(fed_wh),

            "ss_wages_box3": ss_w,
            "ss_wages_box3_digits": digits_from_money(ss_w),

            "ss_tax_box4": ss_t,
            "ss_tax_box4_digits": digits_from_money(ss_t),

            "medicare_wages_box5": med_w,
            "medicare_wages_box5_digits": digits_from_money(med_w),

            "medicare_tax_box6": med_t,
            "medicare_tax_box6_digits": digits_from_money(med_t),

            "nj_wages_box16": nj_w,
            "nj_wages_box16_digits": digits_from_money(nj_w),

            "nj_withheld_box17": nj_wh,
            "nj_withheld_box17_digits": digits_from_money(nj_wh),
        }
        w2s.append(w2)

        if not yn("  Add another W-2?", False):
            break
    return w2s

def gather_other_income() -> Dict[str, Any]:
    print("\n=== Other Income (optional) ===")
    out: Dict[str, Any] = {}

    if yn("Any bank interest (Form 1099-INT)?", False):
        amt = ask_money("  1099-INT interest (Box 1)", 0.0)
        out["bank_interest"] = amt
        out["bank_interest_digits"] = digits_from_money(amt)
    else:
        out["bank_interest"] = 0.0
        out["bank_interest_digits"] = []

    if yn("Any dividends (Form 1099-DIV)?", False):
        ord_amt = ask_money("  1099-DIV ordinary dividends (Box 1a)", 0.0)
        qual_amt = ask_money("  1099-DIV qualified dividends (Box 1b) [optional]", 0.0)
        capg_amt = ask_money("  1099-DIV capital gain distributions (Box 2a) [optional]", 0.0)
        out["dividends_ordinary"] = ord_amt
        out["dividends_ordinary_digits"] = digits_from_money(ord_amt)
        out["dividends_qualified"] = qual_amt
        out["dividends_qualified_digits"] = digits_from_money(qual_amt)
        out["capital_gains_dist"] = capg_amt
        out["capital_gains_dist_digits"] = digits_from_money(capg_amt)
    else:
        out["dividends_ordinary"] = 0.0
        out["dividends_ordinary_digits"] = []
        out["dividends_qualified"] = 0.0
        out["dividends_qualified_digits"] = []
        out["capital_gains_dist"] = 0.0
        out["capital_gains_dist_digits"] = []

    if yn("Any unemployment income (Form 1099-G)?", False):
        u = ask_money("  1099-G unemployment compensation (Box 1)", 0.0)
        out["unemployment"] = u
        out["unemployment_digits"] = digits_from_money(u)
    else:
        out["unemployment"] = 0.0
        out["unemployment_digits"] = []

    if yn("Any 1099-NEC self-employment income?", False):
        nec_gross = ask_money("  1099-NEC gross income (Box 1)", 0.0)
        nec_exp   = ask_money("  1099-NEC expenses (if any)", 0.0)
        nec_net   = max(nec_gross - nec_exp, 0.0)
        out["nec_gross"] = nec_gross
        out["nec_gross_digits"] = digits_from_money(nec_gross)
        out["nec_expenses"] = nec_exp
        out["nec_expenses_digits"] = digits_from_money(nec_exp)
        out["nec_net"] = nec_net
        out["nec_net_digits"] = digits_from_money(nec_net)
    else:
        out["nec_gross"] = 0.0; out["nec_gross_digits"] = []
        out["nec_expenses"] = 0.0; out["nec_expenses_digits"] = []
        out["nec_net"] = 0.0; out["nec_net_digits"] = []

    if yn("Any Social Security benefits (SSA-1099)?", False):
        ss = ask_money("  SSA-1099 total benefits (Box 5)", 0.0)
        out["ss_benefits_total"] = ss
        out["ss_benefits_total_digits"] = digits_from_money(ss)
    else:
        out["ss_benefits_total"] = 0.0
        out["ss_benefits_total_digits"] = []

    if yn("Any pension/IRA distributions (Form 1099-R)?", False):
        gross = ask_money("  1099-R gross distribution (Box 1)", 0.0)
        taxable = ask_money("  1099-R taxable amount (Box 2a) [enter same as Box 1 if unknown]", gross)
        out["pension_gross"] = gross
        out["pension_gross_digits"] = digits_from_money(gross)
        out["pension_taxable"] = taxable
        out["pension_taxable_digits"] = digits_from_money(taxable)
    else:
        out["pension_gross"] = 0.0; out["pension_gross_digits"] = []
        out["pension_taxable"] = 0.0; out["pension_taxable_digits"] = []

    return out

def gather_adjustments() -> Dict[str, Any]:
    print("\n=== Adjustments & Deductions (basic) ===")
    itemize = yn("Do you want to itemize deductions (Schedule A)? If unsure, select No (standard).", False)
    stud_loan = ask_money("Student loan interest (Form 1098-E)", 0.0)
    ira_contrib = ask_money("Traditional IRA contributions", 0.0)
    hsa_contrib = ask_money("HSA contributions", 0.0)

    return {
        "itemize": "y" if itemize else "n",
        "student_loan_interest": stud_loan,
        "student_loan_interest_digits": digits_from_money(stud_loan),
        "ira_contrib": ira_contrib,
        "ira_contrib_digits": digits_from_money(ira_contrib),
        "hsa_contrib": hsa_contrib,
        "hsa_contrib_digits": digits_from_money(hsa_contrib),
    }

def gather_nj_housing() -> Dict[str, Any]:
    print("\n=== NJ Property Tax / Rent (optional) ===")
    out = {
        "housing_status": "",
        "property_tax_paid": 0.0,
        "property_tax_paid_digits": [],
        "rent_paid": 0.0,
        "rent_paid_digits": [],
        "housing_months": 0,
        "landlord": "",
    }
    if yn("Did you pay NJ property tax or rent in the year?", False):
        status = choose_from(
            "Are you a homeowner, tenant, or both?",
            [("homeowner","Homeowner"),("tenant","Tenant"),("both","Both")],
            "tenant"
        )
        out["housing_status"] = status
        if status in ("homeowner","both"):
            pt = ask_money("  NJ property tax paid (total)", 0.0)
            out["property_tax_paid"] = pt
            out["property_tax_paid_digits"] = digits_from_money(pt)
        if status in ("tenant","both"):
            r = ask_money("  NJ rent paid (total)", 0.0)
            out["rent_paid"] = r
            out["rent_paid_digits"] = digits_from_money(r)
        out["housing_months"] = int(fnum(ask("  # months lived at this property (0–12)", "12")))
        out["landlord"] = ask("  Landlord/Property owner name [optional]", "")
    return out

def gather_refund_info() -> Dict[str, Any]:
    print("\n=== Refund / Payment Preferences ===")
    direct = yn("If you’re due a refund, do you want direct deposit?", True)
    if direct:
        routing = ask("Routing number")
        account = ask("Account number")
        acct_type = choose_from("Account type:", [("checking","Checking"),("savings","Savings")], "checking")
        return {
            "want_direct_deposit": "y",
            "bank_routing": routing,
            "bank_routing_digits": digits_from_string(routing),
            "bank_account": account,
            "bank_account_digits": digits_from_string(account),
            "bank_account_type": acct_type,
        }
    else:
        return {
            "want_direct_deposit": "n",
            "bank_routing": "",
            "bank_routing_digits": [],
            "bank_account": "",
            "bank_account_digits": [],
            "bank_account_type": "",
        }

# ------------------------- csv writers (optional) ------------------
def save_taxpayer_csv(taxpayer: Dict[str, Any], dependents: List[Dict[str, Any]]):
    path = OUT_DIR / "user_inputs" / "taxpayer.csv"
    row = dict(taxpayer)
    row["dependents_count"] = len(dependents)
    # remove big arrays to keep CSV compact
    for k in list(row.keys()):
        if k.endswith("_digits"):
            row.pop(k, None)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        w.writeheader()
        w.writerow(row)

def save_w2s_csv(w2s: List[Dict[str, Any]]):
    path = OUT_DIR / "user_inputs" / "w2s.csv"
    if not w2s:
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["employer","wages_box1","fed_withheld_box2","nj_wages_box16","nj_withheld_box17"])
            w.writeheader()
        return
    # strip digits arrays for csv
    clean_rows = []
    for r in w2s:
        rr = {k: v for k, v in r.items() if not k.endswith("_digits")}
        clean_rows.append(rr)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(clean_rows[0].keys()))
        w.writeheader()
        for rr in clean_rows:
            w.writerow(rr)

# ------------------------- main -----------------------------------
def main():
    print("US + NJ Tax Wizard —", datetime.now().date().isoformat())
    print("(Educational tool — not official tax advice.)")

    taxpayer = gather_personal()
    dependents = gather_dependents()
    taxpayer["dependents_list"] = dependents
    taxpayer["dependents"] = len(dependents)

    w2s = gather_w2s()
    other = gather_other_income()
    adjustments = gather_adjustments()
    nj_housing = gather_nj_housing()
    bank = gather_refund_info()

    # save a raw snapshot of all inputs (with digits arrays) for mapping later
    session_blob = {
        "taxpayer": taxpayer,
        "dependents": dependents,
        "w2s": w2s,
        "other_income": other,
        "adjustments": adjustments,
        "nj_housing": nj_housing,
        "bank": bank,
    }
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with (SESS_DIR / f"session_{stamp}.json").open("w", encoding="utf-8") as f:
        json.dump(session_blob, f, indent=2)

    # Merge relevant blocks into taxpayer for engines
    tp_for_engine = dict(taxpayer)
    tp_for_engine.update(other)
    tp_for_engine.update(adjustments)
    tp_for_engine["nj_housing"] = nj_housing
    tp_for_engine["bank"] = bank

    # compute
    fed_raw = FED(tp_for_engine, w2s)
    nj_raw  = NJ(tp_for_engine, w2s)

    # add per-line digit arrays for mapping
    fed_lines = add_digit_arrays_to_lines(fed_raw)
    nj_lines  = add_digit_arrays_to_lines(nj_raw)

    # write combined outputs
    with (OUT_DIR / "out_f1040.json").open("w", encoding="utf-8") as f:
        json.dump({"inputs": {"taxpayer": taxpayer, "w2s": w2s}, "lines": fed_lines}, f, indent=2)
    with (OUT_DIR / "out_nj1040.json").open("w", encoding="utf-8") as f:
        json.dump({"inputs": {"taxpayer": taxpayer, "w2s": w2s}, "lines": nj_lines}, f, indent=2)

    # also write lighter CSVs for quick review
    save_taxpayer_csv(taxpayer, dependents)
    save_w2s_csv(w2s)

    # console summaries
    total_wages = sum(float(w.get("wages_box1", 0) or 0) for w in w2s)
    fed_wh = sum(float(w.get("fed_withheld_box2", 0) or 0) for w in w2s)
    nj_wh  = sum(float(w.get("nj_withheld_box17", 0) or 0) for w in w2s)

    print("\n=== Federal Summary ===")
    print(f"Wages: {total_wages:,.2f} | Withheld: {fed_wh:,.2f} | Refund: {fed_lines.get('34',0):,.2f} | Owed: {fed_lines.get('37',0):,.2f}")
    print("Wrote", OUT_DIR / "out_f1040.json")

    print("\n=== NJ Summary ===")
    print(f"Wages: {total_wages:,.2f} | Withheld: {nj_wh:,.2f} | Refund: {nj_lines.get('34',0):,.2f} | Owed: {nj_lines.get('37',0):,.2f}")
    print("Wrote", OUT_DIR / "out_nj1040.json")

if __name__ == "__main__":
    main()

