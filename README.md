# Balance Reconciler

Checks whether daily bank balances match the running total of transactions.

## How It Works (`main.py`)

`reconcile_data(tx_text, bank_text)` is the core function. It takes the raw CSV content of both files as strings and returns a structured result.

**1. Clean and parse transactions**
Each row's date and amount are stripped of whitespace and currency symbols. Amounts on the same date are summed together, so duplicate dates are collapsed into one total per day.

**2. Clean and parse bank balances**
Each row is loaded into a date-keyed dictionary. If the same date appears twice, an error is raised immediately — a bank statement should never have two balances for the same day.

**3. Opening balance check**
Before any comparison, the very first date is checked. If the transaction total on day one does not match the bank balance on day one, a warning is shown but reconciliation continues — the accountant can see the full picture and judge whether it's a prior period issue.

**4. Day-by-day comparison**
All dates from both files are merged and sorted. For each date the function accumulates a running balance from transactions and compares it against the bank's reported balance for that day:
- **OK** — running balance matches the bank
- **NO RECORD** — no bank entry for this date; running balance carries forward
- **MISMATCH** — discrepancy detected or the discrepancy amount changed from the previous day

**5. Discrepancy log**
After the row-by-row pass, a separate list records every date where a non-zero discrepancy first appeared or changed. Dates where the discrepancy returned to zero are excluded — zero means clean and does not belong in a discrepancy report.

**6. Summary**
Returns the final running balance, the final bank balance, the net discrepancy, and the discrepancy log — everything the UI needs to render the report.

## Setup

```bash
pip install flask
```

## Run

```bash
python server.py
```

Then open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

## Usage

1. Drop in your **transactions CSV** — must have `date` and `amount` columns. Duplicate dates are automatically combined.
2. Drop in your **bank balances CSV** — must have `date` and `balance` columns.
3. Click **Reconcile**.

### Report sections

**Summary cards** — Final running balance, final bank balance, and net discrepancy at a glance.

**Discrepancy Report** — A concise table showing every date a non-zero discrepancy appeared or changed, with the discrepancy amount. Resolutions back to zero are excluded.

**Day-by-Day Statement** — Full row-by-row breakdown (hidden by default, toggle with View Statement):
- **Green (OK)** — running balance matches the bank
- **Red (MISMATCH)** — running balance does not match the bank; the Discrepancy column shows the gap
- **Yellow (NO RECORD)** — date has a transaction but no corresponding bank entry

### Downloading

Click **Download Statement** to export a timestamped CSV containing both the reconciliation statement and the discrepancy report. The filename includes the date and time the report was generated (e.g. `reconciliation_statement_06-18-2026-14-32-05.csv`) so every download is uniquely identifiable.

## CSV Format

**transactions.csv**
```
date,amount
2025-06-01,1000.00
2025-06-02,-50.00
```

**bank_balances.csv**
```
date,balance
2025-06-01,1000.00
2025-06-02,950.00
```

## Edge Cases Covered

### Data Quality
| Case | Behaviour |
|---|---|
| Duplicate dates in transactions | Amounts are summed into a single entry before reconciling |
| Duplicate dates in bank balances | Rejected as a data error — bank statements should not have two balances for the same day |
| Opening balance mismatch | Warning shown above the report; reconciliation continues so the full period is still visible |
| Whitespace in values | Stripped from dates and amounts before parsing |
| Currency symbols (`$` `£` `€` `¥` `₹` `₩` `₪`) | Stripped before converting to a number |
| Comma-formatted numbers (`$1,000.00`) | Commas removed — values must be quoted in the CSV (`"$1,000.00"`) since unquoted commas are treated as column separators |

### Reconciliation Logic
| Case | Behaviour |
|---|---|
| Missing bank record for a date | Flagged as NO RECORD, running balance carries forward, reconciliation continues |
| Discrepancy that self-corrects | Shows MISMATCH while the gap is open; returns to OK once resolved |
| Discrepancy that persists unchanged | Continues to show MISMATCH with the same discrepancy amount each day |
| Discrepancy that changes amount mid-period | Continues as MISMATCH; the Discrepancy column reflects the updated gap amount |
| Discrepancy returning to zero | Excluded from the discrepancy report — zero means clean |
| Negative running balance | Handled correctly — compared against bank balance as-is |

## Running Tests

```bash
python run_tests.py
```

### Test Cases
| Test | What it covers |
|---|---|
| `all_match` | Happy path — all dates reconcile |
| `mismatch` | Single discrepancy that self-resolves |
| `diverge` | Discrepancy that carries forward unresolved |
| `complex_discrepancies` | Multi-discrepancy scenario: timing difference, persistent gap, changing gap, missing bank record |
| `duplicate_dates` | Duplicate transaction dates combined before comparison |
| `duplicate_bank_dates` | Duplicate bank dates rejected with error |
| `opening_mismatch` | Mismatched day-one balance shows warning and continues |
| `no_bank_record` | Missing bank entry handled gracefully |
| `negative_balance` | Running balance goes negative |
| `dirty_data` | Mixed currency symbols, whitespace, comma-formatted numbers |
