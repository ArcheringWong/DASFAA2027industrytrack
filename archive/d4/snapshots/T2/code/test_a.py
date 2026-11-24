"""A: ordinary parametrized pytest regressions with explicit histories."""
import os
import pytest
from common import select, single, save

CASES = select(os.environ["D4_CASE_FILE"])
RESULTS = []


@pytest.mark.parametrize("case", CASES, ids=lambda x: x["name"])
def test_regression(case):
    result = single(case)
    result["expected_status"] = case["expected_status"]
    result["reproduce"] = f"D4_CASE_FILE={os.environ['D4_CASE_FILE']} pytest test_a.py -k {case['name']}"
    RESULTS.append(result)
    save(os.environ["D4_RESULT_FILE"], RESULTS)
    assert result["status"] == case["expected_status"], result
