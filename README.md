# Balance Reconciler

Checks whether daily bank balances match the running total of transactions.

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

Each row shows the running balance from transactions vs. the bank's reported balance:

- **Green** — values match
- **Red** — mismatch detected (stops at first failure)
- **Yellow** — date has no corresponding bank record

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
