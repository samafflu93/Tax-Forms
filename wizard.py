# wizard.py — console wizard with Review/Edit and money digit arrays
from __future__ import annotations
import os, sys, json
from typing import Dict, List

# ---------- small input helpers ----------

def prompt(label: str, default: str = "") -> str:
    ans = input(f"{label} [{default}]: ").strip()
    return ans if ans else default

def prompt_yesno(label: str, default_no: bool = False) -> bool:
    default_letter = "n" if default_no else "y"
    ans = input(f"{label} (y/n) [{default_letter}]: ").strip().lower()
    if not ans:
        return default_letter == "y"
    return ans.startswith("y")

def _to_float_money(raw: str) -> float:
    # supports $ , and parentheses for negatives
    s = (raw or "").strip().replace(",", "").replace("$", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    return float(s) if s else 0.0

def prompt_money(label: str, default: float = 0.0) -> float:
    ans = input(f"{label} [{default}]: ").strip()
    if ans == "":
        return float(default)
    try:
        return _to_float_money(ans)
    except ValueError:
        print("  Please enter a number (e.g., 1,234.56 or ($123.45)).")
        return prompt_money(label, default)

def prompt_int(label: str, default: int = 0) -> int:
    ans = input(f"{label} [{default}]: ").strip().replace(",", "")
    if ans == "":
        return default
    try:
        return int(float(ans))
    except ValueError:
        print("  Please enter a whole number.")
        return prompt_int(label, default)

def prompt_choice(label: str, options: List[str], default: str) -> str:
    opts = ", ".join(options)
    while True:
        ans = input(f"{label} [{default}]\n  Please choose one of: {opts}\n> ").strip().lower()
        if not ans:
            return default
        if ans in options:
            return ans
        print("  Invalid choice, try again.")

def digits_list(raw: str) -> List[str]:
    return [c for c in str(raw) if c.isdigit()]

# ---------- money → digit arrays ----------

def money_to_digits(amount: float, dollar_pad: int = 9) -> (List[str], List[str]):
    """
    Convert 1234.56 -> (['0','0','0','0','1','2','3','4'], ['5','6']) with pad=8
    - dollars are zero-padded on the left to dollar_pad
    - cents always 2 digits
    """
    try:
        val = float(amount)
    except Exception:
        val = 0.0
    val_abs = abs(val)
    dollars = int(val_abs)  # floor toward zero
    cents = int(round((val_abs - dollars) * 100))  # rounded cents
    if cents == 100:  # handle 1.9999 -> 2.00 rounding edge
        dollars += 1
        cents = 0
    d_str = f"{dollars:0{dollar_pad}d}"
    c_str = f"{cents:02d}"
    return list(d_str), list(c_str)

def set_money(obj: Dict, key: str, value: float, pad: int = 9):
    """Store numeric and digits arrays side-by-side on obj."""
    obj[key] = float(value or 0.0)
    d, c = money_to_digits(obj[key], pad)
    obj[f"{key}_digits"] = d
    obj[f"{key}_cents_digits"] = c

# ---------- collect sections ----------

def collect_personal_info() -> Dict:
    print("\n=== Basic Personal Info ===")
    tp: Dict = {}
    tp["first"] = prompt("First name")
    tp["last"]  = prompt("Last name")
    ssn_raw     = prompt("SSN (123-45-6789)")
    tp["ssn"]   = ssn_raw
    tp["ssn_digits"] = digits_list(ssn_raw)

    dob_raw     = prompt("Date of Birth (MM/DD/YYYY)")
    tp["dob"]   = dob_raw
    tp["dob_digits"] = digits_list(dob_raw)

    tp["email"] = prompt("Email (optional)")
    tp["filing_status"] = prompt_choice(
        "Filing status",
        ["single", "married_joint", "married_separate", "head_household", "qual_widow"],
        "single",
    )

    print("\n=== Address & Residency ===")
    addr: Dict = {}
    addr["line1"] = prompt("Address line 1")
    addr["line2"] = prompt("Address line 2 (optional)")
    addr["city"]  = prompt("City")
    addr["state"] = prompt("State (2 letters)", "NJ")
    zip_raw       = prompt("ZIP code (5 digits)")
    addr["zip"]   = zip_raw
    addr["zip_digits"] = digits_list(zip_raw)
    tp["address"] = addr

    tp["nj_full_year_resident"] = prompt_yesno("Are you a full-year NJ resident?")
    tp["nj_county"] = prompt("NJ County (optional)")
    return tp

def collect_dependents() -> List[Dict]:
    deps: List[Dict] = []
    print("\n=== Dependents (optional) ===")
    if not prompt_yesno("Do you have any dependents?"):
        return deps

    while True:
        first = prompt("  Dependent first name")
        last  = prompt("  Dependent last name")
        ssn   = prompt("  Dependent SSN (123-45-6789)")
        dob   = prompt("  Dependent DOB (MM/DD/YYYY)")
        rel   = prompt("  Relationship to you")
        deps.append({
            "first": first,
            "last":  last,
            "ssn":   ssn,
            "digits": digits_list(ssn),
            "dob":   dob,
            "dob_digits": digits_list(dob),
            "relationship": rel,
        })
        if not prompt_yesno("Add another dependent?"):
            break
    return deps

def collect_w2s() -> List[Dict]:
    w2s: List[Dict] = []
    print("\n=== W-2 Income ===")
    if not prompt_yesno("Do you have any W-2s?"):
        return w2s
    while True:
        print("\nEnter W-2 details from the form (box labels shown):")
        w: Dict = {}
        w["employer"] = prompt("Employer name")

        set_money(w, "wages",            prompt_money("  Box 1 – Wages"))
        set_money(w, "federal_withheld", prompt_money("  Box 2 – Federal income tax withheld"))
        set_money(w, "ss_wages",         prompt_money("  Box 3 – Social Security wages", 0.0))
        set_money(w, "ss_tax",           prompt_money("  Box 4 – Social Security tax withheld", 0.0))
        set_money(w, "medicare_wages",   prompt_money("  Box 5 – Medicare wages", 0.0))
        set_money(w, "medicare_tax",     prompt_money("  Box 6 – Medicare tax", 0.0))
        set_money(w, "nj_wages",         prompt_money("  Box 16 – NJ wages"))
        set_money(w, "nj_withheld",      prompt_money("  Box 17 – NJ income tax withheld"))

        w2s.append(w)
        if not prompt_yesno("Add another W-2?"):
            break
    return w2s

def collect_other_income(tp: Dict):
    print("\n=== Other Income (optional) ===")
    if prompt_yesno("Any bank interest (1099-INT)?"):
        set_money(tp, "interest", prompt_money("  1099-INT Box 1 – Interest"))
    else:
        set_money(tp, "interest", 0.0)

    if prompt_yesno("Any dividends (1099-DIV)?"):
        set_money(tp, "dividends", prompt_money("  1099-DIV Box 1a – Ordinary dividends"))
    else:
        set_money(tp, "dividends", 0.0)

    if prompt_yesno("Any unemployment income (1099-G)?"):
        set_money(tp, "unemployment", prompt_money("  1099-G Box 1 – Unemployment"))
    else:
        set_money(tp, "unemployment", 0.0)

    if prompt_yesno("Any 1099-NEC self-employment income?"):
        set_money(tp, "nec_income",   prompt_money("  1099-NEC Box 1 – Gross income"))
        set_money(tp, "nec_expenses", prompt_money("  1099-NEC Expenses", 0.0))
    else:
        set_money(tp, "nec_income",   0.0)
        set_money(tp, "nec_expenses", 0.0)

    if prompt_yesno("Any Social Security benefits (SSA-1099)?"):
        set_money(tp, "ssa_benefits", prompt_money("  SSA-1099 Box 5 – Net benefits"))
    else:
        set_money(tp, "ssa_benefits", 0.0)

    if prompt_yesno("Any pension/IRA distributions (1099-R)?"):
        set_money(tp, "pension", prompt_money("  1099-R Box 1 – Gross distribution"))
    else:
        set_money(tp, "pension", 0.0)

def collect_adjustments(tp: Dict):
    print("\n=== Adjustments & Deductions (basic) ===")
    tp["itemize"] = prompt_yesno(
        "Do you want to itemize deductions (Schedule A)? If unsure, choose No (standard).",
        default_no=True
    )
    set_money(tp, "student_loan_interest", prompt_money("Student loan interest", 0.0))
    set_money(tp, "ira_contributions",     prompt_money("Traditional IRA contributions", 0.0))
    set_money(tp, "hsa_contributions",     prompt_money("HSA contributions", 0.0))

def collect_nj_property(tp: Dict):
    print("\n=== NJ Property Tax / Rent (optional) ===")
    if not prompt_yesno("Did you pay NJ property tax or rent in the tax year?"):
        set_money(tp, "rent_paid", 0.0)
        set_money(tp, "property_tax_paid", 0.0)
        tp["months_at_property"] = 0
        tp["landlord_or_owner"]  = ""
        return
    status = prompt_choice("Are you a homeowner, tenant, or both? (homeowner/tenant/both)",
                           ["homeowner","tenant","both"], "tenant")
    if status in ("tenant","both"):
        set_money(tp, "rent_paid", prompt_money("  NJ rent amount paid", 0.0))
    else:
        set_money(tp, "rent_paid", 0.0)
    if status in ("homeowner","both"):
        set_money(tp, "property_tax_paid", prompt_money("  NJ property tax paid", 0.0))
    else:
        set_money(tp, "property_tax_paid", 0.0)
    tp["months_at_property"] = prompt_int("  # of months lived at this property (0–12)", 12)
    tp["landlord_or_owner"]  = prompt("  Landlord/Property owner name", "")

def collect_refund_prefs(tp: Dict):
    print("\n=== Refund / Payment Preferences ===")
    if prompt_yesno("If you are due a refund, do you want direct deposit?"):
        tp["direct_deposit"] = True
        routing = prompt("Routing number (9 digits)")
        account = prompt("Account number")
        tp["bank_routing"] = routing
        tp["bank_routing_digits"] = digits_list(routing)
        tp["bank_account"] = account
        tp["bank_account_digits"] = digits_list(account)
        tp["bank_account_type"] = prompt_choice("Account type", ["checking","savings"], "checking")
    else:
        tp["direct_deposit"] = False
        tp["bank_routing"] = ""
        tp["bank_account"] = ""
        tp["bank_account_type"] = "checking"
        tp["bank_routing_digits"] = []
        tp["bank_account_digits"] = []

# ---------- Review & Edit helpers ----------

def show_summary(tp: Dict, w2s: List[Dict]):
    print("\n=========== REVIEW SUMMARY ===========")
    print(f"Name: {tp.get('first','')} {tp.get('last','')}")
    print(f"SSN:  {tp.get('ssn','')}")
    print(f"DOB:  {tp.get('dob','')}")
    print(f"Email: {tp.get('email','')}")
    print(f"Filing status: {tp.get('filing_status','')}")
    addr = tp.get("address", {})
    print("Address:")
    print(f"  {addr.get('line1','')}")
    if addr.get("line2"): print(f"  {addr.get('line2')}")
    print(f"  {addr.get('city','')}, {addr.get('state','')} {addr.get('zip','')}")
    print(f"NJ full-year resident: {tp.get('nj_full_year_resident', False)}")
    if tp.get("nj_county"): print(f"NJ County: {tp.get('nj_county')}")

    print("\nDependents:")
    deps = tp.get("dependents", [])
    if not deps:
        print("  (none)")
    else:
        for i, d in enumerate(deps, 1):
            print(f"  {i}. {d.get('first','')} {d.get('last','')} — {d.get('relationship','')} (SSN {d.get('ssn','')})")

    print("\nW-2s:")
    if not w2s:
        print("  (none)")
    else:
        for i, w in enumerate(w2s, 1):
            print(f"  {i}. {w.get('employer','')}: "
                  f"Wages {w.get('wages',0):,.2f}, Fed WH {w.get('federal_withheld',0):,.2f}, "
                  f"NJ Wages {w.get('nj_wages',0):,.2f}, NJ WH {w.get('nj_withheld',0):,.2f}")

    print("\nOther Income:")
    print(f"  Interest(1099-INT): {tp.get('interest',0):,.2f}")
    print(f"  Dividends(1099-DIV): {tp.get('dividends',0):,.2f}")
    print(f"  Unemployment(1099-G): {tp.get('unemployment',0):,.2f}")
    print(f"  NEC gross(1099-NEC): {tp.get('nec_income',0):,.2f}  Expenses: {tp.get('nec_expenses',0):,.2f}")
    print(f"  Social Security(SSA-1099): {tp.get('ssa_benefits',0):,.2f}")
    print(f"  Pension/IRA(1099-R): {tp.get('pension',0):,.2f}")

    print("\nAdjustments & NJ:")
    print(f"  Student loan interest: {tp.get('student_loan_interest',0):,.2f}")
    print(f"  IRA contributions: {tp.get('ira_contributions',0):,.2f}")
    print(f"  HSA contributions: {tp.get('hsa_contributions',0):,.2f}")
    print(f"  Rent paid (NJ): {tp.get('rent_paid',0):,.2f}")
    print(f"  Property tax paid (NJ): {tp.get('property_tax_paid',0):,.2f}")
    print(f"  Months at property: {tp.get('months_at_property',0)}")
    if tp.get("landlord_or_owner"): print(f"  Landlord/Owner: {tp.get('landlord_or_owner')}")

    print("\nRefund/Deposit:")
    if tp.get("direct_deposit", False):
        print(f"  Direct deposit: YES ({tp.get('bank_account_type','checking')})")
        print(f"  Routing: {tp.get('bank_routing','')}  Account: {tp.get('bank_account','')}")
    else:
        print("  Direct deposit: NO")
    print("======================================\n")

def edit_personal(tp: Dict):
    print("\n-- Edit: Personal & Address --")
    tp["first"] = prompt("First name", tp.get("first",""))
    tp["last"]  = prompt("Last name",  tp.get("last",""))

    ssn_raw = prompt("SSN (123-45-6789)", tp.get("ssn",""))
    tp["ssn"] = ssn_raw
    tp["ssn_digits"] = digits_list(ssn_raw)

    dob_raw = prompt("Date of Birth (MM/DD/YYYY)", tp.get("dob",""))
    tp["dob"] = dob_raw
    tp["dob_digits"] = digits_list(dob_raw)

    tp["email"] = prompt("Email (optional)", tp.get("email",""))
    tp["filing_status"] = prompt_choice(
        "Filing status",
        ["single","married_joint","married_separate","head_household","qual_widow"],
        tp.get("filing_status","single"),
    )
    addr = tp.get("address", {})
    addr["line1"] = prompt("Address line 1", addr.get("line1",""))
    addr["line2"] = prompt("Address line 2 (optional)", addr.get("line2",""))
    addr["city"]  = prompt("City", addr.get("city",""))
    addr["state"] = prompt("State (2 letters)", addr.get("state","NJ"))
    zip_raw      = prompt("ZIP code (5 digits)", addr.get("zip",""))
    addr["zip"]  = zip_raw
    addr["zip_digits"] = digits_list(zip_raw)
    tp["address"] = addr

    tp["nj_full_year_resident"] = prompt_yesno("Full-year NJ resident?", default_no=not tp.get("nj_full_year_resident", True))
    tp["nj_county"] = prompt("NJ County (optional)", tp.get("nj_county",""))

def edit_one_w2(w: Dict):
    print("\nEditing this W-2:")
    w["employer"] = prompt("  Employer", w.get("employer",""))
    set_money(w, "wages",            prompt_money("  Box 1 – Wages", w.get("wages",0)))
    set_money(w, "federal_withheld", prompt_money("  Box 2 – Fed income tax withheld", w.get("federal_withheld",0)))
    set_money(w, "ss_wages",         prompt_money("  Box 3 – SS wages", w.get("ss_wages",0)))
    set_money(w, "ss_tax",           prompt_money("  Box 4 – SS tax withheld", w.get("ss_tax",0)))
    set_money(w, "medicare_wages",   prompt_money("  Box 5 – Medicare wages", w.get("medicare_wages",0)))
    set_money(w, "medicare_tax",     prompt_money("  Box 6 – Medicare tax", w.get("medicare_tax",0)))
    set_money(w, "nj_wages",         prompt_money("  Box 16 – NJ wages", w.get("nj_wages",0)))
    set_money(w, "nj_withheld",      prompt_money("  Box 17 – NJ tax withheld", w.get("nj_withheld",0)))

def edit_w2s(w2s: List[Dict]):
    while True:
        print("\n-- Edit: W-2s --")
        if not w2s:
            print("No W-2s yet.")
        else:
            for i, w in enumerate(w2s, 1):
                print(f"  {i}. {w.get('employer','')} — Wages {w.get('wages',0):,.2f}, Fed WH {w.get('federal_withheld',0):,.2f}")
        choice = prompt_choice("Choose: add, edit, delete, done", ["add","edit","delete","done"], "done")
        if choice == "done":
            return
        if choice == "add":
            w2s.extend(collect_w2s())
        elif choice == "edit":
            if not w2s:
                print("No W-2 to edit."); continue
            idx = max(1, min(len(w2s), prompt_int("Which W-2 # to edit?", 1)))
            edit_one_w2(w2s[idx-1])
        elif choice == "delete":
            if not w2s:
                print("No W-2 to delete."); continue
            idx = max(1, min(len(w2s), prompt_int("Which W-2 # to delete?", 1)))
            del w2s[idx-1]

def edit_other_income(tp: Dict):
    print("\n-- Edit: Other Income --")
    set_money(tp, "interest",      prompt_money("  1099-INT Box 1 – Interest", tp.get("interest",0)))
    set_money(tp, "dividends",     prompt_money("  1099-DIV Box 1a – Ordinary dividends", tp.get("dividends",0)))
    set_money(tp, "unemployment",  prompt_money("  1099-G Box 1 – Unemployment", tp.get("unemployment",0)))
    set_money(tp, "nec_income",    prompt_money("  1099-NEC Box 1 – Gross", tp.get("nec_income",0)))
    set_money(tp, "nec_expenses",  prompt_money("  1099-NEC Expenses", tp.get("nec_expenses",0)))
    set_money(tp, "ssa_benefits",  prompt_money("  SSA-1099 Box 5 – Net benefits", tp.get("ssa_benefits",0)))
    set_money(tp, "pension",       prompt_money("  1099-R Box 1 – Gross distribution", tp.get("pension",0)))

def edit_adjustments(tp: Dict):
    print("\n-- Edit: Adjustments & Deductions --")
    tp["itemize"] = prompt_yesno("Itemize deductions (Schedule A)?", default_no=not tp.get("itemize", False))
    set_money(tp, "student_loan_interest", prompt_money("  Student loan interest", tp.get("student_loan_interest",0)))
    set_money(tp, "ira_contributions",     prompt_money("  Traditional IRA contributions", tp.get("ira_contributions",0)))
    set_money(tp, "hsa_contributions",     prompt_money("  HSA contributions", tp.get("hsa_contributions",0)))

def edit_nj_property(tp: Dict):
    print("\n-- Edit: NJ Rent / Property Tax --")
    set_money(tp, "rent_paid",         prompt_money("  Rent paid (NJ)", tp.get("rent_paid",0)))
    set_money(tp, "property_tax_paid", prompt_money("  Property tax paid (NJ)", tp.get("property_tax_paid",0)))
    tp["months_at_property"] = prompt_int("  Months lived at property (0–12)", tp.get("months_at_property",0))
    tp["landlord_or_owner"]  = prompt("  Landlord/Owner (optional)", tp.get("landlord_or_owner",""))

def edit_refund_prefs(tp: Dict):
    print("\n-- Edit: Refund / Payment Prefs --")
    dd = prompt_yesno("Direct deposit if refund?", default_no=not tp.get("direct_deposit", False))
    tp["direct_deposit"] = dd
    if dd:
        routing = prompt("  Routing number", tp.get("bank_routing",""))
        account = prompt("  Account number", tp.get("bank_account",""))
        tp["bank_routing"] = routing
        tp["bank_routing_digits"] = digits_list(routing)
        tp["bank_account"] = account
        tp["bank_account_digits"] = digits_list(account)
        tp["bank_account_type"] = prompt_choice("  Account type", ["checking","savings"], tp.get("bank_account_type","checking"))

def show_summary(tp: Dict, w2s: List[Dict]):
    # (kept same as above)
    print("\n=========== REVIEW SUMMARY ===========")
    print(f"Name: {tp.get('first','')} {tp.get('last','')}")
    print(f"SSN:  {tp.get('ssn','')}")
    print(f"DOB:  {tp.get('dob','')}")
    print(f"Email: {tp.get('email','')}")
    print(f"Filing status: {tp.get('filing_status','')}")
    addr = tp.get("address", {})
    print("Address:")
    print(f"  {addr.get('line1','')}")
    if addr.get("line2"): print(f"  {addr.get('line2')}")
    print(f"  {addr.get('city','')}, {addr.get('state','')} {addr.get('zip','')}")
    print(f"NJ full-year resident: {tp.get('nj_full_year_resident', False)}")
    if tp.get("nj_county"): print(f"NJ County: {tp.get('nj_county')}")

    print("\nDependents:")
    deps = tp.get("dependents", [])
    if not deps:
        print("  (none)")
    else:
        for i, d in enumerate(deps, 1):
            print(f"  {i}. {d.get('first','')} {d.get('last','')} — {d.get('relationship','')} (SSN {d.get('ssn','')})")

    print("\nW-2s:")
    if not w2s:
        print("  (none)")
    else:
        for i, w in enumerate(w2s, 1):
            print(f"  {i}. {w.get('employer','')}: "
                  f"Wages {w.get('wages',0):,.2f}, Fed WH {w.get('federal_withheld',0):,.2f}, "
                  f"NJ Wages {w.get('nj_wages',0):,.2f}, NJ WH {w.get('nj_withheld',0):,.2f}")

    print("\nOther Income:")
    print(f"  Interest(1099-INT): {tp.get('interest',0):,.2f}")
    print(f"  Dividends(1099-DIV): {tp.get('dividends',0):,.2f}")
    print(f"  Unemployment(1099-G): {tp.get('unemployment',0):,.2f}")
    print(f"  NEC gross(1099-NEC): {tp.get('nec_income',0):,.2f}  Expenses: {tp.get('nec_expenses',0):,.2f}")
    print(f"  Social Security(SSA-1099): {tp.get('ssa_benefits',0):,.2f}")
    print(f"  Pension/IRA(1099-R): {tp.get('pension',0):,.2f}")

    print("\nAdjustments & NJ:")
    print(f"  Student loan interest: {tp.get('student_loan_interest',0):,.2f}")
    print(f"  IRA contributions: {tp.get('ira_contributions',0):,.2f}")
    print(f"  HSA contributions: {tp.get('hsa_contributions',0):,.2f}")
    print(f"  Rent paid (NJ): {tp.get('rent_paid',0):,.2f}")
    print(f"  Property tax paid (NJ): {tp.get('property_tax_paid',0):,.2f}")
    print(f"  Months at property: {tp.get('months_at_property',0)}")
    if tp.get("landlord_or_owner"): print(f"  Landlord/Owner: {tp.get('landlord_or_owner')}")

    print("\nRefund/Deposit:")
    if tp.get("direct_deposit", False):
        print(f"  Direct deposit: YES ({tp.get('bank_account_type','checking')})")
        print(f"  Routing: {tp.get('bank_routing','')}  Account: {tp.get('bank_account','')}")
    else:
        print("  Direct deposit: NO")
    print("======================================\n")

def review_and_edit(tp: Dict, w2s: List[Dict]):
    while True:
        show_summary(tp, w2s)
        print("Edit menu:")
        print("  1) Personal & address")
        print("  2) Dependents")
        print("  3) W-2s")
        print("  4) Other income")
        print("  5) Adjustments & deductions")
        print("  6) NJ rent / property tax")
        print("  7) Refund preferences")
        print("  8) Continue to compute")
        choice = prompt_int("Choose 1–8", 8)
        if choice == 1:   edit_personal(tp)
        elif choice == 2: deps = collect_dependents(); tp["dependents"] = deps
        elif choice == 3: edit_w2s(w2s)
        elif choice == 4: edit_other_income(tp)
        elif choice == 5: edit_adjustments(tp)
        elif choice == 6: edit_nj_property(tp)
        elif choice == 7: edit_refund_prefs(tp)
        elif choice == 8: return

# ---------- engines + main ----------

def load_engines():
    use_stub_fed = os.getenv("USE_STUB_FED", "0") == "1"
    use_stub_nj  = os.getenv("USE_STUB_NJ",  "0") == "1"
    if use_stub_fed:
        from engines.compute_federal import compute_federal as FED
    else:
        from engines.compute_federal_full import compute_federal as FED
    if use_stub_nj:
        from engines.compute_nj import compute_nj as NJ
    else:
        from engines.compute_nj_full import compute_nj as NJ
    return FED, NJ

def write_json(path: str, data: Dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def main():
    FED, NJ = load_engines()

    taxpayer = collect_personal_info()
    taxpayer["dependents"] = collect_dependents()
    w2s = collect_w2s()
    collect_other_income(taxpayer)
    collect_adjustments(taxpayer)
    collect_nj_property(taxpayer)
    collect_refund_prefs(taxpayer)

    # Review & edit before computing
    review_and_edit(taxpayer, w2s)

    fed_raw = FED(taxpayer, w2s)
    nj_raw  = NJ(taxpayer, w2s)

    write_json("out/out_f1040.json", {"inputs": taxpayer, "w2s": w2s, "lines": fed_raw})
    write_json("out/out_nj1040.json", {"inputs": taxpayer, "w2s": w2s, "lines": nj_raw})

    print("\n=== Federal Summary ===")
    wages   = sum(w.get("wages",0) for w in w2s)
    fed_tax = fed_raw.get("16", 0)
    fed_wh  = sum(w.get("federal_withheld",0) for w in w2s)
    print(f"Wages: {wages:,.2f} | Tax: {fed_tax:,.2f} | Withheld: {fed_wh:,.2f} | "
          f"Refund: {fed_raw.get('34',0):,.2f} | Owed: {fed_raw.get('37',0):,.2f}")
    print("Wrote out/out_f1040.json")

    print("\n=== NJ Summary ===")
    nj_wages = sum(w.get("nj_wages",0) for w in w2s)
    nj_tax   = nj_raw.get("16", 0)
    nj_wh    = sum(w.get("nj_withheld",0) for w in w2s)
    print(f"Wages: {nj_wages:,.2f} | Tax: {nj_tax:,.2f} | Withheld: {nj_wh:,.2f} | "
          f"Refund: {nj_raw.get('65',0):,.2f} | Owed: {nj_raw.get('66',0):,.2f}")
    print("Wrote out/out_nj1040.json\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)


