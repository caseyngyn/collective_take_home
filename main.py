import csv
import io
import re
from collections import defaultdict
from typing import Any
from dateutil import parser as dateutil_parser


def _clean_number(value: str) -> float:
    """
    strips whitespace, currency symbols ($£€¥₹₩₪ etc), and commas from formatted numbers
    supports: leading minus (-250.00), accounting parens ((250.00)), trailing minus (250.00-)
    params: value (str) — raw cell value from CSV
    returns: float
    """
    stripped = value.strip()
    # edge case: accounting parens mean negative: (250.00) → -250.00
    if stripped.startswith('(') and stripped.endswith(')'):
        stripped = '-' + stripped[1:-1]
    cleaned = re.sub(r'[^\d.\-]', '', stripped)
    # edge case: trailing minus means negative: 250.00- → -250.00
    if cleaned.endswith('-') and not cleaned.startswith('-'):
        cleaned = '-' + cleaned[:-1]
    try:
        return float(cleaned)
    except ValueError:
        raise ValueError(f"Cannot parse amount from value: {value!r}")


def _parse_date(raw: str) -> str:
    """
    validates and normalizes a raw date cell to YYYY-MM-DD
    raises: ValueError for empty or placeholder values (e.g. "N/A", "-")
    """
    date = raw.strip()
    if not date or not any(c.isdigit() for c in date):
        raise ValueError(f"invalid date value: {date!r}")
    return dateutil_parser.parse(date).strftime("%Y-%m-%d")


def _make_reader(text: str) -> csv.DictReader:
    """
    wraps text in a DictReader and strips whitespace from column headers
    params: text (str) — full CSV text
    returns: csv.DictReader ready to iterate
    raises: ValueError if the CSV has no header row
    """
    reader = csv.DictReader(io.StringIO(text))
    # user uploaded empty file
    if reader.fieldnames is None:
        raise ValueError("CSV has no header row")
    reader.fieldnames = [f.strip() for f in reader.fieldnames]
    # after stripping, headers could all be blank (e.g. a row of just commas)
    if not any(reader.fieldnames):
        raise ValueError("CSV has no header row")
    return reader


def _parse_totals(tx_text: str) -> defaultdict[str, float]:
    """
    sums transaction amounts per date from a transactions CSV string
    params: tx_text (str) — full CSV text with 'date' and 'amount' columns
    returns: defaultdict(float) keyed by date string, value is net amount for that date
    """
    totals: defaultdict[str, float] = defaultdict(float)
    for row in _make_reader(tx_text):
        try:
            date = _parse_date(row["date"])
            totals[date] += _clean_number(row["amount"])
        except (ValueError, KeyError, AttributeError) as e:
            raise ValueError(f"Row {(row.get('date') or '').strip() or 'unknown'}: {e}") from e
    return totals


def _parse_bank(bank_text: str) -> dict[str, float]:
    """
    parses bank balance snapshots from a bank balances CSV string
    params: bank_text (str) — full CSV text with 'date' and 'balance' columns
    returns: dict keyed by date string, value is the bank balance for that date
    raises: ValueError if the same date appears more than once
    """
    bank: dict[str, float] = {}
    for row in _make_reader(bank_text):
        try:
            date = _parse_date(row["date"])
            balance = _clean_number(row["balance"])
        except (ValueError, KeyError, AttributeError) as e:
            raise ValueError(f"Row {(row.get('date') or '').strip() or 'unknown'}: {e}") from e
        if date in bank:
            raise ValueError(f"Duplicate date in bank balances: {date}")
        bank[date] = balance
    return bank


def _opening_warning(first_date: str, opening_tx: float, opening_bank: float | None) -> str | None:
    """
    checks whether the first date's transaction total matches the bank's opening balance
    params: first_date (str) — earliest date across both inputs
            opening_tx (float) — sum of transactions on that date
            opening_bank (float | None) — bank balance on that date, or None if absent
    returns: str warning message if there is a mismatch, None otherwise
    """
    if opening_bank is not None and round(opening_tx - opening_bank, 2) != 0:
        return (
            f"Opening balance mismatch on {first_date}: "
            f"transactions show {opening_tx:.2f}, bank shows {opening_bank:.2f}. "
            f"Results may be affected by a prior period issue."
        )
    return None


def _evaluate_discrepancy(
    discrepancy: float,
    open_discrepancy: float | None,
    mismatch_count: int,
) -> tuple[str, float | None, int]:
    """
    determines the status for a single date and updates mismatch tracking state
    params: discrepancy (float) — running balance minus bank balance for this date
            open_discrepancy (float | None) — the active gap amount from prior dates;
                                              None means the last comparison was clean
            mismatch_count (int) — running count of distinct discrepancy events so far
    returns: tuple of (status (str), new_open_discrepancy (float | None), new_mismatch_count (int))
    """
    if discrepancy == 0:
        return "OK", None, mismatch_count
    # same gap as the prior date — continuation, not a new event, so mismatch_count stays unchanged
    if discrepancy == open_discrepancy:
        return "MISMATCH", open_discrepancy, mismatch_count
    return "MISMATCH", discrepancy, mismatch_count + 1

# main logic
def reconcile_data(tx_text: str, bank_text: str, starting_balance: float = 0.0) -> dict[str, Any]:
    # guard against callers passing bytes or None (Flask file.read() returns bytes if not decoded)
    if not isinstance(tx_text, str) or not isinstance(bank_text, str):
        raise TypeError("tx_text and bank_text must be strings")

    totals = _parse_totals(tx_text)
    bank = _parse_bank(bank_text)

    all_dates = sorted(set(totals) | set(bank))

    # both files had headers but no data rows
    if not all_dates:
        return {"rows": [], "mismatch_count": 0, "warning": None,
                "summary": {"starting_balance": starting_balance, "final_running_balance": starting_balance,
                             "final_bank_balance": None, "net_discrepancy": None, "discrepancies": []}}

    first_date = all_dates[0]
    warning = _opening_warning(first_date, starting_balance + totals.get(first_date, 0.0), bank.get(first_date))

    running_balance = starting_balance
    mismatch_count = 0
    open_discrepancy: float | None = None # used by _evaluate_discrepancy to decide whether a non-zero discrepancy is a continuation
    last_seen_discrepancy = 0.0
    final_bank_balance: float | None = None
    rows: list[dict[str, Any]] = []
    discrepancy_log: list[dict[str, Any]] = []

    for d in all_dates:
        # default 0.0 handles dates that appear only in the bank file — running balance carries forward
        running_balance += totals.get(d, 0.0)
        bank_balance = bank.get(d)

        # date exists in transactions but not bank — not a mismatch, just no snapshot for that day
        if bank_balance is None:
            rows.append({"date": d, "running": running_balance, "bank": None, "status": "NO_RECORD", "discrepancy": None})
            continue

        final_bank_balance = bank_balance
        # round to 2 decimals to absorb float accumulation drift across many additions
        discrepancy = round(running_balance - bank_balance, 2)

        # only log when the gap appears or changes — prevents a persistent gap from creating an entry every day
        if discrepancy != 0 and discrepancy != last_seen_discrepancy:
            discrepancy_log.append({"date": d, "discrepancy": discrepancy})
        last_seen_discrepancy = discrepancy

        status, open_discrepancy, mismatch_count = _evaluate_discrepancy(discrepancy, open_discrepancy, mismatch_count)
        rows.append({"date": d, "running": running_balance, "bank": bank_balance, "status": status, "discrepancy": discrepancy})

    net_discrepancy = round(running_balance - final_bank_balance, 2) if final_bank_balance is not None else None

    return {
        "rows": rows,
        "mismatch_count": mismatch_count,
        "warning": warning,
        "summary": {
            "starting_balance": starting_balance,
            "final_running_balance": running_balance,
            "final_bank_balance": final_bank_balance,
            "net_discrepancy": net_discrepancy,
            "discrepancies": discrepancy_log,
        },
    }
