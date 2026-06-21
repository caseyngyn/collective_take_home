import csv
import io
import re
from collections import defaultdict
from typing import Any


def clean_number(value: str) -> float:
    # strips whitespace, currency symbols ($£€¥₹₩₪ etc), and commas from formatted numbers
    # params: value (str) — raw cell value from CSV
    # returns: float
    cleaned = re.sub(r'[^\d.\-]', '', value.strip())
    if not cleaned or cleaned in ('.', '-'):
        raise ValueError(f"Cannot parse amount from value: {value!r}")
    try:
        return float(cleaned)
    except ValueError:
        raise ValueError(f"Cannot parse amount from value: {value!r}")


def _make_reader(text: str) -> csv.DictReader:
    # wraps text in a DictReader and strips whitespace from column headers
    # params: text (str) — full CSV text
    # returns: csv.DictReader ready to iterate
    # raises: ValueError if the CSV has no header row
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CSV has no header row")
    reader.fieldnames = [f.strip() for f in reader.fieldnames]
    return reader


def _parse_totals(tx_text: str) -> defaultdict[str, float]:
    # sums transaction amounts per date from a transactions CSV string
    # params: tx_text (str) — full CSV text with 'date' and 'amount' columns
    # returns: defaultdict(float) keyed by date string, value is net amount for that date
    totals: defaultdict[str, float] = defaultdict(float)
    for row in _make_reader(tx_text):
        date = row["date"].strip()
        try:
            totals[date] += clean_number(row["amount"])
        except ValueError as e:
            raise ValueError(f"Row {date}: {e}") from e
    return totals


def _parse_bank(bank_text: str) -> dict[str, float]:
    # parses bank balance snapshots from a bank balances CSV string
    # params: bank_text (str) — full CSV text with 'date' and 'balance' columns
    # returns: dict keyed by date string, value is the bank balance for that date
    # raises: ValueError if the same date appears more than once
    bank: dict[str, float] = {}
    for row in _make_reader(bank_text):
        date = row["date"].strip()
        if date in bank:
            raise ValueError(f"Duplicate date in bank balances: {date}")
        try:
            bank[date] = clean_number(row["balance"])
        except ValueError as e:
            raise ValueError(f"Row {date}: {e}") from e
    return bank


def _opening_warning(first_date: str, opening_tx: float, opening_bank: float | None) -> str | None:
    # checks whether the first date's transaction total matches the bank's opening balance
    # params: first_date (str) — earliest date across both inputs
    #         opening_tx (float) — sum of transactions on that date
    #         opening_bank (float | None) — bank balance on that date, or None if absent
    # returns: str warning message if there is a mismatch, None otherwise
    if opening_bank is not None and round(opening_tx - opening_bank, 2) != 0:
        return (
            f"Opening balance mismatch on {first_date}: "
            f"transactions show {opening_tx:.2f}, bank shows {opening_bank:.2f}. "
            f"Results may be affected by a prior period issue."
        )
    return None


def _classify(
    discrepancy: float,
    open_discrepancy: float | None,
    mismatch_count: int,
) -> tuple[str, float | None, int]:
    # determines the status for a single date and updates mismatch tracking state
    # params: discrepancy (float) — running balance minus bank balance for this date
    #         open_discrepancy (float | None) — the active gap amount from prior dates;
    #                                           None means the last comparison was clean
    #         mismatch_count (int) — running count of distinct discrepancy events so far
    # returns: tuple of (status (str), new_open_discrepancy (float | None), new_mismatch_count (int))
    if discrepancy == 0:
        return "OK", None, mismatch_count
    if discrepancy == open_discrepancy:
        return "MISMATCH", open_discrepancy, mismatch_count
    return "MISMATCH", discrepancy, mismatch_count + 1

# main logic
def reconcile_data(tx_text: str, bank_text: str) -> dict[str, Any]:
    if not isinstance(tx_text, str) or not isinstance(bank_text, str):
        raise TypeError("tx_text and bank_text must be strings")

    totals = _parse_totals(tx_text)
    bank = _parse_bank(bank_text)

    all_dates = sorted(set(totals) | set(bank))

    if not all_dates:
        return {"rows": [], "mismatch_count": 0, "warning": None,
                "summary": {"final_running_balance": 0.0, "final_bank_balance": None,
                             "net_discrepancy": None, "discrepancies": []}}

    first_date = all_dates[0]
    warning = _opening_warning(first_date, totals.get(first_date, 0.0), bank.get(first_date))

    running_balance = 0.0
    mismatch_count = 0
    open_discrepancy: float | None = None # used by _classify to decide whether a non-zero discrepancy is a continuation
    last_seen_discrepancy = 0.0 #  what was the discrepancy on the previous date? avoid duplicate entries in discrepancy_log
    final_bank_balance: float | None = None
    rows: list[dict[str, Any]] = []
    discrepancy_log: list[dict[str, Any]] = []

    for d in all_dates:
        running_balance += totals.get(d, 0.0)
        bank_balance = bank.get(d)

        if bank_balance is None:
            rows.append({"date": d, "running": running_balance, "bank": None, "status": "NO_RECORD", "discrepancy": None})
            continue

        final_bank_balance = bank_balance
        discrepancy = round(running_balance - bank_balance, 2)

        if discrepancy != 0 and discrepancy != last_seen_discrepancy:
            discrepancy_log.append({"date": d, "discrepancy": discrepancy})
        last_seen_discrepancy = discrepancy

        status, open_discrepancy, mismatch_count = _classify(discrepancy, open_discrepancy, mismatch_count)
        rows.append({"date": d, "running": running_balance, "bank": bank_balance, "status": status, "discrepancy": discrepancy})

    net_discrepancy = round(running_balance - final_bank_balance, 2) if final_bank_balance is not None else None

    return {
        "rows": rows,
        "mismatch_count": mismatch_count,
        "warning": warning,
        "summary": {
            "final_running_balance": running_balance,
            "final_bank_balance": final_bank_balance,
            "net_discrepancy": net_discrepancy,
            "discrepancies": discrepancy_log,
        },
    }
