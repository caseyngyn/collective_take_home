import csv
import io
import re
from collections import defaultdict


def clean_number(value):
    # strips whitespace, currency symbols ($£€¥₹₩₪ etc), and commas from formatted numbers
    return float(re.sub(r'[^\d.\-]', '', value.strip()))


def build_gaps(rows):
    gaps = []
    current_gap = None

    for row in rows:
        if row["status"] == "MISMATCH":
            # if a new mismatch starts while one is already open, close the old one as unresolved
            if current_gap:
                gaps.append(current_gap)
            current_gap = {
                "id": len(gaps) + 1,
                "started": row["date"],
                "resolved": None,
                "amount": row["discrepancy"],
            }
        elif row["status"] == "OK" and current_gap:
            # gap self-corrected — likely a timing difference
            current_gap["resolved"] = row["date"]
            gaps.append(current_gap)
            current_gap = None

    # gap still open at end of data — unresolved, needs investigation
    if current_gap:
        gaps.append(current_gap)

    return gaps


def reconcile_data(tx_text, bank_text):
    # sum amounts per date so duplicate transaction dates are combined
    totals = defaultdict(float)
    for row in csv.DictReader(io.StringIO(tx_text)):
        totals[row["date"].strip()] += clean_number(row["amount"])

    bank = {}
    for row in csv.DictReader(io.StringIO(bank_text)):
        date = row["date"].strip()
        # duplicate dates in bank balances are a data error — reject immediately
        if date in bank:
            raise ValueError(f"Duplicate date in bank balances: {date}")
        bank[date] = clean_number(row["balance"])

    all_dates = sorted(set(totals) | set(bank))

    # if day one doesn't agree, stop code
    first_date = all_dates[0]
    opening_tx   = totals.get(first_date, 0.0)
    opening_bank = bank.get(first_date)
    if opening_bank is not None and round(opening_tx - opening_bank, 2) != 0:
        raise ValueError(
            f"Opening balance mismatch on {first_date}: "
            f"transactions show {opening_tx:.2f}, bank shows {opening_bank:.2f}. "
            f"Resolve the starting balance before reconciling."
        )

    running_balance = 0.0
    all_match = True
    mismatch_count = 0
    last_discrepancy = None
    final_bank_balance = None
    rows = []

    for d in all_dates:
        running_balance += totals.get(d, 0.0)
        bank_balance = bank.get(d)

        # date exists in transactions but not in bank — flag and continue
        if bank_balance is None:
            rows.append({"date": d, "running": running_balance, "bank": None, "status": "NO_RECORD", "discrepancy": None})
            continue

        final_bank_balance = bank_balance
        discrepancy = round(running_balance - bank_balance, 2)

        if discrepancy == 0:
            status = "OK"
            last_discrepancy = None
        elif discrepancy == last_discrepancy:
            # same gap as yesterday — discrepancy is carrying forward unchanged
            status = "DIVERGE"
        else:
            # new discrepancy or the gap amount changed — open a new mismatch
            status = "MISMATCH"
            mismatch_count += 1
            all_match = False
            last_discrepancy = discrepancy

        rows.append({"date": d, "running": running_balance, "bank": bank_balance, "status": status, "discrepancy": discrepancy})

    gaps = build_gaps(rows)

    net_discrepancy = round(running_balance - final_bank_balance, 2) if final_bank_balance is not None else None

    return {
        "rows": rows,
        "all_match": all_match,
        "mismatch_count": mismatch_count,
        "summary": {
            "final_running_balance": running_balance,
            "final_bank_balance": final_bank_balance,
            "net_discrepancy": net_discrepancy,
            "gaps": gaps,
        },
    }
