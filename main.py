import csv
import io
from collections import defaultdict


def reconcile_data(tx_text, bank_text):
    #get cummulative total of date in  transactions.csv
    totals = defaultdict(float)
    for row in csv.DictReader(io.StringIO(tx_text)):
        totals[row["date"]] += float(row["amount"])

    #get bank total of date
    bank = {}
    for row in csv.DictReader(io.StringIO(bank_text)):
        if row["date"] in bank:
            raise ValueError(f"Duplicate date in bank balances: {row['date']}")
        bank[row["date"]] = float(row["balance"])

    all_dates = sorted(set(totals) | set(bank))
    running_balance = 0.0
    all_match = True
    rows = []

    for d in all_dates:
        running_balance += totals.get(d, 0.0)
        bank_balance = bank.get(d)

        if bank_balance is None:
            rows.append({"date": d, "running": running_balance, "bank": None, "status": "NO_RECORD"})
            continue

        match = running_balance - bank_balance == 0.00
        status = "OK" if match else "MISMATCH"
        rows.append({"date": d, "running": running_balance, "bank": bank_balance, "status": status})

        if not match:
            all_match = False
            break

    return {"rows": rows, "all_match": all_match}


