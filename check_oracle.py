"""Rerun the archived explicit-boundary checks with the unchanged repaired adapters."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
from runtime import arguments, prepare

HERE = Path(__file__).resolve().parent
D = HERE / "archive"

def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def d2_test_cases(d2):
    def ops(rows, *, fmt="dict", mode=None):
        result = [d2.Operation("set_format", value=fmt), d2.Operation("set_end_value", value=10)]
        if mode is not None:
            result.append(d2.Operation("set_range_end", value=mode))
        for batch in rows:
            result.append(d2.Operation("append_batch", rows=tuple(d2.Row(identity, cursor, identity)
                                                                 for identity, cursor in batch)))
        return [*result, d2.Operation("run_incremental_sync")]

    # IDs 1–5 stand for below-start, at-start, interior, at-end, and above-end.
    bounds = [[(1, -1), (2, 0), (3, 9), (4, 10), (5, 11)]]
    nulls = [[(11, None), (12, None)], [(13, None), (14, 9), (15, 10), (16, 11)]]
    return [
        ("T1–T3 default open", [2, 3], ops(bounds)),
        ("T2 explicit open", [2, 3], ops(bounds, mode="open")),
        ("T5 explicit closed", [2, 3, 4], ops(bounds, mode="closed")),
        ("T4 all-null then mixed Arrow; no order", [14], ops(nulls, fmt="arrow")),
    ]


def d3_test_cases():
    include = {"format": "dict", "row_order": None, "end_value": 10, "missing_policy": "include",
               "base_batches": [[{"id": 21, "ts": None}, {"id": 22, "ts": 9}, {"id": 23, "ts": 10}]]}
    prior = {"format": "dict", "row_order": None, "end_value": 10, "missing_policy": "exclude",
             "prior_batches": [[{"id": 31, "ts": 9}, {"id": 32, "ts": 10}]],
             "base_batches": [[{"id": 33, "ts": 1}, {"id": 34, "ts": 10}, {"id": 35, "ts": 11}]]}
    return [
        ("T4 include null and exclude equality", [21, 22], include),
        ("T5 explicit closed with include null", [21, 22, 23], {**include, "range_end": "closed"}),
        ("T2/T3 bounded prior does not move start", [31, 33], prior),
    ]


def run_tests(d2, d3, version):
    tests = []

    def add(label, inputs, expected, actual, passed):
        tests.append({"label": label, "input": inputs, "expected": expected, "actual": actual, "pass": passed})
        print(f"{'PASS' if passed else 'FAIL'} {label}", flush=True)

    if version == "1.32.0":
        for label, wanted, ops in d2_test_cases(d2):
            result = d2.run_case(ops, label)
            actual = {k: result[k] for k in ("expected_ids", "target_ids", "target_rows", "requested_batches",
                                              "connector_error", "missing_ids", "range_end")}
            ok = result["connector_error"] is None and result["expected_ids"] == result["target_ids"] == wanted
            add(label, result["ops"], wanted, actual, ok)
        for label, wanted, case in d3_test_cases():
            oracle = d3.expected_ids(case, case["base_batches"])
            product = d3.run_product(case, case["base_batches"], label)
            ok = product["error"] is None and oracle["final_ids"] == product["target_ids"] == wanted
            add(label, case, wanted, {"oracle": oracle, "product": product}, ok)

    cases = {case["name"]: case for case in read(D / "d3/cases.json")}
    names = ("confirmed_boundary_prefix",) if version == "1.31.0" else ("confirmed_boundary_prefix", "excluded_null_prefix")
    for name in names:
        values = {
            ("confirmed_boundary_prefix", "1.31.0"): ([1, 2], [1], [2], [1], "TRUE_VIOLATION"),
            ("confirmed_boundary_prefix", "1.32.0"): ([1, 2], [1, 2], [], [1, 2], "PASS"),
            ("excluded_null_prefix", "1.32.0"): ([3, 4], [], [3, 4], [1], "TRUE_VIOLATION"),
        }[(name, version)]
        wanted = dict(zip(("eligible_ids", "transformed_target_ids", "missing_ids", "transformed_requests", "status"),
                          values))
        case = cases[name]
        result = d3.test_pair(case)
        validation = result["validation"]
        actual = {"eligible_ids": validation["original_oracle"]["final_ids"],
                  "transformed_oracle_ids": validation["transformed_oracle"]["final_ids"],
                  "base_target_ids": result["base"]["target_ids"],
                  "base_error": result["base"]["error"], "transformed_error": result["transformed"]["error"],
                  "transformed_target_ids": result["transformed"]["target_ids"],
                  "missing_ids": result["transformed_missing_ids"],
                  "transformed_requests": result["transformed"]["requested_batches"], "status": result["status"]}
        passed = all(actual[key] == value for key, value in wanted.items()) and (
            actual["base_target_ids"] == actual["transformed_oracle_ids"] == wanted["eligible_ids"]
            and actual["base_error"] is None and actual["transformed_error"] is None
        )
        add(f"T6 {name} on {version}", case, wanted, {**actual, "real_trace": result}, passed)
    if version == "1.32.0":
        changed = {**cases["excluded_null_prefix"], "transformed_range_end": "closed"}
        result = d3.test_pair(changed)
        ok = result["status"] == "INVALID_TRANSFORMATION" and result["base"] is result["transformed"] is None
        add("range-end change rejects a comparison before execution", changed, "INVALID_TRANSFORMATION", result, ok)
        included = {**cases["excluded_null_prefix"], "missing_policy": "include"}
        result = d3.test_pair(included)
        ok = (result["status"] == "INVALID_TRANSFORMATION" and result["base"] is result["transformed"] is None
              and result["validation"]["original_oracle"]["final_ids"] == [3, 4]
              and result["validation"]["transformed_oracle"]["final_ids"] == [3, 4, 5, 6])
        add("include policy does not make a null prefix neutral", included, "INVALID_TRANSFORMATION", result, ok)
    return tests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    arguments(parser)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with TemporaryDirectory(prefix="o-", dir=args.output) as directory:
        work = Path(directory)
        dlt = prepare(args, work)
        sys.path.insert(0, str(HERE / "code"))
        import d2_tool
        import metamorphic

        d2_tool.E = metamorphic.E = work
        os.environ["DLT_DATA_DIR"] = str(work / "settings")
        tests = run_tests(d2_tool, metamorphic, args.version)
        payload = {
            "validation_kind": "submission_preparation_oracle_checks",
            "observed_at_utc": datetime.now(timezone.utc).isoformat(),
            "environment": {"python": sys.version, "dlt": dlt.__version__,
                            "duckdb": d2_tool.duckdb.__version__, "pyarrow": d2_tool.pa.__version__},
            "elapsed_seconds": time.monotonic() - started,
            "tests": tests, "passed": sum(row["pass"] for row in tests), "tested": len(tests),
        }
    path = args.output / f"oracle-{args.version}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"output": path.name, "passed": payload["passed"], "tested": len(tests)}))
    return 0 if payload["passed"] == payload["tested"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
