# run_federal.py
# Usage:
#   python run_federal.py federal_taxpayer_template.csv nj_w2_template.csv [dependents_template.csv] [out.json]
#
# Reads your CSVs, validates/normalizes inputs, calls compute_federal(), and prints
# a neat summary + the 2024 Form 1040 line map. Optionally writes JSON.

import csv, json, re, sys
from typing import Dict, List

# ---- import your engine ----
try:
    from compute_federal import compute_federal, Taxpayer, W2, FS_SINGLE, FS_MFJ, FS_MFS, FS_HOH, FS_QW
except Exception as e:
    print("ERROR: could not import compute_federal. Is compute_federal.py in this folder?\n", e)
    sys.exit(1)

ALLOWED_FS = {FS_SINGLE, FS_MFJ, FS_MFS, FS_HOH, FS_QW}

SSN_RE = re.compile(r"^\d{3}-\d{2}-\d{4}$")
ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")  # YYYY-MM-DD

def to_float(x):
    if x is None: return 0.0
    s = str(x).strip()
    if s == "": return 0.0
    return float(s.replace("$","").replace(",",""))

def to_int(x):
    try:
        return int(str(x).strip())
    except:
        return 0

def read_taxpayer_csv(path: str) -> Dict:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("federal taxpayer CSV is empty")
    r = rows[0]

    fs = (r.get("filing_status") or "").strip()
    if fs not in ALLOWED_FS:
        raise ValueError(f"filing_status must be one of {sorted(ALLOWED_FS)}")

    def need(k, msg=None):
        v = (r.get(k) or "").strip()
        if not v:
            raise ValueError(msg or f"missing required field: {k}")
        return v

    primary_ssn = need("primary_ssn", "primary_ssn required (###-##-####)")
    if not SSN_RE.match(primary_ssn):
        raise ValueError("primary_ssn must match ###-##-####")

    primary_dob = need("primary_dob", "primary_dob required (YYYY-MM-DD)")
    if not DATE_RE.match(primary_dob):
        raise ValueError("primary_dob must be YYYY-MM-DD")

    z = need("zip", "zip (5-digit or ZIP+4)")
    if not ZIP_RE.match(z):
        raise ValueError("zip must be 5-digit (or ZIP+4)")

    # Spouse fields (only if MFJ/MFS/QW)
    spouse_first = (r.get("spouse_first") or "").strip()
    spouse_last  = (r.get("spouse_last") or "").strip()
    spouse_ssn   = (r.get("spouse_ssn") or "").strip()
    spouse_dob   = (r.get("spouse_dob") or "").strip()
    spouse_deceased_year = (r.get("spouse_deceased_year") or "").strip()

    if fs in (FS_MFJ, FS_MFS, FS_QW):
        if not spouse_first or not spouse_last or not spouse_ssn or not spouse_dob:
            raise ValueError("spouse_first/last/ssn/dob required for MFJ/MFS/QW")
        if not SSN_RE.match(spouse_ssn):
            raise ValueError("spouse_ssn must match ###-##-####")
        if not DATE_RE.match(spouse_dob):
            raise ValueError("spouse_dob must be YYYY-MM-DD")
        if fs == FS_QW and not spouse_deceased_year:
            raise ValueError("spouse_deceased_year required for QW")

    tp = {
        "filing_status": fs,
        "primary_first": need("primary_first"),
        "primary_last":  need("primary_last"),
        "primary_ssn":   primary_ssn,
        "primary_dob":   primary_dob,
        "address":       need("address"),
        "city":          need("city"),
        "state":         need("state"),
        "zip":           z,

        "spouse_first": spouse_first,
        "spouse_last":  spouse_last,
        "spouse_ssn":   spouse_ssn,
        "spouse_dob":   spouse_dob,
        "spouse_deceased_year": spouse_deceased_year,

        "phone": (r.get("phone") or "").strip(),
        "email": (r.get("email") or "").strip(),

        # EITC hooks
        "num_qualifying_children": to_int(r.get("num_qualifying_children")),
        "investment_income": to_float(r.get("investment_income")),

        # Income outside W-2s
        "interest_taxable": to_float(r.get("interest_taxable")),
        "dividends_ordinary": to_float(r.get("dividends_ordinary")),
        "dividends_qualified": to_float(r.get("dividends_qualified")),
        "unemployment_comp": to_float(r.get("unemployment_comp")),

        # Adjustments
        "student_loan_interest_paid": to_float(r.get("student_loan_interest_paid")),

        # Direct deposit (optional)
        "bank_routing": (r.get("bank_routing") or "").strip(),
        "bank_account": (r.get("bank_account") or "").strip(),
        "deposit_type": (r.get("deposit_type") or "").strip().lower(),
    }

    return tp

def read_w2_csv(path: str) -> List[Dict]:
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append({
                "wages_box1": to_float(r.get("wages_box1")),
                "fed_withheld_box2": to_float(r.get("fed_withheld_box2")),
            })
    if not out:
        raise ValueError("W-2 CSV is empty")
    return out

def read_dependents_csv(path: str) -> List[Dict]:
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append({
                "first": (r.get("first") or "").strip(),
                "last":  (r.get("last") or "").strip(),
                "ssn":   (r.get("ssn") or "").strip(),
                "dob":   (r.get("dob") or "").strip(),
                "relationship": (r.get("relationship") or "").strip(),
                "months_lived_with_you": to_int(r.get("months_lived_with_you")),
                "child_under_17": str(r.get("child_under_17") or "").strip().lower() in {"true","1","yes","y"},
            })
    return out

def main():
    tp_csv = sys.argv[1] if len(sys.argv) > 1 else "federal_taxpayer_template.csv"
    w2_csv = sys.argv[2] if len(sys.argv) > 2 else "nj_w2_template.csv"
    dep_csv = sys.argv[3] if len(sys.argv) > 3 else ""     # optional
    out_json = sys.argv[4] if len(sys.argv) > 4 else ""    # optional

    try:
        tp_dict = read_taxpayer_csv(tp_csv)
        w2_rows = read_w2_csv(w2_csv)
        deps = read_dependents_csv(dep_csv) if dep_csv else []
    except Exception as e:
        print("INPUT ERROR:", e)
        sys.exit(2)

    # Build dataclasses for compute_federal
    tp = Taxpayer(**tp_dict)
    w2s = [W2(**{"wages_box1": r["wages_box1"], "fed_withheld_box2": r["fed_withheld_box2"]}) for r in w2_rows]

    # (Optional) If you later implement full dependent-based credits, pass `deps` to your engine.

    out = compute_federal(tp, w2s)

    # Pretty print summary
    print("\n=== FEDERAL 1040 SUMMARY (TY 2024) ===")
    print(f" Filing Status : {tp.filing_status}")
    print(f" W-2 Wages (1z): ${out['1z']:,}")
    print(f" Interest (2b) : ${out['2b']:,}")
    print(f" Divs (3b)     : ${out['3b']:,} (Qualified 3a: ${out['3a']:,})")
    print(f" Unemployment  : ${out['8']:,} (Schedule 1 line 10)")
    print(f" AGI (11)      : ${out['11']:,}")
    print(f" Std Ded (12)  : ${out['12']:,}")
    print(f" Taxable (15)  : ${out['15']:,}")
    print(f" Tax (16)      : ${out['16']:,}")
    print(f" Withheld (25d): ${out['25d']:,}")
    print(f" EITC (27)     : ${out['27']:,}")
    if out['34'] > 0:
        print(f" Refund (34)   : ${out['34']:,}")
    else:
        print(f" Amount Owed(37): ${out['37']:,}")

    # Print line map sorted by line order (handles 1z, 2b, etc.)
    def sort_key(k: str):
        m = re.match(r"^(\d+)([a-z]*)$", k)
        if not m: return (9999, k)
        num = int(m.group(1))
        suf = m.group(2)
        add = 0.0
        if suf:
            add = (ord(suf[0]) - ord('a') + 1) / 10.0
        return (num + add, k)

    print("\n--- 1040 LINE MAP ---")
    for k in sorted([kk for kk in out.keys() if not kk.startswith("_")], key=sort_key):
        print(f" Line {k:>3}: {out[k]}")

    if out_json:
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        print(f"\nWrote JSON -> {out_json}")

if __name__ == "__main__":
    main()
