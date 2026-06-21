# Balance Reconciliation Tool

A browser-based tool that compares a running transaction ledger against daily bank balances and produces a color-coded day-by-day reconciliation report. Upload two CSV files, click Reconcile, and immediately see which days match, which don't, and by how much.

---

## How It Works

The tool has three layers:

**`main.py` — reconciliation engine**
Reads both CSVs, sums all transaction amounts per date into a running balance, then compares that running balance against the bank's reported balance for each date. It returns a structured result containing a row for every date, a summary, and a list of the specific dates where discrepancies first appeared or changed.

**`server.py` — Flask backend**
Serves the single-page UI and exposes three endpoints:
- `POST /reconcile` — accepts the two uploaded files, runs the engine, returns JSON
- `POST /download/csv` — renders the result as a downloadable CSV report
- `POST /download/html` — renders the result as a downloadable styled HTML report

**HTML/JS frontend (embedded in `server.py`)**
All UI lives in a single HTML string served by Flask. No build step, no external dependencies. The browser sends files to `/reconcile`, receives JSON, and renders the results client-side. Downloads trigger a form POST so the browser handles the file save natively.

---

## Setup

**Requirements:** Python 3.8+, Flask

Install Flask if you don't already have it:

```bash
pip install flask
```

No other packages are required. The reconciliation engine (`main.py`) uses only the Python standard library.

---

## How to Run

```bash
python server.py
```

Then open your browser to:

```
http://localhost:5000
```

The server runs in debug mode on port 5000 by default.

---

## How to Use

1. **Drop or browse** your `transactions.csv` into the left upload zone.
2. **Drop or browse** your `bank_balances.csv` into the right upload zone.
3. The **Reconcile** button activates once both files are loaded — click it.
4. Results appear immediately below:
   - A **summary banner** (green = all clear, red = discrepancies found)
   - A **day-by-day table** with color-coded rows
5. Use **Download CSV** or **Download HTML** to save a report. Both filenames are timestamped, e.g. `reconciliation_20260618_143022.csv`.

You can re-upload different files and click Reconcile again without refreshing — results replace the previous run.

---

## CSV Format

### `transactions.csv`

One row per transaction. Multiple transactions on the same date are allowed and will be summed together.

| Column | Required | Description |
|--------|----------|-------------|
| `date` | Yes | Date of the transaction |
| `amount` | Yes | Transaction amount (positive = credit, negative = debit) |

```csv
date,amount
2024-01-01,1000.00
2024-01-02,250.00
2024-01-02,-75.00
2024-01-03,-200.00
```

### `bank_balances.csv`

One row per date representing the bank's end-of-day balance. Each date must be unique — duplicate dates are treated as a data error and the upload will be rejected.

| Column | Required | Description |
|--------|----------|-------------|
| `date` | Yes | Date of the balance snapshot |
| `balance` | Yes | End-of-day balance reported by the bank |

```csv
date,balance
2024-01-01,1000.00
2024-01-02,1175.00
2024-01-03,975.00
```

### Accepted number formats

The parser strips currency symbols and formatting before converting, so all of these are valid in either file:

```
1000
1000.00
1,000.00
$1,000.00
£1,000.00
€1,000.00
-250.50
-$250.50
$-250.50
```

Column headers are also whitespace-tolerant — `" date "` and `"date"` are treated identically.

### Date format

Dates are compared as strings after stripping whitespace. As long as both files use the same date format consistently, any format works (`2024-01-15`, `01/15/2024`, `Jan 15 2024`, etc.). The tool sorts dates lexicographically, so `YYYY-MM-DD` is strongly recommended for correct ordering.

---

## Understanding the Report

### Summary banner

Appears at the top of the results.

| Field | Description |
|-------|-------------|
| Final Running Balance | Sum of all transaction amounts across all dates |
| Final Bank Balance | The bank's balance on the last date that appears in the bank file |
| Net Discrepancy | Final Running Balance minus Final Bank Balance |
| Days Reviewed | Total number of distinct dates across both files |
| Days with Mismatch | Number of dates where a new or changed discrepancy was first detected |

If discrepancies exist, each affected date is listed as a pill below the stats, showing the discrepancy amount at that point in time.

A **yellow warning** appears when the very first date's running total doesn't match the bank's opening balance. This usually means there are transactions from a prior period that aren't included in the uploaded file. All subsequent rows may be offset by that opening gap.

### Day-by-day table

Each row represents one calendar date. Rows are sorted chronologically.

| Column | Description |
|--------|-------------|
| Date | The date |
| Running Balance | Cumulative sum of all transactions up to and including this date |
| Bank Balance | The bank's reported balance on this date (`—` if no bank record exists) |
| Discrepancy | Running Balance minus Bank Balance (`—` if no bank record) |
| Status | Match, Mismatch, or No Record (see below) |

**Row colors:**

| Color | Status | Meaning |
|-------|--------|---------|
| Green | Match | Running balance equals the bank balance exactly |
| Red | Mismatch | Running balance and bank balance differ |
| Grey | No Record | Date appears in transactions but has no corresponding bank entry |

### Downloaded reports

Both formats include the full summary and the day-by-day table. The HTML download is a self-contained file with inline styles — open it in any browser without needing the server running. The CSV download is structured with a summary section followed by the full row-level data, suitable for opening in Excel or any spreadsheet tool.

---

## Edge Cases Covered

| Scenario | Behavior |
|----------|----------|
| Multiple transactions on the same date | All amounts for that date are summed before comparing to the bank |
| Duplicate date in bank file | Rejected immediately with an error message naming the offending date |
| Date in transactions with no matching bank entry | Row status is `NO_RECORD`; running balance continues to accumulate; not counted as a mismatch |
| Date in bank with no matching transactions | Running balance carries forward unchanged; compared against the bank balance as normal |
| Negative running balance (overdraft) | Handled normally — compared against the bank balance as-is; recovers correctly if balance goes positive again |
| Opening balance mismatch | A yellow warning is shown; the gap typically carries forward through all subsequent rows |
| Discrepancy that resolves then re-appears | Counts as two distinct mismatch events, not one |
| Discrepancy that changes value without resolving | Each change in gap amount increments the mismatch count and adds a new entry to the discrepancy log |
| Persistent same-gap across multiple days | Counted as one mismatch event regardless of how many days it spans |
| Currency symbols in amounts | Stripped before parsing (`$`, `£`, `€`, `¥`, `₹`, `₩`, `₪`, etc.) |
| Comma-formatted numbers | Commas removed before parsing (`$1,500.00` → `1500.00`) |
| Whitespace around values or headers | Stripped from column names and all cell values before processing |
| Negative amounts prefixed with `-` | Parsed correctly as negative (`-$250.50`, `$-250.50`) |
| Zero-amount transactions | Treated as valid no-ops; running balance is unaffected |
| Unsorted input rows | Both CSVs are sorted chronologically internally; row order in the input files does not matter |
| Empty CSVs (headers only, no data rows) | Returns a clean empty result with no rows, no mismatches, and no crash |
| No bank records at all | All transaction dates marked `NO_RECORD`; `net_discrepancy` is `None`; `all_match` remains `True` |
| Floating point accumulation | Discrepancy is rounded to two decimal places at comparison time, absorbing minor float drift |
| BOM in UTF-8 files (Excel exports) | Handled automatically — files are decoded as `utf-8-sig` |

---

## Running the Tests

```bash
pip install pytest
python -m pytest test_reconcile.py -v
```

49 tests across 15 scenarios. All test the core reconciliation engine in `main.py` directly, independent of Flask.

---

## Assumptions

- **The running balance starts at zero.** There is no concept of a prior-period carried balance. The running balance is built entirely from the transactions provided. If your export starts mid-period, the opening mismatch warning will fire and all rows may show a consistent offset equal to whatever was missing from before the export window.

- **Dates are sorted lexicographically.** The tool does not parse or validate date formats — it compares them as strings and sorts them with Python's default string sort. `YYYY-MM-DD` is the only format that guarantees correct chronological ordering.

- **Duplicate transaction dates are intentional and valid.** It is normal to have multiple transactions in one day. Duplicate bank dates are treated as a data error because each bank entry represents a single end-of-day snapshot.

- **A discrepancy that persists unchanged across multiple days counts as one discrepancy event, not one per day.** The mismatch count and discrepancy log record the date a new gap appears or an existing gap changes amount — not every day the gap exists. This keeps the summary focused on where something went wrong, not how long it lingered.

- **No bank record is not the same as a mismatch.** If a date exists in transactions but not in the bank file, the tool flags it as `NO_RECORD` and skips it for match/mismatch counting. This is intentional — the bank simply may not report a balance every single day (weekends, holidays, etc.).

- **The discrepancy column shows running balance minus bank balance.** A positive discrepancy means the ledger is higher than the bank; a negative discrepancy means the bank is higher than the ledger.

- **The tool is tolerant of imperfect CSV formatting.** Real-world exports from accounting software, banks, and spreadsheets are not always consistent. Column headers may have surrounding whitespace. Amount fields may include currency symbols (`$`, `£`, `€`, etc.), thousands separators (`,`), and mixed formatting. The tool strips all of this before parsing so that files from different sources can be compared without manual cleanup. If an amount cell cannot be reduced to a valid number after cleaning, the row is rejected with an error identifying the offending date and value.

- **Negatives are denoted with a leading minus sign (`-`).** Accounting notation using parentheses for negatives — e.g. `(250.00)` — is not supported. Amounts must use `-250.00` or `-$250.00` format.

- **CSV files must have a header row.** A completely empty file (no headers, no data) is rejected. A file with only a header row and no data rows is valid and produces an empty result.

