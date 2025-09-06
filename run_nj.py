import os
import sys
import csv
import json
# Toggle: set USE_STUB_NJ=1 to use the stub; anything else uses full logic
if os.getenv("USE_STUB_NJ", "0") == "1":
    from engines.compute_nj import compute_nj                    # <-- your existing STUB
else:
    from engines.compute_nj_full import compute_nj               # <-- NEW full version

try:
    from engines.compute_nj import compute_nj
except Exception as e:
    print("Import error for engines.compute_nj:", e)
    sys.exit(1)

def read_first_row(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        r = csv.DictReader(f)
        for row in r:
            return row
    raise ValueError(f"No rows in {path}")

def read_rows(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

def main():
    if len(sys.argv) < 3:
        print("Usage: python run_nj.py <taxpayer_csv> <w2_csv> [out_json]")
        print("Example: python run_nj.py samples\\samples_nj_taxpayer.csv samples\\samples_nj_w2.csv out_nj1040.json")
        sys.exit(2)

    tp_csv, w2_csv = sys.argv[1], sys.argv[2]
    out_json = sys.argv[3] if len(sys.argv) > 3 else None

    taxpayer = read_first_row(tp_csv)
    w2s = read_rows(w2_csv)

    result = compute_nj(taxpayer, w2s)

    # Try common keys; fall back to printing the dict
    wages    = result.get("wages", result.get("nj_wages"))
    tax      = result.get("tax", result.get("tax_due", result.get("total_tax")))
    withheld = result.get("withheld", result.get("nj_withheld"))
    refund   = result.get("refund", result.get("overpayment"))
    owed     = result.get("balance_due", result.get("amount_owed"))

    print("=== NJ Summary ===")
    if any(v is not None for v in [wages, tax, withheld, refund, owed]):
        print(f"Wages: {wages} | Tax: {tax} | Withheld: {withheld} | Refund: {refund} | Owed: {owed}")
    else:
        # Unknown key names? just show the whole dict.
        print(json.dumps(result, indent=2))

    if out_json:
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print("Wrote", out_json)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERROR:", e)
        sys.exit(1)
