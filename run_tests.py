import json
import os
from main import reconcile_data

tests_dir = "tests"
passed = 0
failed = 0

for case in sorted(os.listdir(tests_dir)):
    case_dir = os.path.join(tests_dir, case)
    if not os.path.isdir(case_dir):
        continue

    tx_path = os.path.join(case_dir, "transactions.csv")
    bank_path = os.path.join(case_dir, "bank_balances.csv")
    expected_path = os.path.join(case_dir, "expected.json")

    with open(tx_path) as f:
        tx_text = f.read()
    with open(bank_path) as f:
        bank_text = f.read()
    with open(expected_path) as f:
        expected = json.load(f)

    try:
        result = reconcile_data(tx_text, bank_text)
        error = None
    except ValueError as e:
        result = None
        error = str(e)

    if "error" in expected:
        ok = error is not None and expected["error"] in error
    else:
        ok = result == expected

    if ok:
        print(f"PASS  {case}")
        passed += 1
    else:
        print(f"FAIL  {case}")
        print(f"      expected: {json.dumps(expected)}")
        print(f"      got:      {json.dumps(result) if result is not None else error}")
        failed += 1

print(f"\n{passed} passed, {failed} failed")
