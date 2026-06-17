# Balance Reconciler

Checks whether daily bank balances match the running total of transactions.

## How It Works (`main.py`)

`reconcile_data(tx_text, bank_text)` is the core function. It takes the raw CSV content of both files as strings and returns a structured result.

**1. Clean and parse transactions**
Each row's date and amount are stripped of whitespace and currency symbols. Amounts on the same date are summed together, so duplicate dates are collapsed into one total per day.

**2. Clean and parse bank balances**
Each row is loaded into a date-keyed dictionary. If the same date appears twice, an error is raised immediately — a bank statement should never have two balances for the same day.

**3. Opening balance check**
Before any comparison, the very first date is checked. If the transaction total on day one does not match the bank balance on day one, reconciliation halts with a clear error. A bad starting point would make every subsequent row meaningless.

**4. Day-by-day comparison**
All dates from both files are merged and sorted. For each date the function accumulates a running balance from transactions and compares it against the bank's reported balance for that day:
- **OK** — running balance matches the bank
- **NO RECORD** — no bank entry for this date; running balance carries forward
- **MISMATCH** — discrepancy detected, or the discrepancy amount changed from the previous day
- **DIVERGE** — same discrepancy as the previous day, carrying forward unchanged

**5. Gap detection**
After the row-by-row pass, the function groups consecutive MISMATCH and DIVERGE rows into gaps. Each gap records when it started, when (if) it resolved, and the amount off. A gap that self-corrects back to OK is likely a timing difference; one that never resolves needs investigation.

**6. Summary**
Returns the final running balance, the final bank balance, the net discrepancy, and the list of gaps — everything the UI needs to render the report.

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

Each row in the day-by-day log shows the cumulative running balance from transactions vs. the bank's reported balance:

- **Green (OK)** — running balance matches the bank
- **Red (MISMATCH)** — new discrepancy detected, or the discrepancy amount changed
- **Orange (DIVERGE)** — same discrepancy as the previous day, carrying forward unchanged
- **Yellow (NO RECORD)** — date has a transaction but no corresponding bank entry

The **Discrepancy Report** groups mismatches into gaps showing when each started, when (if) it resolved, and how much is off.

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
| Opening balance mismatch | Halts immediately before processing any further rows — every subsequent comparison would be poisoned by a bad starting point |
| Whitespace in values | Stripped from dates and amounts before parsing |
| Currency symbols (`$` `£` `€` `¥` `₹` `₩` `₪`) | Stripped before converting to a number |
| Comma-formatted numbers (`$1,000.00`) | Commas removed — values must be quoted in the CSV (`"$1,000.00"`) since unquoted commas are treated as column separators |

### Reconciliation Logic
| Case | Behaviour |
|---|---|
| Missing bank record for a date | Flagged as NO RECORD, running balance carries forward, reconciliation continues |
| Discrepancy on one day that self-corrects | MISMATCH → DIVERGE → OK; recorded as a resolved gap (likely a timing difference) |
| Discrepancy that persists unchanged | MISMATCH followed by DIVERGE rows; recorded as an unresolved gap |
| Discrepancy that changes amount mid-period | Each change triggers a new MISMATCH and opens a new gap; the prior gap is closed as unresolved |
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
| `complex_discrepancies` | Multi-gap scenario: timing difference, persistent gap, changing gap, missing bank record |
| `duplicate_dates` | Duplicate transaction dates combined before comparison |
| `duplicate_bank_dates` | Duplicate bank dates rejected with error |
| `opening_mismatch` | Mismatched day-one balance halts reconciliation |
| `no_bank_record` | Missing bank entry handled gracefully |
| `negative_balance` | Running balance goes negative |
| `dirty_data` | Mixed currency symbols, whitespace, comma-formatted numbers |
