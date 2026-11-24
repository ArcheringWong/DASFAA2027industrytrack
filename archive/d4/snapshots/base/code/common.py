"""Shared product adapter and source-identity oracle for all D4 designs."""
from __future__ import annotations
import json
import time
from pathlib import Path
from engine import expected_ids, run_product


def select(path: str):
    import dlt
    cases = [c for c in json.loads(Path(path).read_text(encoding="utf-8"))
             if dlt.__version__ in c["versions"]]
    for case in cases:
        case["expected_status"] = case["expected_status_by_version"][dlt.__version__]
    return cases


def single(case):
    """Evaluate an explicit complete source history, without a metamorphic oracle."""
    started = time.perf_counter()
    if case.get("invalid_reason"):
        return {"name": case["name"], "status": "INVALID_TRANSFORMATION",
                "reason": case["invalid_reason"], "trace": None,
                "pipeline_calls": 0, "elapsed_seconds": 0}
    oracle = expected_ids(case, case["base_batches"])
    trace = run_product(case, case["base_batches"], "single")
    missing = sorted(set(oracle["final_ids"]) - set(trace["target_ids"]))
    if trace["error"]:
        status = "EXECUTION_ERROR"
    elif case.get("baseline_incomplete"):
        status = "INCONCLUSIVE"
    elif missing:
        status = "TRUE_VIOLATION"
    else:
        status = "PASS"
    source = [r for b in case["base_batches"] for r in b]
    return {"name": case["name"], "status": status, "expected_ids": oracle["final_ids"],
            "missing_ids": missing,
            "missing_cursor_values": {str(r["id"]): r["ts"] for r in source if r["id"] in missing},
            "missing_batch_numbers": {str(r["id"]): i for i, b in enumerate(case["base_batches"], 1)
                                      for r in b if r["id"] in missing},
            "trace": trace, "pipeline_calls": 1 + bool(case.get("prior_batches")),
            "elapsed_seconds": round(time.perf_counter() - started, 6)}


def save(path: str, records):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(records, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
