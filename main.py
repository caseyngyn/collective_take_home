import csv
import io
import re
from collections import defaultdict


def clean_number(value):
    # strips whitespace, currency symbols ($£€¥₹₩₪ etc), and commas from formatted numbers
    return float(re.sub(r'[^\d.\-]', '', value.strip()))



def reconcile_data(tx_text, bank_text):
    # sum amounts per date so duplicate transaction dates are combined
    totals = defaultdict(float)
    tx_reader = csv.DictReader(io.StringIO(tx_text))
    tx_reader.fieldnames = [f.strip() for f in tx_reader.fieldnames]
    for row in tx_reader:
        totals[row["date"].strip()] += clean_number(row["amount"])

    bank = {}
    bk_reader = csv.DictReader(io.StringIO(bank_text))
    bk_reader.fieldnames = [f.strip() for f in bk_reader.fieldnames]
    for row in bk_reader:
        date = row["date"].strip()
        # duplicate dates in bank balances are a data error — reject immediately
        if date in bank:
            raise ValueError(f"Duplicate date in bank balances: {date}")
        bank[date] = clean_number(row["balance"])

    all_dates = sorted(set(totals) | set(bank))

    # warn if day one doesn't agree — results may reflect a prior period issue
    first_date   = all_dates[0]
    opening_tx   = totals.get(first_date, 0.0)
    opening_bank = bank.get(first_date)
    warning = None
    if opening_bank is not None and round(opening_tx - opening_bank, 2) != 0:
        warning = (
            f"Opening balance mismatch on {first_date}: "
            f"transactions show {opening_tx:.2f}, bank shows {opening_bank:.2f}. "
            f"Results may be affected by a prior period issue."
        )

    running_balance = 0.0
    all_match = True
    mismatch_count = 0
    last_discrepancy = None
    prev_discrepancy = 0.0
    final_bank_balance = None
    rows = []
    discrepancy_log = []

    for d in all_dates:
        running_balance += totals.get(d, 0.0)
        bank_balance = bank.get(d)

        # date exists in transactions but not in bank — flag and continue
        if bank_balance is None:
            rows.append({"date": d, "running": running_balance, "bank": None, "status": "NO_RECORD", "discrepancy": None})
            continue

        final_bank_balance = bank_balance
        discrepancy = round(running_balance - bank_balance, 2)

        # log when a non-zero discrepancy appears or changes — zero means clean, not a discrepancy
        if discrepancy != 0 and discrepancy != prev_discrepancy:
            discrepancy_log.append({"date": d, "discrepancy": discrepancy})

        prev_discrepancy = discrepancy

        if discrepancy == 0:
            status = "OK"
            last_discrepancy = None
        elif discrepancy == last_discrepancy:
            status = "MISMATCH"
        else:
            # new discrepancy or gap amount changed
            status = "MISMATCH"
            mismatch_count += 1
            all_match = False
            last_discrepancy = discrepancy

        rows.append({"date": d, "running": running_balance, "bank": bank_balance, "status": status, "discrepancy": discrepancy})

    net_discrepancy = round(running_balance - final_bank_balance, 2) if final_bank_balance is not None else None

    return {
        "rows": rows,
        "all_match": all_match,
        "mismatch_count": mismatch_count,
        "warning": warning,
        "summary": {
            "final_running_balance": running_balance,
            "final_bank_balance": final_bank_balance,
            "net_discrepancy": net_discrepancy,
            "discrepancies": discrepancy_log,
        },
    }
