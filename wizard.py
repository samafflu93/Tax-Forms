#!/usr/bin/env python3
# Interactive Tax Wizard (Federal + NJ) — Phase 2+
# Asks questions → computes FED + NJ via engines → writes JSON + CSVs

import os, csv, json, datetime
from pathlib import Path

# ---------- Output locations ----------
OUT_DIR = Path("out")
OUT_DIR.mkdir(exist_ok=True)
(OUT_DIR / "user_inputs").mkdir(parents=True, exist_ok=True)

# ---------- Engine imports (stub/full toggle) ----------
# Set USE_STUB_FED=1 or USE_STUB_NJ=1 to force stub engines (optional)
if os.getenv("USE_STUB_FED", "0") == "1":
    from engines.compute_federal import compute_federal as FED
else:
    from engines.compute_federal_full import compute_federal as FED

if os.getenv("USE_STUB_NJ", "0") == "1":
    from engines.compute_nj import compute_nj as NJ
else:
    from engines.compute_nj_full import compute_nj as NJ

# ---------- Helpers ----------
def ask(prompt, default=None, cast=str, choices=None):
    """
    Ask user for input with optional default, cast, and (case-insensitive) choices validation.
    """
    while True:
        raw = input(f"{prompt}" + (f" [{default}]" if default is not None else "") + ": ").strip()
        if raw == "" and default is not None:
            raw = str(default)
        try:
            val = cast(raw) if raw != "" else cast("" if default is None else default)
        except Exception:
            print("  Please enter a valid value.")
            continue
        if choices:
            if isinstance(val, str):
                if val.lower() not in {c.lower() for c in choices}:
                    print(f"  Please choose one of: {', '.join(choices)}")
                    continue
            else:
                if val not in choices:
                    print(f"  Please choose one of: {choices}")
                    continue
        return val

def yn(prompt, default="n"):
    s = input(f"{prompt} (y/n) [{default}]: ").strip().lower()
    if not s:
        s = default.lower()
    return s in ("y", "yes")

def fnum(x):
    try:
        if x is None: return 0.0
        if isinstance(x, (int, float)): return float(x)
        s = str(x).strip()
        return float(s) if s else 0.0
    except Exception:
        return 0.0

# ---------- Sections ----------
def gather_personal():
    print("\n=== Personal Info ===")
    first = ask("First name")
    last = ask("Last name")
    ssn = ask("SSN (123-45-6789)")
    dob = ask("Date of birth (YYYY-MM-DD)")
    filing_status = ask(
        "Filing status",
        "single",
        str,
        {"single", "married_joint", "married_separate", "head_household", "qual_widow"}
    )
    email = ask("Email (optional)", "", str)
    nj_full_year = yn("Are you a full-year New Jersey resident?", "y")
    address = ask("Home address (street/city/state/zip)", "")

    return {
        "first_name": first,
        "last_name": last,
        "ssn": ssn,
        "dob": dob,
        "filing_status": filing_status,
        "email": email,
        "nj_full_year_resident": "y" if nj_full_year else "n",
        "address": address,
    }

def gather_dependents():
    print("\n=== Dependents ===")
    deps = []
    if yn("Do you have dependents to claim?", "n"):
        while True:
            name = ask("  Dependent full name")
            dssn = ask("  Dependent SSN")
            ddob = ask("  Dependent DOB (YYYY-MM-DD)")
            relation = ask("  Relationship (child/parent/other)", "child")
            deps.append({
                "name": name,
                "ssn": dssn,
                "dob": ddob,
                "relationship": relation
            })
            if not yn("  Add another dependent?", "n"):
                break
    return deps

def gather_w2s():
    print("\n=== W-2 Income (one or more) ===")
    w2s = []
    if not yn("Do you have any W-2s?", "y"):
        return w2s
    while True:
        employer = ask("  Employer name")
        wages = fnum(ask("  Wages (Box 1)", "0", float))
        fed_wh = fnum(ask("  Federal income tax withheld (Box 2)", "0", float))
        ss_w = fnum(ask("  Social Security wages (Box 3) [optional]", "0", float))
        ss_t = fnum(ask("  Social Security tax withheld (Box 4) [optional]", "0", float))
        med_w = fnum(ask("  Medicare wages (Box 5) [optional]", "0", float))
        med_t = fnum(ask("  Medicare tax withheld (Box 6) [optional]", "0", float))
        nj_w = fnum(ask("  NJ wages (Box 16)", "0", float))
        nj_wh = fnum(ask("  NJ income tax withheld (Box 17)", "0", float))

        w2s.append({
            "employer": employer,
            "wages": wages,
            "federal_withheld": fed_wh,
            "ss_wages": ss_w,
            "ss_tax": ss_t,
            "medicare_wages": med_w,
            "medicare_tax": med_t,
            "nj_wages": nj_w,
            "nj_withheld": nj_wh,
        })

        if not yn("  Add another W-2?", "n"):
            break
    return w2s

def gather_other_income():
    print("\n=== Other Income (optional) ===")
    out = {
        "interest": 0.0,
        "dividends": 0.0,
        "unemployment": 0.0,
        "nec_income": 0.0,
        "nec_expenses": 0.0,
        "ssa_benefits": 0.0,
        "pension_distributions": 0.0,
    }

    if yn("Any bank interest (1099-INT)?", "n"):
        out["interest"] = fnum(ask("  1099-INT interest", "0", float))
    if yn("Any dividends (1099-DIV)?", "n"):
        out["dividends"] = fnum(ask("  1099-DIV dividends", "0", float))
    if yn("Any unemployment income?", "n"):
        out["unemployment"] = fnum(ask("  Unemployment income", "0", float))
    if yn("Any 1099-NEC self-employment income?", "n"):
        out["nec_income"] = fnum(ask("  1099-NEC gross income", "0", float))
        out["nec_expenses"] = fnum(ask("  1099-NEC expenses", "0", float))

    # NEW: Social Security & Pensions/IRA
    if yn("Any Social Security benefits (SSA-1099)?", "n"):
        out["ssa_benefits"] = fnum(ask("  SSA benefits (total for the year)", "0", float))
    if yn("Any pension/IRA distributions (1099-R)?", "n"):
        out["pension_distributions"] = fnum(ask("  1099-R total distributions (taxable portion if known)", "0", float))

    return out

def gather_adjustments():
    print("\n=== Adjustments & Deductions (basic) ===")
    itemize = yn("Do you want to itemize deductions (Schedule A)? If unsure, choose No (standard).", "n")
    stud_loan = fnum(ask("Student loan interest paid", "0", float))
    ira_contrib = fnum(ask("Traditional IRA contributions", "0", float))
    hsa_contrib = fnum(ask("HSA contributions", "0", float))
    return {
        "itemize": "y" if itemize else "n",
        "student_loan_interest": stud_loan,
        "ira_contrib": ira_contrib,
        "hsa_contrib": hsa_contrib,
    }

def gather_nj_housing():
    print("\n=== NJ Property Tax / Rent (optional) ===")
    if yn("Did you pay NJ property tax or rent in the tax year? (y/n)", "n"):
        status = ask(
            "Are you a homeowner, tenant, or both? (homeowner/tenant/both)",
            "tenant", str, {"homeowner", "tenant", "both"}
        )
        # engines want a single status; if "both", we'll keep "both" and engines will handle sum
        housing_status = status

        property_tax_paid = 0.0
        rent_paid = 0.0
        if status in ("homeowner", "both"):
            property_tax_paid = fnum(ask("  NJ property tax paid", "0", float))
        if status in ("tenant", "both"):
            rent_paid = fnum(ask("  NJ rent paid", "0", float))

        months   = int(fnum(ask("  # of months lived at this property (0–12)", "12", float)))
        landlord = ask("  Landlord/Property owner name [optional]", "")

        return {
            "housing_status": housing_status,
            "property_tax_paid": property_tax_paid,
            "rent_paid": rent_paid,
            "housing_months": months,
            "landlord": landlord,
        }
    else:
        return {
            "housing_status": "",
            "property_tax_paid": 0.0,
            "rent_paid": 0.0,
            "housing_months": 0,
            "landlord": "",
        }

def gather_refund_info():
    print("\n=== Refund / Payment Preferences ===")
    direct = yn("If you are due a refund, do you want direct deposit?", "y")
    if direct:
        routing = ask("Routing number")
        account = ask("Account number")
        acct_type = ask("Account type (checking/savings)", "checking", str, {"checking", "savings"})
    else:
        routing = account = ""
        acct_type = ""
    return {
        "want_direct_deposit": "y" if direct else "n",
        "bank_routing": routing,
        "bank_account": account,
        "bank_account_type": acct_type,
    }

# ---------- CSV writers ----------
def save_taxpayer_csv(taxpayer, dependents):
    path = OUT_DIR / "user_inputs" / "taxpayer.csv"
    row = dict(taxpayer)
    row["dependents_count"] = len(dependents)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        w.writeheader()
        w.writerow(row)

def save_w2s_csv(w2s):
    path = OUT_DIR / "user_inputs" / "w2s.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        if w2s:
            fields = list(w2s[0].keys())
        else:
            fields = ["employer","wages","federal_withheld","nj_wages","nj_withheld"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in w2s:
            w.writerow(r)

# ---------- Main flow ----------
def main():
    print("US + NJ Tax Wizard —", datetime.date.today().isoformat())
    print("(Educational tool — not official tax advice.)")

    taxpayer = {}
    taxpayer.update(gather_personal())

    dependents = gather_dependents()
    taxpayer["dependents"] = dependents  # engines accept the list directly

    w2s = gather_w2s()

    # Other income (interest/dividends/unemployment/NEC + NEW: SSA, Pension)
    taxpayer.update(gather_other_income())

    # Basic adjustments/deductions
    taxpayer.update(gather_adjustments())

    # NJ housing (rent/property tax)
    taxpayer.update(gather_nj_housing())

    # Banking / refund prefs
    taxpayer.update(gather_refund_info())

    # ---- Save the inputs for reference as CSVs ----
    save_taxpayer_csv(taxpayer, dependents)
    save_w2s_csv(w2s)

    # ---- Compute lines via engines ----
    fed_lines = FED(taxpayer, w2s)
    nj_lines  = NJ(taxpayer, w2s)

    # ---- Write JSON outputs ----
    with (OUT_DIR / "out_f1040.json").open("w", encoding="utf-8") as f:
        json.dump({"inputs": {"taxpayer": taxpayer, "w2s": w2s}, "lines": fed_lines}, f, indent=2)

    with (OUT_DIR / "out_nj1040.json").open("w", encoding="utf-8") as f:
        json.dump({"inputs": {"taxpayer": taxpayer, "w2s": w2s}, "lines": nj_lines}, f, indent=2)

    # Quick console summaries
    wages = sum(fnum(w.get("wages", 0)) for w in w2s)
    fed_wh = sum(fnum(w.get("federal_withheld", 0)) for w in w2s)
    nj_wh  = sum(fnum(w.get("nj_withheld", 0)) for w in w2s)

    print("\n=== Federal Summary ===")
    print(f"Wages: {wages:,.2f} | Withheld: {fed_wh:,.2f} | Tax (pre-credits): {fed_lines.get('16',0):,.2f} | Refund: {fed_lines.get('34',0):,.2f} | Owed: {fed_lines.get('37',0):,.2f}")
    print("Wrote", OUT_DIR / "out_f1040.json")

    print("\n=== NJ Summary ===")
    print(f"Wages: {wages:,.2f} | Withheld: {nj_wh:,.2f} | Tax: {nj_lines.get('16',0):,.2f} | Refund: {nj_lines.get('34',0):,.2f} | Owed: {nj_lines.get('37',0):,.2f}")
    print("Wrote", OUT_DIR / "out_nj1040.json")

if __name__ == "__main__":
    main()

