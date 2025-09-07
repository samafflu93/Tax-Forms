# wizard.py  — all-in-one interactive wizard for Federal + NJ (Phase 1–2)

import os, sys, json, csv
from pathlib import Path
from datetime import date, datetime

# =====================
# Config
# =====================
TAX_YEAR   = 2024
AGE_CUTOFF = date(TAX_YEAR, 12, 31)

OUT_DIR     = Path("out")
INPUTS_DIR  = OUT_DIR / "user_inputs"
FED_JSON    = OUT_DIR / "out_f1040.json"
NJ_JSON     = OUT_DIR / "out_nj1040.json"
TP_CSV      = INPUTS_DIR / "taxpayer.csv"
W2_CSV      = INPUTS_DIR / "w2s.csv"

# =====================
# Engine imports (FULL by default, stubs if env set)
# =====================
from engines.compute_federal import compute_federal as FED_STUB
from engines.compute_nj import compute_nj as NJ_STUB
FED = FED_STUB
NJ  = NJ_STUB
try:
    if os.getenv("USE_STUB_FED", "0") != "1":
        from engines.compute_federal_full import compute_federal as FED
except Exception:
    pass
try:
    if os.getenv("USE_STUB_NJ", "0") != "1":
        from engines.compute_nj_full import compute_nj as NJ
except Exception:
    pass

# =====================
# Helpers
# =====================
def ask(prompt, default=None, cast=str, allowed=None):
    """Generic prompt with optional default, type-cast and allowed set."""
    while True:
        s = input(f"{prompt}" + (f" [{default}]" if default is not None else "") + ": ").strip()
        if not s and default is not None:
            s = str(default)
        if cast in (int, float):
            try:
                s = cast(s)
            except Exception:
                print(f"Please enter a {cast.__name__}.")
                continue
        if allowed:
            sl = str(s).lower()
            if sl not in allowed:
                print("Please enter one of:", ", ".join(sorted(allowed)))
                continue
        return s

def yn(prompt, default="n"):
    """Yes/no prompt -> True/False."""
    return ask(prompt + " (y/n)", default, str, {"y","n"}).lower() == "y"

def parse_date(s, default_empty=False):
    """Parse date from common formats."""
    s = (s or "").strip()
    if not s and default_empty:
        return ""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    print("Could not parse date. Please use YYYY-MM-DD (or MM/DD/YYYY).")
    return parse_date(input("Re-enter date: "), default_empty)

def calc_age_on(dob, on_date):
    if not isinstance(dob, date): return 0
    years = on_date.year - dob.year
    if (on_date.month, on_date.day) < (dob.month, dob.day):
        years -= 1
    return max(years, 0)

def fnum(v):
    try: 
        return float(v)
    except Exception:
        return 0.0

def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

def normalize_filing_status(s):
    s = (s or "").strip().lower()
    mapping = {
        "single":"single","s":"single",
        "mfj":"married_filing_jointly","married filing jointly":"married_filing_jointly",
        "mfs":"married_filing_separately","married filing separately":"married_filing_separately",
        "hoh":"head_of_household","head of household":"head_of_household",
        "qw":"qualifying_widow(er)","qualifying widow":"qualifying_widow(er)","qualifying widower":"qualifying_widow(er)",
    }
    return mapping.get(s, s)

# =====================
# Collect inputs
# =====================
def gather_personal():
    print("\n=== Basic Personal Info ===")
    first = ask("First name", "Alex")
    last  = ask("Last name",  "Example")
    ssn   = ask("SSN (###-##-####)", "123-45-6789")
    dob   = parse_date(ask("Your date of birth (YYYY-MM-DD)", "1990-01-01"))

    print("\n=== Filing Status ===")
    fs = normalize_filing_status(ask("Filing status (single/mfj/mfs/hoh/qw)", "single"))

    spouse = None
    if fs in ("married_filing_jointly","married_filing_separately"):
        print("\nSpouse info (required for MFJ/MFS):")
        spouse = {
            "spouse_first_name": ask("Spouse first name", "Sam"),
            "spouse_last_name":  ask("Spouse last name",  "Example"),
            "spouse_ssn":        ask("Spouse SSN (###-##-####)", "123-45-6788"),
            "spouse_dob":        parse_date(ask("Spouse DOB (YYYY-MM-DD)", "1990-02-02")),
        }

    tp_over_65 = calc_age_on(dob, AGE_CUTOFF) >= 65
    tp_blind   = yn("Are you blind (IRS definition)?", "n")

    sp_over_65 = False
    sp_blind   = False
    if spouse:
        sp_over_65 = calc_age_on(spouse["spouse_dob"], AGE_CUTOFF) >= 65
        sp_blind   = yn("Is your spouse blind (IRS definition)?", "n")

    print("\n=== Residency & Address (NJ) ===")
    nj_full_year = yn("Are you a full-year New Jersey resident?", "y")
    address = ask("Home address (street, city, state, ZIP)", "123 Main St, Edison, NJ 08817")
    county  = ask("County (NJ)", "Middlesex")

    taxpayer = {
        "first_name": first, "last_name": last, "ssn": ssn,
        "dob": dob.isoformat(),
        "filing_status": fs,
        "tp_over_65": tp_over_65,
        "tp_blind": tp_blind,
        "sp_over_65": sp_over_65,
        "sp_blind": sp_blind,
        "nj_full_year_resident": nj_full_year,
        "address": address,
        "county": county,
    }
    if spouse:
        taxpayer["spouse_first_name"] = spouse["spouse_first_name"]
        taxpayer["spouse_last_name"]  = spouse["spouse_last_name"]
        taxpayer["spouse_ssn"]        = spouse["spouse_ssn"]
        taxpayer["spouse_dob"]        = spouse["spouse_dob"].isoformat()

    return taxpayer

def gather_dependents():
    print("\n=== Dependents (optional) ===")
    deps = []
    if yn("Do you have any dependents to claim?", "n"):
        while True:
            print("\nAdd dependent:")
            d = {
                "first_name": ask("  First name", "Jamie"),
                "last_name":  ask("  Last name", "Example"),
                "ssn":        ask("  SSN (###-##-####)", "111-22-3333"),
                "dob":        parse_date(ask("  DOB (YYYY-MM-DD)", "2015-06-15")),
                "relationship": ask("  Relationship (son/daughter/parent/other)", "son")
            }
            d["dob"] = d["dob"].isoformat()
            deps.append(d)
            if not yn("Add another dependent?", "n"):
                break
    return deps

def gather_w2s():
    print("\n=== W-2 Income ===")
    w2s = []
    while True:
        print("\nEnter a W-2 (or press Enter to stop after employer):")
        employer = ask("Employer name", "")
        if not employer:
            break
        w = {
            "employer": employer,
            "wages_box1":              fnum(ask("  Wages (Box 1)", "20000", float)),
            "fed_withheld_box2":       fnum(ask("  Federal tax withheld (Box 2)", "1500", float)),
            "ss_wages_box3":           fnum(ask("  Social Security wages (Box 3)", "20000", float)),
            "ss_tax_box4":             fnum(ask("  Social Security tax (Box 4)", "1240", float)),
            "medicare_wages_box5":     fnum(ask("  Medicare wages (Box 5)", "20000", float)),
            "medicare_tax_box6":       fnum(ask("  Medicare tax (Box 6)", "290", float)),
            "nj_wages_box16":          fnum(ask("  NJ wages (Box 16)", "20000", float)),
            "nj_withheld_box17":       fnum(ask("  NJ tax withheld (Box 17)", "500", float)),
        }
        w2s.append(w)
    return w2s

def gather_other_income():
    print("\n=== Other Income (optional) ===")
    if not yn("Did you have other income (interest/dividends/unemployment/gig/etc.)?", "n"):
        return {}
    data = {}
    data["interest"]       = fnum(ask("  1099-INT (interest)", "0", float))
    data["dividends"]      = fnum(ask("  1099-DIV (dividends)", "0", float))
    data["unemployment"]   = fnum(ask("  Unemployment income", "0", float))
    data["gig_income"]     = fnum(ask("  1099-NEC/MISC (freelance/gig)", "0", float))
    # You can expand with more types later.
    return data

def gather_adjustments():
    print("\n=== Adjustments & Deductions (basic) ===")
    itemize = yn("Do you want to itemize deductions (Schedule A)? If unsure, choose No (standard).", "n")
    student_loan_interest = fnum(ask("Student loan interest paid", "0", float))
    ira_contrib           = fnum(ask("Traditional IRA contributions", "0", float))
    hsa_contrib           = fnum(ask("HSA contributions", "0", float))
    return {
        "itemize": itemize,
        "student_loan_interest": student_loan_interest,
        "ira_contrib": ira_contrib,
        "hsa_contrib": hsa_contrib,
    }

def gather_nj_housing():
    print("\n=== NJ Property Tax / Rent (optional) ===")
    data = {
        "nj_rent_paid": 0.0,
        "nj_months_at_property": 0,
        "nj_landlord": "",
        "nj_homeowner_tenant": ""
    }
    if not yn("Did you pay NJ property tax or rent in the tax year?", "n"):
        return data
    role = ask("Are you a homeowner, tenant, or both? (homeowner/tenant/both)", "tenant",
               str, {"homeowner","tenant","both"})
    data["nj_homeowner_tenant"] = role
    if role in {"tenant","both"}:
        data["nj_rent_paid"] = fnum(ask("  NJ rent amount paid", "10000", float))
        data["nj_months_at_property"] = int(ask("  # of months lived at this property (0–12)", "12", int))
        data["nj_landlord"] = ask("  Landlord/Property owner name", "ABC Properties")
    # You could add property-tax entry for homeowners later.
    return data

def gather_refund():
    print("\n=== Refund / Payment Preferences ===")
    dd = yn("If you are due a refund, do you want direct deposit?", "y")
    bank = {}
    if dd:
        bank["routing_number"] = ask("Routing number", "021000021")
        bank["account_number"] = ask("Account number", "00014156154")
        bank["account_type"]   = ask("Account type (checking/savings)", "checking",
                                     str, {"checking","savings"})
    return {"direct_deposit": dd, **bank}

# =====================
# Summary helpers
# =====================
def sum_wages(w2s):
    return sum(fnum(w.get("wages_box1", 0)) for w in w2s)

def sum_fed_withheld(w2s):
    return sum(fnum(w.get("fed_withheld_box2", 0)) for w in w2s)

def sum_nj_withheld(w2s):
    return sum(fnum(w.get("nj_withheld_box17", 0)) for w in w2s)

def pretty_summary(title, wages, tax, withheld):
    refund = max(withheld - tax, 0)
    owed   = max(tax - withheld, 0)
    print(f"=== {title} ===")
    print(f"Wages: {wages:,.1f} | Tax: {tax:,.1f} | Withheld: {withheld:,.1f} | Refund: {refund:,.1f} | Owed: {owed:,.1f}")

# =====================
# Main flow
# =====================
def main():
    print("Mode  FED:", "STUB" if os.getenv("USE_STUB_FED","0")=="1" else "FULL")
    print("Mode   NJ:", "STUB" if os.getenv("USE_STUB_NJ","0")=="1" else "FULL")

    # 1) Gather everything
    taxpayer = gather_personal()
    dependents = gather_dependents()
    w2s = gather_w2s()
    other_income = gather_other_income()
    adjustments  = gather_adjustments()
    nj_housing   = gather_nj_housing()
    refund_info  = gather_refund()

    # Flatten optional sections into taxpayer object
    taxpayer["dependents"]       = dependents
    taxpayer["dependents_count"] = len(dependents)           # convenience for engines
    taxpayer.update(other_income)
    taxpayer.update(adjustments)
    taxpayer.update(nj_housing)
    taxpayer.update(refund_info)

    # 2) Save inputs to CSVs for reference
    tp_csv_row = {
        "first_name": taxpayer.get("first_name",""),
        "last_name":  taxpayer.get("last_name",""),
        "ssn":        taxpayer.get("ssn",""),
        "dob":        taxpayer.get("dob",""),
        "filing_status": taxpayer.get("filing_status",""),
        "tp_over_65": taxpayer.get("tp_over_65", False),
        "tp_blind":   taxpayer.get("tp_blind", False),
        "sp_over_65": taxpayer.get("sp_over_65", False),
        "sp_blind":   taxpayer.get("sp_blind", False),
        "spouse_first_name": taxpayer.get("spouse_first_name",""),
        "spouse_last_name":  taxpayer.get("spouse_last_name",""),
        "spouse_ssn":        taxpayer.get("spouse_ssn",""),
        "spouse_dob":        taxpayer.get("spouse_dob",""),
        "dependents_count":  taxpayer.get("dependents_count",0),
        "address": taxpayer.get("address",""),
        "county":  taxpayer.get("county",""),
        "nj_full_year_resident": taxpayer.get("nj_full_year_resident", True),
        # a few extras:
        "interest": taxpayer.get("interest",0),
        "dividends": taxpayer.get("dividends",0),
        "unemployment": taxpayer.get("unemployment",0),
        "gig_income": taxpayer.get("gig_income",0),
        "itemize": taxpayer.get("itemize", False),
        "student_loan_interest": taxpayer.get("student_loan_interest",0),
        "ira_contrib": taxpayer.get("ira_contrib",0),
        "hsa_contrib": taxpayer.get("hsa_contrib",0),
        "nj_rent_paid": taxpayer.get("nj_rent_paid",0),
        "nj_months_at_property": taxpayer.get("nj_months_at_property",0),
        "nj_landlord": taxpayer.get("nj_landlord",""),
        "nj_homeowner_tenant": taxpayer.get("nj_homeowner_tenant",""),
        "direct_deposit": taxpayer.get("direct_deposit", False),
        "routing_number": taxpayer.get("routing_number",""),
        "account_number": taxpayer.get("account_number",""),
        "account_type": taxpayer.get("account_type",""),
    }
    write_csv(TP_CSV, [tp_csv_row])
    write_csv(W2_CSV, w2s)

    # 3) Run engines
    fed_lines = FED(taxpayer, w2s)
    nj_lines  = NJ(taxpayer, w2s)

    # 4) Print concise summaries
    wages_total = sum_wages(w2s)
    fed_withheld = sum_fed_withheld(w2s)
    nj_withheld  = sum_nj_withheld(w2s)

    pretty_summary("Federal Summary", wages_total, fnum(fed_lines.get("16",0)), fed_withheld)
    pretty_summary("NJ Summary",       wages_total, fnum(nj_lines.get("18",0) or nj_lines.get("tax",0)), nj_withheld)

    # 5) Write JSON results
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(FED_JSON, "w", encoding="utf-8") as f:
        json.dump({"inputs": {"taxpayer": taxpayer, "w2s": w2s}, "lines": fed_lines}, f, indent=2)
    with open(NJ_JSON, "w", encoding="utf-8") as f:
        json.dump({"inputs": {"taxpayer": taxpayer, "w2s": w2s}, "lines": nj_lines}, f, indent=2)

    print(f"\nWrote {FED_JSON}")
    print(f"Wrote {NJ_JSON}")
    print(f"Wrote {TP_CSV} and {W2_CSV} (for reference)")

if __name__ == "__main__":
    main()

