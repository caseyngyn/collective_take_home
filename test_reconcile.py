import csv
import io
import pytest
from main import reconcile_data


# ── helpers ──────────────────────────────────────────────────────────────────

def tx(*rows):
    """Build a transactions CSV string from (date, amount) tuples."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "amount"])
    for d, a in rows:
        w.writerow([d, a])
    return buf.getvalue()


def bk(*rows):
    """Build a bank_balances CSV string from (date, balance) tuples."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "balance"])
    for d, b in rows:
        w.writerow([d, b])
    return buf.getvalue()


def statuses(result):
    return [r["status"] for r in result["rows"]]


def discrepancies(result):
    return [r["discrepancy"] for r in result["rows"]]


# ── 1. Complex statement ──────────────────────────────────────────────────────

class TestComplexStatement:
    """Multi-day ledger: mix of matches, a mid-period mismatch that resolves."""

    def test_row_count(self):
        t = tx(
            ("2024-01-01", "1000"),
            ("2024-01-02", "200"),
            ("2024-01-03", "-50"),
            ("2024-01-04", "300"),
            ("2024-01-05", "-100"),
        )
        b = bk(
            ("2024-01-01", "1000"),
            ("2024-01-02", "1200"),
            ("2024-01-03", "1150"),
            ("2024-01-04", "1450"),   # matches running 1450
            ("2024-01-05", "1400"),   # running 1350 ≠ 1400 → MISMATCH
        )
        result = reconcile_data(t, b)
        assert len(result["rows"]) == 5

    def test_all_ok_days(self):
        t = tx(
            ("2024-01-01", "1000"),
            ("2024-01-02", "200"),
            ("2024-01-03", "-50"),
            ("2024-01-04", "300"),
        )
        b = bk(
            ("2024-01-01", "1000"),
            ("2024-01-02", "1200"),
            ("2024-01-03", "1150"),
            ("2024-01-04", "1450"),
        )
        result = reconcile_data(t, b)
        assert result["mismatch_count"] == 0
        assert all(s == "OK" for s in statuses(result))

    def test_mismatch_detected(self):
        t = tx(
            ("2024-01-01", "1000"),
            ("2024-01-02", "200"),
            ("2024-01-03", "-50"),
            ("2024-01-04", "300"),
            ("2024-01-05", "-100"),
        )
        b = bk(
            ("2024-01-01", "1000"),
            ("2024-01-02", "1200"),
            ("2024-01-03", "1150"),
            ("2024-01-04", "1450"),
            ("2024-01-05", "1400"),  # running=1350, bank=1400 → -50 discrepancy
        )
        result = reconcile_data(t, b)
        assert result["mismatch_count"] > 0
        assert result["rows"][-1]["status"] == "MISMATCH"
        assert result["rows"][-1]["discrepancy"] == -50.0

    def test_summary_final_balances(self):
        t = tx(
            ("2024-01-01", "500"),
            ("2024-01-02", "250"),
        )
        b = bk(
            ("2024-01-01", "500"),
            ("2024-01-02", "750"),
        )
        result = reconcile_data(t, b)
        assert result["summary"]["final_running_balance"] == 750.0
        assert result["summary"]["final_bank_balance"] == 750.0
        assert result["summary"]["net_discrepancy"] == 0.0


# ── 2. Dirty data ─────────────────────────────────────────────────────────────

class TestDirtyData:
    """Currency symbols, commas, extra whitespace — all should be cleaned."""

    def test_dollar_signs_and_commas(self):
        t = tx(("2024-03-01", "$1,500.00"), ("2024-03-02", "$-200.00"))
        b = bk(("2024-03-01", "$1,500.00"), ("2024-03-02", "$1,300.00"))
        result = reconcile_data(t, b)
        assert result["mismatch_count"] == 0

    def test_whitespace_around_values(self):
        t = "date , amount\n 2024-03-01 ,  500 \n 2024-03-02 , 100 "
        b = "date , balance\n 2024-03-01 , 500 \n 2024-03-02 , 600 "
        result = reconcile_data(t, b)
        assert result["mismatch_count"] == 0

    def test_mixed_currency_symbols(self):
        # euro and pound symbols should be stripped
        t = tx(("2024-04-01", "€2,000"), ("2024-04-02", "£500"))
        b = bk(("2024-04-01", "2000"), ("2024-04-02", "2500"))
        result = reconcile_data(t, b)
        assert result["mismatch_count"] == 0

    def test_negative_with_symbol(self):
        t = tx(("2024-05-01", "$1,000"), ("2024-05-02", "-$250.50"))
        b = bk(("2024-05-01", "1000"), ("2024-05-02", "749.50"))
        result = reconcile_data(t, b)
        assert result["mismatch_count"] == 0
        assert round(result["summary"]["final_running_balance"], 2) == 749.50


# ── 3. Duplicate bank dates ───────────────────────────────────────────────────

class TestDuplicateBankDates:
    """Bank CSV with the same date twice must be rejected immediately."""

    def test_raises_value_error(self):
        t = tx(("2024-06-01", "100"))
        b = "date,balance\n2024-06-01,100\n2024-06-01,200"
        with pytest.raises(ValueError, match="Duplicate date in bank balances"):
            reconcile_data(t, b)

    def test_error_message_includes_date(self):
        t = tx(("2024-06-15", "500"))
        b = "date,balance\n2024-06-15,500\n2024-06-15,600"
        with pytest.raises(ValueError) as exc:
            reconcile_data(t, b)
        assert "2024-06-15" in str(exc.value)


# ── 4. Duplicate transaction dates ────────────────────────────────────────────

class TestDuplicateTransactionDates:
    """Multiple transaction rows on the same date should be summed."""

    def test_same_day_amounts_are_summed(self):
        t = "date,amount\n2024-07-01,300\n2024-07-01,200\n2024-07-01,100"
        b = bk(("2024-07-01", "600"))
        result = reconcile_data(t, b)
        assert result["mismatch_count"] == 0
        assert result["rows"][0]["running"] == 600.0

    def test_multi_day_with_duplicates(self):
        t = (
            "date,amount\n"
            "2024-07-01,500\n"
            "2024-07-01,500\n"   # day 1 total: 1000
            "2024-07-02,-100\n"
            "2024-07-02,-50\n"   # day 2 total: -150 → running 850
        )
        b = bk(("2024-07-01", "1000"), ("2024-07-02", "850"))
        result = reconcile_data(t, b)
        assert result["mismatch_count"] == 0
        assert result["rows"][1]["running"] == 850.0

    def test_duplicate_tx_mismatch_still_detected(self):
        t = "date,amount\n2024-08-01,400\n2024-08-01,400"  # sum=800
        b = bk(("2024-08-01", "750"))                       # bank=750
        result = reconcile_data(t, b)
        assert result["mismatch_count"] > 0
        assert result["rows"][0]["discrepancy"] == 50.0


# ── 5. Negative balance ───────────────────────────────────────────────────────

class TestNegativeBalance:
    """Running balance can go below zero (overdraft) and should still reconcile."""

    def test_overdraft_matches_bank(self):
        t = tx(("2024-09-01", "100"), ("2024-09-02", "-500"))
        b = bk(("2024-09-01", "100"), ("2024-09-02", "-400"))
        result = reconcile_data(t, b)
        assert result["mismatch_count"] == 0
        assert result["rows"][1]["running"] == -400.0

    def test_overdraft_mismatch(self):
        t = tx(("2024-09-01", "100"), ("2024-09-02", "-500"))
        b = bk(("2024-09-01", "100"), ("2024-09-02", "-350"))  # differs by -50
        result = reconcile_data(t, b)
        assert result["mismatch_count"] > 0
        assert result["rows"][1]["discrepancy"] == -50.0

    def test_recovery_from_negative(self):
        t = tx(
            ("2024-10-01", "200"),
            ("2024-10-02", "-500"),  # running = -300
            ("2024-10-03", "800"),   # running = 500
        )
        b = bk(
            ("2024-10-01", "200"),
            ("2024-10-02", "-300"),
            ("2024-10-03", "500"),
        )
        result = reconcile_data(t, b)
        assert result["mismatch_count"] == 0


# ── 6. No bank record ─────────────────────────────────────────────────────────

class TestNoBankRecord:
    """Dates that appear only in transactions have status NO_RECORD."""

    def test_status_is_no_record(self):
        t = tx(("2024-11-01", "500"), ("2024-11-02", "100"))
        b = bk(("2024-11-01", "500"))  # 2024-11-02 missing from bank
        result = reconcile_data(t, b)
        assert result["rows"][1]["status"] == "NO_RECORD"
        assert result["rows"][1]["bank"] is None

    def test_no_record_does_not_count_as_mismatch(self):
        t = tx(("2024-11-01", "500"), ("2024-11-02", "100"))
        b = bk(("2024-11-01", "500"))
        result = reconcile_data(t, b)
        # the only bank record matches, so mismatch_count should be 0
        assert result["mismatch_count"] == 0

    def test_running_balance_still_accumulates(self):
        t = tx(("2024-11-01", "500"), ("2024-11-02", "100"), ("2024-11-03", "50"))
        b = bk(("2024-11-01", "500"), ("2024-11-03", "650"))
        result = reconcile_data(t, b)
        # day 2 is NO_RECORD; day 3 running should be 650
        assert result["rows"][2]["running"] == 650.0
        assert result["rows"][2]["status"] == "OK"

    def test_multiple_missing_bank_dates(self):
        t = tx(
            ("2024-12-01", "100"),
            ("2024-12-02", "100"),
            ("2024-12-03", "100"),
        )
        b = bk(("2024-12-01", "100"))
        result = reconcile_data(t, b)
        assert statuses(result) == ["OK", "NO_RECORD", "NO_RECORD"]


# ── 7. Opening balance mismatch ───────────────────────────────────────────────

class TestOpeningBalanceMismatch:
    """If day-one running total ≠ day-one bank balance, a warning is emitted."""

    def test_warning_is_set(self):
        t = tx(("2024-01-01", "1000"))
        b = bk(("2024-01-01", "900"))   # bank thinks opening was 900
        result = reconcile_data(t, b)
        assert result["warning"] is not None

    def test_warning_contains_date(self):
        t = tx(("2024-01-01", "1000"))
        b = bk(("2024-01-01", "900"))
        result = reconcile_data(t, b)
        assert "2024-01-01" in result["warning"]

    def test_warning_mentions_both_values(self):
        t = tx(("2024-01-01", "1000"))
        b = bk(("2024-01-01", "900"))
        result = reconcile_data(t, b)
        assert "1000" in result["warning"] or "1000.00" in result["warning"]
        assert "900"  in result["warning"] or "900.00"  in result["warning"]

    def test_no_warning_when_opening_matches(self):
        t = tx(("2024-01-01", "1000"))
        b = bk(("2024-01-01", "1000"))
        result = reconcile_data(t, b)
        assert result["warning"] is None

    def test_mismatch_status_still_recorded(self):
        # opening mismatch means day-one discrepancy ≠ 0
        t = tx(("2024-01-01", "1000"), ("2024-01-02", "500"))
        b = bk(("2024-01-01", "900"), ("2024-01-02", "1400"))
        result = reconcile_data(t, b)
        assert result["rows"][0]["status"] == "MISMATCH"
        assert result["rows"][0]["discrepancy"] == 100.0

    def test_downstream_rows_inherit_prior_error(self):
        # opening is off by 100; subsequent days show same gap unless amount corrects it
        t = tx(("2024-01-01", "1000"), ("2024-01-02", "200"))
        b = bk(("2024-01-01", "900"), ("2024-01-02", "1100"))
        result = reconcile_data(t, b)
        # running=1200, bank=1100 → discrepancy=100 on day 2 as well
        assert result["rows"][1]["discrepancy"] == 100.0


# ── 8. Bank-only dates ────────────────────────────────────────────────────────

class TestBankOnlyDates:
    """Dates that appear only in the bank CSV (no transactions that day)."""

    def test_bank_only_date_matches_carried_balance(self):
        # Jun 2 has no transactions; running stays at 1000; bank also shows 1000 → OK
        t = tx(("2024-06-01", "1000"), ("2024-06-03", "-200"))
        b = bk(("2024-06-01", "1000"), ("2024-06-02", "1000"), ("2024-06-03", "800"))
        result = reconcile_data(t, b)
        assert result["rows"][1]["status"] == "OK"
        assert result["rows"][1]["running"] == 1000.0
        assert result["rows"][1]["bank"] == 1000.0

    def test_bank_only_date_mismatch(self):
        # bank shows a different balance on a day with no transactions — discrepancy
        t = tx(("2024-06-01", "1000"), ("2024-06-03", "-200"))
        b = bk(("2024-06-01", "1000"), ("2024-06-02", "950"), ("2024-06-03", "750"))
        result = reconcile_data(t, b)
        assert result["rows"][1]["status"] == "MISMATCH"
        assert result["rows"][1]["discrepancy"] == 50.0

    def test_bank_only_date_does_not_affect_running_balance(self):
        # running balance should not change on a bank-only day
        t = tx(("2024-06-01", "500"), ("2024-06-03", "100"))
        b = bk(("2024-06-01", "500"), ("2024-06-02", "500"), ("2024-06-03", "600"))
        result = reconcile_data(t, b)
        assert result["rows"][2]["running"] == 600.0
        assert result["mismatch_count"] == 0

    def test_multiple_consecutive_bank_only_dates(self):
        # several days with no transactions; running balance flat across all of them
        t = tx(("2024-06-01", "1000"), ("2024-06-05", "200"))
        b = bk(
            ("2024-06-01", "1000"),
            ("2024-06-02", "1000"),
            ("2024-06-03", "1000"),
            ("2024-06-04", "1000"),
            ("2024-06-05", "1200"),
        )
        result = reconcile_data(t, b)
        assert all(r["status"] == "OK" for r in result["rows"])


# ── 9. Discrepancy resolves then re-appears ───────────────────────────────────

class TestDiscrepancyResolvesAndReappears:
    """A gap that closes to zero and then opens again should count as two mismatches."""

    def test_mismatch_count_increments_on_reappearance(self):
        t = tx(
            ("2024-01-01", "1000"),
            ("2024-01-02", "-50"),   # running=950, bank=1000 → gap=-50
            ("2024-01-03", "50"),    # running=1000, bank=1000 → gap resolved
            ("2024-01-04", "-80"),   # running=920, bank=1000 → new gap=-80
        )
        b = bk(
            ("2024-01-01", "1000"),
            ("2024-01-02", "1000"),
            ("2024-01-03", "1000"),
            ("2024-01-04", "1000"),
        )
        result = reconcile_data(t, b)
        assert result["mismatch_count"] == 2

    def test_statuses_after_resolution_and_reappearance(self):
        t = tx(
            ("2024-01-01", "1000"),
            ("2024-01-02", "-50"),
            ("2024-01-03", "50"),
            ("2024-01-04", "-80"),
        )
        b = bk(
            ("2024-01-01", "1000"),
            ("2024-01-02", "1000"),
            ("2024-01-03", "1000"),
            ("2024-01-04", "1000"),
        )
        result = reconcile_data(t, b)
        assert statuses(result) == ["OK", "MISMATCH", "OK", "MISMATCH"]

    def test_discrepancy_log_has_two_entries(self):
        t = tx(
            ("2024-01-01", "1000"),
            ("2024-01-02", "-50"),
            ("2024-01-03", "50"),
            ("2024-01-04", "-80"),
        )
        b = bk(
            ("2024-01-01", "1000"),
            ("2024-01-02", "1000"),
            ("2024-01-03", "1000"),
            ("2024-01-04", "1000"),
        )
        result = reconcile_data(t, b)
        assert len(result["summary"]["discrepancies"]) == 2


# ── 10. Discrepancy changes value ─────────────────────────────────────────────

class TestDiscrepancyChangesValue:
    """A gap that shifts to a different non-zero amount is a new distinct problem."""

    def test_mismatch_count_increments_when_gap_changes(self):
        t = tx(
            ("2024-02-01", "1000"),
            ("2024-02-02", "-50"),   # running=950, bank=1000 → gap=-50
            ("2024-02-03", "-30"),   # running=920, bank=1000 → gap=-80 (changed)
        )
        b = bk(
            ("2024-02-01", "1000"),
            ("2024-02-02", "1000"),
            ("2024-02-03", "1000"),
        )
        result = reconcile_data(t, b)
        assert result["mismatch_count"] == 2

    def test_discrepancy_log_records_each_change(self):
        t = tx(
            ("2024-02-01", "1000"),
            ("2024-02-02", "-50"),
            ("2024-02-03", "-30"),
        )
        b = bk(
            ("2024-02-01", "1000"),
            ("2024-02-02", "1000"),
            ("2024-02-03", "1000"),
        )
        result = reconcile_data(t, b)
        log = result["summary"]["discrepancies"]
        assert len(log) == 2
        assert log[0]["discrepancy"] == -50.0
        assert log[1]["discrepancy"] == -80.0

    def test_persistent_same_gap_counts_as_one(self):
        # same gap three days in a row should be mismatch_count=1, log length=1
        t = tx(
            ("2024-02-01", "1000"),
            ("2024-02-02", "-50"),
            ("2024-02-03", "0"),
            ("2024-02-04", "0"),
        )
        b = bk(
            ("2024-02-01", "1000"),
            ("2024-02-02", "1000"),
            ("2024-02-03", "1000"),
            ("2024-02-04", "1000"),
        )
        result = reconcile_data(t, b)
        assert result["mismatch_count"] == 1
        assert len(result["summary"]["discrepancies"]) == 1


# ── 11. Empty inputs ──────────────────────────────────────────────────────────

class TestEmptyInputs:
    """CSVs with headers but zero data rows."""

    def test_truly_empty_csv_raises_value_error(self):
        with pytest.raises(ValueError, match="no header row"):
            reconcile_data("", "date,balance\n")
        with pytest.raises(ValueError, match="no header row"):
            reconcile_data("date,amount\n", "")

    def test_empty_transactions_empty_bank(self):
        t = "date,amount\n"
        b = "date,balance\n"
        result = reconcile_data(t, b)
        assert result["rows"] == []
        assert result["mismatch_count"] == 0
        assert result["warning"] is None

    def test_empty_transactions_valid_bank(self):
        # no tx rows; running balance stays 0; all bank entries compare against 0
        t = "date,amount\n"
        b = bk(("2024-03-01", "0"))
        result = reconcile_data(t, b)
        assert result["rows"][0]["running"] == 0.0
        assert result["rows"][0]["status"] == "OK"

    def test_valid_transactions_empty_bank(self):
        # no bank rows; every tx date gets NO_RECORD
        t = tx(("2024-03-01", "500"), ("2024-03-02", "200"))
        b = "date,balance\n"
        result = reconcile_data(t, b)
        assert all(r["status"] == "NO_RECORD" for r in result["rows"])
        assert result["mismatch_count"] == 0


# ── 12. No bank records at all (net_discrepancy is None) ──────────────────────

class TestNoBankRecordsAtAll:
    """When every date is TX-only, final_bank_balance and net_discrepancy are None."""

    def test_net_discrepancy_is_none(self):
        t = tx(("2024-04-01", "1000"), ("2024-04-02", "500"))
        b = "date,balance\n"
        result = reconcile_data(t, b)
        assert result["summary"]["net_discrepancy"] is None
        assert result["summary"]["final_bank_balance"] is None

    def test_no_mismatches_with_no_bank(self):
        # no bank records means no comparisons, so no mismatches
        t = tx(("2024-04-01", "1000"))
        b = "date,balance\n"
        result = reconcile_data(t, b)
        assert result["mismatch_count"] == 0

    def test_running_balance_still_computed(self):
        t = tx(("2024-04-01", "1000"), ("2024-04-02", "-200"))
        b = "date,balance\n"
        result = reconcile_data(t, b)
        assert result["summary"]["final_running_balance"] == 800.0


# ── 14. Unsorted input dates ──────────────────────────────────────────────────

class TestUnsortedInputDates:
    """Input rows out of chronological order should produce the same result as sorted."""

    def test_unsorted_transactions_match_bank(self):
        # transactions fed in reverse order
        t = (
            "date,amount\n"
            "2024-06-03,-200\n"
            "2024-06-01,1000\n"
            "2024-06-02,100\n"
        )
        b = bk(("2024-06-01", "1000"), ("2024-06-02", "1100"), ("2024-06-03", "900"))
        result = reconcile_data(t, b)
        assert result["mismatch_count"] == 0

    def test_unsorted_bank_dates(self):
        # bank rows fed out of order
        t = tx(("2024-06-01", "1000"), ("2024-06-02", "100"))
        b = (
            "date,balance\n"
            "2024-06-02,1100\n"
            "2024-06-01,1000\n"
        )
        result = reconcile_data(t, b)
        assert result["mismatch_count"] == 0

    def test_unsorted_row_order_matches_sorted_result(self):
        t_sorted = tx(("2024-06-01", "500"), ("2024-06-02", "300"))
        t_unsorted = "date,amount\n2024-06-02,300\n2024-06-01,500\n"
        b = bk(("2024-06-01", "500"), ("2024-06-02", "800"))
        r1 = reconcile_data(t_sorted, b)
        r2 = reconcile_data(t_unsorted, b)
        assert r1["mismatch_count"] == r2["mismatch_count"]
        assert r1["summary"]["net_discrepancy"] == r2["summary"]["net_discrepancy"]


# ── 15. Zero-amount transactions ──────────────────────────────────────────────

class TestZeroAmountTransactions:
    """A transaction row with amount 0 should be a no-op on the running balance."""

    def test_zero_amount_does_not_affect_balance(self):
        t = tx(("2024-07-01", "1000"), ("2024-07-02", "0"))
        b = bk(("2024-07-01", "1000"), ("2024-07-02", "1000"))
        result = reconcile_data(t, b)
        assert result["mismatch_count"] == 0
        assert result["rows"][1]["running"] == 1000.0

    def test_zero_string_variants(self):
        from main import clean_number
        assert clean_number("0") == 0.0
        assert clean_number("0.00") == 0.0
        assert clean_number("$0.00") == 0.0


# ── 16. Floating point accumulation ──────────────────────────────────────────

class TestFloatingPointAccumulation:
    """Many small fractional amounts can cause float drift in running_balance.
    The discrepancy is rounded at comparison time, which may mask or surface drift."""

    def test_many_small_amounts_match_bank(self):
        # 10 transactions of 0.1 each; naive float sum = 0.9999...8 not 1.0
        rows = [("2024-08-01", "0.1")] * 10
        t = tx(*rows)
        b = bk(("2024-08-01", "1.0"))
        result = reconcile_data(t, b)
        # rounding to 2 decimal places at comparison should absorb the drift
        assert result["rows"][0]["discrepancy"] == 0.0
        assert result["rows"][0]["status"] == "OK"

    def test_fractional_accumulation_over_multiple_days(self):
        # 0.1 per day for 3 days; running should be 0.1, 0.2, 0.3
        t = tx(("2024-08-01", "0.1"), ("2024-08-02", "0.1"), ("2024-08-03", "0.1"))
        b = bk(("2024-08-01", "0.1"), ("2024-08-02", "0.2"), ("2024-08-03", "0.3"))
        result = reconcile_data(t, b)
        assert result["rows"][0]["discrepancy"] == 0.0
        assert result["rows"][1]["discrepancy"] == 0.0
        assert result["rows"][2]["discrepancy"] == 0.0
