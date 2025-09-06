import os
# Toggle: set USE_STUB_FED=1 to use the stub; anything else uses full logic
if os.getenv("USE_STUB_FED", "0") == "1":
    from engines.compute_federal import compute_federal          # <-- your existing STUB
else:
    from engines.compute_federal_full import compute_federal     # <-- NEW full version


try:
    from engines.compute_federal import compute_federal
except Exception as e:
    print("Import error for engines.compute_federal:", e)
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
        print("Usage: python run_federal.py <taxpayer_csv> <w2_csv> [out_json]")
        print("Example: python run_federal.py samples\\samples_fed_taxpayer.csv samples\\samples_fed_w2.csv out_f1040.json")
        sys.exit(2)

    tp_csv, w2_csv = sys.argv[1], sys.argv[2]
    out_json = sys.argv[3] if len(sys.argv) > 3 else None

    taxpayer = read_first_row(tp_csv)
    w2s = read_rows(w2_csv)

    result = compute_federal(taxpayer, w2s)

    # Friendly summary (works with either the stub keys or future real keys)
    wages    = result.get("1z", result.get("wages"))
    tax      = result.get("16", result.get("tax_due"))
    withheld = result.get("25d", result.get("withheld"))
    refund   = result.get("34", result.get("refund"))
    owed     = result.get("37", result.get("balance_due"))

    print("=== Federal Summary ===")
    print(f"Wages: {wages} | Tax: {tax} | Withheld: {withheld} | Refund: {refund} | Owed: {owed}")

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
