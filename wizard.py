# wizard.py
# Simple terminal wizard for Federal 1040 + NJ-1040 (Phase 1–2)
# No external packages needed.

import os, json, csv
from pathlib import Path
from datetime import date, datetime

# ---- Tax Year (edit if needed) ----
TAX_YEAR = 2024
AGE_CUTOFF = date(TAX_YEAR, 12, 31)  # age is computed as of Dec 31 of tax year

# ---- Import engines with safe toggles (default = FULL if present) ----
from engines.compute_federal import compute_federal as FED_STUB
from engines.compute_nj import compute_nj as NJ_STUB
FED = FED_STUB
NJ  = NJ_STUB
try:
    if os.getenv("USE_STUB_FED", "0") != "1":
        from engines.compute_federal_full import compute_federal as FED  # noqa: F401
except Exception:
    pass
try:
    if os.getenv("USE_STUB_NJ", "0") != "1":
        from engines.compute_nj_full import compute_nj as NJ  # noqa: F401
except Exception:
    pass

# ----------------- helpers -----------------
def ask(prompt, default=None, cast=str, allowed=None):
    """Basic input helper with defaults and validation."""
    while True:
        s = input(f"{prompt}" + (f" [{default}]" if default is not None else "") + ": ").strip()
        if s == "" and default is not None:
            s = default
        if cast in (int, float):
            try:
                s = cast(s)
            except Exception:
                print(f"Please enter a {cast.__name__}.")
                continue
        if allowed and allowed != "ANY":
            if str(s).lower() not in allowed:
                print("Please enter one of:", ", ".join(sorted(allowed)))
                continue
        return s

def yn(prompt, default="n"):
    return ask(prompt + " (y/n)", default, cast=str, allowed={"y","n"}).lower() == "y"

def normalize_filing_status(s):
    s = (s or "").strip().lower()
    m = {
        "single":"single","s":"single",
        "mfj":"married_filing_jointly","married filing jointly":"married_filing_jointly",
        "mfs":"married_filing_separately","married filing separately":"married_filing_separately",
        "hoh":"head_of_household","head of household":"head_of_household",
        "qw":"qualifying_widow(er)","qualifying widow":"qualifying_widow(er)","qualifying widower":"qualifying_widow(er)",
    }
    return m.get(s, s)

def parse_date(s, default_empty=True):
    s = (s or "").strip()
    if not s and default_empty:
        return ""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    print("Could not parse date. Please use YYYY-MM-DD (e.g., 1990-04-12).")
    return parse_date(input("Re-enter date: "), default_empty)

def calc_age_on(dob, on_date):
    if not isinstance(dob, date):
        return 0
    years = on_date.year - dob.year
    if (on_date.month, on_date.day) < (dob.month, dob.day):
        years -= 1
    return max(years, 0)

def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

def fnum(v):
    try:
        return float(v)
    except Exception:
        return 0.0
# ----------------- end helpers -----------------


def gather_user_input():
    print("\n=== Taxpayer Info ===")
    first = ask("First name", "Alex")
    last  = ask("Last name", "Example")
    ssn   = ask("SSN (###-##-####)", "123-45-6789")
    dob   = parse_date(ask(f"Your date of birth (YYYY-MM-DD)", "1990-01-01"))

    print("\n=== Address (for 1040 header & NJ) ===")
    addr1 = ask("Street address", "123 Main St")
    addr2 = ask("Apt/Suite (optional)", "")
    city  = ask("City", "Edison")
    state = ask("State (2-letter)", "NJ")
    zipc  = ask("ZIP code", "08817")
    email = ask("Email (optional)", "", cast=str)

    print("\n=== Filing Questions ===")
    fs = normalize_filing_status(ask("Filing status (single/mfj/mfs/hoh/qw)", "single"))

    spouse = {}
    if fs in ("married_filing_jointly","married_filing_separately"):
        print("\nSpouse information:")
        spouse["first_name"] = ask("Spouse first name", "Sam")
        spouse["last_name"]  = ask("Spouse last name", "Example")
        spouse["ssn"]        = ask("Spouse SSN (###-##-####)", "123-45-6788")
        spouse["dob"]        = parse_date(ask("Spouse date of birth (YYYY-MM-DD)", "1990-02-02"))
    else:
        spouse = None

    # Compute 65+ & blindness flags (DOB based; you can still ask manual overrides if you want)
    tp_age = calc_age_on(dob, AGE_CUTOFF)
    tp_over_65 = tp_age >= 65
    tp_blind   = yn("Are you blind (IRS definition)?", "n")

    sp_over_65 = sp_blind = False
    if spouse:
        sp_age = calc_age_on(spouse["dob"], AGE_CUTOFF)
        sp_over_65 = sp_age >= 65
        sp_blind   = yn("Is spouse blind (IRS definition)?", "n")

    print("\n=== Dependents ===")
    has_deps = yn("Do you have any dependents to claim?", "n")
    dependents = []
    if has_deps:
        count = ask("How many dependents?", 1, int)
        for i in range(1, count+1):
            print(f"Dependent #{i}")
            d_first = ask("  First name", f"Child{i}")
            d_last  = ask("  Last name", "Example")
            d_ssn   = ask("  SSN (###-##-####)", f"000-00-000{i}")
            d_dob   = parse_date(ask("  Date of birth (YYYY-MM-DD)", "2016-01-01"))
            d_rel   = ask("  Relationship (son/daughter/parent/etc.)", "son")
            d_months= ask("  Months lived with you in the year (0-12)", 12, int)
            under_17 = calc_age_on(d_dob, AGE_CUTOFF) < 17
            dependents.append({
                "first_name": d_first, "last_name": d_last, "ssn": d_ssn,
                "dob": d_dob.isoformat(), "relationship": d_rel,
                "months_with_taxpayer": d_months, "under_17": under_17,
            })

    print("\n=== NJ Residency & County/Municipality ===")
    residency = ask("Resident type (full/part)", "full", cast=str, allowed={"full","part"})
    county_muni_code = ask("NJ County/Municipality Code (as printed in NJ-1040 instr.)", "0714")
    nj_move_in = nj_move_out = ""
    if residency == "part":
        nj_move_in  = parse_date(ask("Move-in to NJ date (YYYY-MM-DD)", ""))
        nj_move_out = parse_date(ask("Move-out of NJ date (YYYY-MM-DD)", ""))

    print("\n=== W-2s (at least one) ===")
    w2s = []
    while True:
        employer = ask("Employer", "Company A")
        wages = ask("Wages (Box 1)", 20000, float)
        fed_withheld = ask("Federal income tax withheld (Box 2)", 1500, float)
        ss_wages = ask("Social Security wages (Box 3)", wages, float)
        ss_tax   = ask("Social Security tax withheld (Box 4)", round(ss_wages*0.062,2), float)
        med_wages= ask("Medicare wages (Box 5)", wages, float)
        med_tax  = ask("Medicare tax withheld (Box 6)", round(med_wages*0.0145,2), float)
        nj_wages = ask("NJ wages (Box 16)", wages, float)
        nj_wh    = ask("NJ income tax withheld (Box 17)", 500, float)
        w2s.append({
            "employer": employer,
            "wages_box1": wages,
            "fed_withheld_box2": fed_withheld,
            "ss_wages_box3": ss_wages,
            "ss_tax_box4": ss_tax,
            "medicare_wages_box5": med_wages,
            "medicare_tax_box6": med_tax,
            "nj_wages_box16": nj_wages,
            "nj_withheld_box17": nj_wh
        })
        more = ask("Add another W-2? (y/n)", "n").lower()
        if more != "y":
            break

    print("\n=== Other Income (optional) ===")
    has_other = yn("Did you receive other income (interest/dividends/unemployment/SS/IRA/etc.)?", "n")
    other = {}
    if has_other:
        other["interest"]              = ask("  1099-INT (bank interest) total", 0, float)
        other["ordinary_dividends"]    = ask("  1099-DIV (ordinary dividends)", 0, float)
        other["qualified_dividends"]   = ask("  1099-DIV (qualified dividends)", 0, float)
        other["unemployment"]          = ask("  Unemployment income", 0, float)
        other["social_security"]       = ask("  Social Security benefits (total)", 0, float)
        other["ira_distributions"]     = ask("  IRA distributions", 0, float)
        other["pension_distributions"] = ask("  Pension distributions", 0, float)
        other["gambling_winnings"]     = ask("  Gambling winnings", 0, float)
        # (Self-employment / rental kept for Phase 3)
    else:
        other = {k:0 for k in ["interest","ordinary_dividends","qualified_dividends","unemployment","social_security","ira_distributions","pension_distributions","gambling_winnings"]}

    print("\n=== Adjustments & Deductions (basic) ===")
    itemize = yn("Do you want to itemize deductions (Schedule A)? If unsure, choose No (standard).", "n")
    student_loan_interest = ask("Student loan interest paid", 0, float)
    ira_contrib = ask("Traditional IRA contributions", 0, float)
    hsa_contrib = ask("HSA contributions", 0, float)

    print("\n=== NJ Property Tax / Rent (optional) ===")
    has_housing = yn("Did you pay NJ property tax or rent in the tax year?", "n")
    nj_housing = {}
    if has_housing:
        housing_type = ask("Are you a homeowner, tenant, or both? (homeowner/tenant/both)", "tenant", cast=str, allowed={"homeowner","tenant","both"})
        nj_housing["type"] = housing_type
        nj_housing["property_tax_paid"] = 0.0
        nj_housing["rent_paid"] = 0.0
        if housing_type in ("homeowner","both"):
            nj_housing["property_tax_paid"] = ask("  NJ property tax amount paid", 0, float)
        if housing_type in ("tenant","both"):
            nj_housing["rent_paid"] = ask("  NJ rent amount paid", 0, float)
            nj_housing["months_at_property"] = ask("  # of months lived at this property (0-12)", 12, int)
            nj_housing["landlord_or_owner"] = ask("  Landlord/Property owner name", "ABC Properties")
    else:
        nj_housing = {"type":"none","property_tax_paid":0.0,"rent_paid":0.0}

    print("\n=== Refund / Payment Preferences ===")
    want_dd = yn("If you are due a refund, do you want direct deposit?", "y")
    bank = {}
    if want_dd:
        bank["routing"] = ask("Routing number", "021000021")
        bank["account"] = ask("Account number", "000123456789")
        bank["type"]    = ask("Account type (checking/savings)", "checking", cast=str, allowed={"checking","savings"})

    # Build taxpayer dict
    taxpayer = {
        # identity & contacts
        "first_name": first, "last_name": last, "ssn": ssn,
        "dob": dob.isoformat(),
        "email": email,
        "address1": addr1, "address2": addr2, "city": city, "state": state, "zip": zipc,

        # filing status & flags (computed/asked)
        "filing_status": fs,
        "tp_over_65": (calc_age_on(dob, AGE_CUTOFF) >= 65),
        "tp_blind": bool(tp_blind),
        "sp_over_65": bool(sp_over_65),
        "sp_blind": bool(sp_blind),

        # dependents
        "dependents_count": len(dependents),
        "dependents": dependents,

        # other income (basic subset wired to federal engine)
        "interest": other.get("interest", 0.0),
        "ordinary_dividends": other.get("ordinary_dividends", 0.0),
        "qualified_dividends": other.get("qualified_dividends", 0.0),
        "unemployment": other.get("unemployment", 0.0),
        # hold others for later phases:
        "social_security": other.get("social_security", 0.0),
        "ira_distributions": other.get("ira_distributions", 0.0),
        "pension_distributions": other.get("pension_distributions", 0.0),
        "gambling_winnings": other.get("gambling_winnings", 0.0),

        # deductions/adjustments (Phase 2 basic)
        "itemize": bool(itemize),
        "student_loan_interest": student_loan_interest,
        "ira_contrib": ira_contrib,
        "hsa_contrib": hsa_contrib,

        # NJ residency
        "nj_residency": residency,
        "county_muni_code": county_muni_code,
        "nj_move_in": nj_move_in.isoformat() if isinstance(nj_move_in, date) else "",
        "nj_move_out": nj_move_out.isoformat() if isinstance(nj_move_out, date) else "",

        # NJ housing credit/deduction info
        "nj_housing": nj_housing,

        # refund/payment
        "direct_deposit": bool(want_dd),
        "bank_routing": bank.get("routing","") if want_dd else "",
        "bank_account": bank.get("account","") if want_dd else "",
        "bank_type": bank.get("type","") if want_dd else "",
    }
    if spouse:
        taxpayer["spouse_first_name"] = spouse["first_name"]
        taxpayer["spouse_last_name"]  = spouse["last_name"]
        taxpayer["spouse_ssn"]        = spouse["ssn"]
        taxpayer["spouse_dob"]        = spouse["dob"].isoformat()

    return taxpayer, w2s


def to_engine_inputs(taxpayer, w2s):
    # Compute totals the engines expect right now
    wages_total   = sum(fnum(w.get("wages_box1")) for w in w2s)
    fed_wh_total  = sum(fnum(w.get("fed_withheld_box2")) for w in w2s)
    nj_wh_total   = sum(fnum(w.get("nj_withheld_box17")) for w in w2s)
    # Add them to taxpayer dicts for engines
    tp_fed = dict(taxpayer)
    tp_fed["wages_total"] = wages_total
    tp_fed["federal_withheld_total"] = fed_wh_total

    tp_nj = dict(taxpayer)
    tp_nj["wages_total"] = wages_total
    tp_nj["nj_withheld_total"] = nj_wh_total
    # (Keep per-W2 detail; engines may use it later)
    return tp_fed, tp_nj

def g(d,*ks):
    for k in ks:
        if k in d and d[k] not in (None,"","nan"):
            try: return float(d[k])
            except: return 0.0
    return 0.0

def main():
    print("Mode FED:", "STUB" if os.getenv("USE_STUB_FED","0")=="1" else "FULL")
    print("Mode  NJ:", "STUB" if os.getenv("USE_STUB_NJ","0")=="1" else "FULL")

    taxpayer, w2s = gather_user_input()

    # Save session CSVs (optional audit)
    out_dir = Path("sessions") / (taxpayer["last_name"] + "_" + taxpayer["first_name"])
    out_dir.mkdir(parents=True, exist_ok=True)

    # CSV snapshots
    write_csv(out_dir / "fed_taxpayer.csv",   [{k: taxpayer.get(k,"") for k in ["first_name","last_name","ssn","dob","email","address1","address2","city","state","zip"]}])
    write_csv(out_dir / "fed_questions.csv",  [{k: taxpayer.get(k,"") for k in ["filing_status","tp_over_65","tp_blind","sp_over_65","sp_blind","dependents_count","interest","ordinary_dividends","qualified_dividends","unemployment","student_loan_interest","ira_contrib","hsa_contrib","itemize"]}])
    write_csv(out_dir / "fed_dependents.csv", taxpayer.get("dependents", []))
    write_csv(out_dir / "fed_w2.csv",         w2s)

    write_csv(out_dir / "nj_taxpayer.csv",    [{k: taxpayer.get(k,"") for k in ["first_name","last_name","ssn","dob","address1","address2","city","state","zip","county_muni_code"]}])
    write_csv(out_dir / "nj_questions.csv",   [{k: taxpayer.get(k,"") for k in ["filing_status","nj_residency","nj_move_in","nj_move_out","dependents_count"]}])
    write_csv(out_dir / "nj_dependents.csv",  taxpayer.get("dependents", []))
    write_csv(out_dir / "nj_w2.csv",          w2s)
    write_csv(out_dir / "nj_housing.csv",     [taxpayer.get("nj_housing", {})])

    # Engine inputs and run
    tp_fed, tp_nj = to_engine_inputs(taxpayer, w2s)
    fed_lines = FED(tp_fed, w2s)
    nj_lines  = NJ(tp_nj,  w2s)

    # Summaries
    wages  = sum(fnum(w.get("wages_box1")) for w in w2s)
    fed_wh = sum(fnum(w.get("fed_withheld_box2")) for w in w2s)
    nj_wh  = sum(fnum(w.get("nj_withheld_box17")) for w in w2s)

    fed_tax = g(fed_lines,"16","total_tax")
    fed_ref = g(fed_lines,"34","refund")
    fed_owed= g(fed_lines,"37","amount_owed")

    nj_tax  = g(nj_lines,"16","total_tax","tax")
    nj_ref  = g(nj_lines,"34","refund")
    nj_owed = g(nj_lines,"37","amount_owed","balance_due")

    print("\n=== Federal Summary ===")
    print(f"Wages: {wages:,.2f} | Tax: {fed_tax:,.2f} | Withheld: {fed_wh:,.2f} | Refund: {fed_ref:,.2f} | Owed: {fed_owed:,.2f}")
    print("\n=== NJ Summary ===")
    print(f"Wages: {wages:,.2f} | Tax: {nj_tax:,.2f} | Withheld: {nj_wh:,.2f} | Refund: {nj_ref:,.2f} | Owed: {nj_owed:,.2f}")

    # Save JSONs to drive PDF fill later
    (out_dir / "out_f1040.json").write_text(json.dumps({"inputs":{"taxpayer":tp_fed,"w2s":w2s},"lines":fed_lines}, indent=2))
    (out_dir / "out_nj1040.json").write_text(json.dumps({"inputs":{"taxpayer":tp_nj,"w2s":w2s},"lines":nj_lines}, indent=2))
    print(f"\nSaved session files in {out_dir.resolve()}")

if __name__ == "__main__":
    main()
