"""Read-only consistency checks for saved D3 input and true product traces."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
E = ROOT / "evidence"


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


cases = load(ROOT / "cases.json")
assert len(cases) == 20
summary = {"versions": {}, "core": {}, "invalid_no_execution": 0,
           "normal_passes": 0, "inconclusive": 0, "execution_errors": 0,
           "real_scenario_executions": 0, "pipeline_run_calls": 0}
for version in ("1.31.0", "1.32.0"):
    runs = load(E / f"metamorphic_{version}.json")
    expected_names = [c["name"] for c in cases if version in c["versions"]]
    assert [r["name"] for r in runs] == expected_names
    counts = {}
    for run in runs:
        status = run["status"]
        counts[status] = counts.get(status, 0) + 1
        case = run["case"]
        check = run["validation"]
        if status == "INVALID_TRANSFORMATION":
            assert not check["valid"] and check["reasons"]
            assert run["base"] is None and run["transformed"] is None
            summary["invalid_no_execution"] += 1
            continue
        assert check["valid"]
        assert check["original_oracle"]["final_ids"] == check["transformed_oracle"]["final_ids"]
        assert check["original_oracle"]["new_ids"] == check["transformed_oracle"]["new_ids"]
        assert run["base"] is not None and run["transformed"] is not None
        summary["real_scenario_executions"] += 2
        summary["pipeline_run_calls"] += 2 * (1 + bool(case.get("prior_batches")))
        assert run["transformed"]["current_batches"] == check["variant_batches"]
        ids = set(check["original_oracle"]["final_ids"])
        if run["base"]["error"] or run["transformed"]["error"]:
            assert status == "EXECUTION_ERROR"
            summary["execution_errors"] += 1
            continue
        assert run["base_missing_ids"] == sorted(ids - set(run["base"]["target_ids"]))
        assert run["transformed_missing_ids"] == sorted(ids - set(run["transformed"]["target_ids"]))
        if status == "TRUE_VIOLATION":
            assert not run["base_missing_ids"] and run["transformed_missing_ids"]
        elif status == "INCONCLUSIVE":
            assert run["base_missing_ids"]
            summary["inconclusive"] += 1
        elif status == "PASS":
            assert not run["base_missing_ids"] and not run["transformed_missing_ids"]
            summary["normal_passes"] += 1
        else:
            raise AssertionError(status)
    summary["versions"][version] = counts

old = load(E / "metamorphic_1.31.0.json")
new = load(E / "metamorphic_1.32.0.json")
lookup = {(r["dlt_version"], r["name"]): r for r in old + new}
assert lookup[("1.31.0", "confirmed_boundary_prefix")]["status"] == "TRUE_VIOLATION"
assert lookup[("1.32.0", "confirmed_boundary_prefix")]["status"] == "PASS"
assert lookup[("1.32.0", "excluded_null_prefix")]["status"] == "TRUE_VIOLATION"
assert lookup[("1.31.0", "base_already_incomplete")]["status"] == "INCONCLUSIVE"
for version in ("1.31.0", "1.32.0"):
    manual = load(E / f"manual_pairs_{version}.json")
    for m in manual:
        matching = lookup[(version, "confirmed_boundary_prefix" if m["mechanism"] == "confirmed_boundary" else "excluded_null_prefix")]
        branch = matching["transformed"] if m["prefix"] else matching["base"]
        assert m["target_ids"] == branch["target_ids"]
        assert m["requested_batches"] == branch["requested_batches"]

for key in (("1.31.0", "confirmed_boundary_prefix"),
            ("1.32.0", "confirmed_boundary_prefix"),
            ("1.32.0", "excluded_null_prefix")):
    r = lookup[key]
    summary["core"]["/".join(key)] = {
        "status": r["status"], "expected": r["validation"]["original_oracle"]["final_ids"],
        "base_actual": r["base"]["target_ids"],
        "transformed_actual": r["transformed"]["target_ids"],
        "base_requested": r["base"]["requested_batches"],
        "transformed_requested": r["transformed"]["requested_batches"],
        "elapsed_seconds": r["elapsed_seconds"]}
summary["sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in (ROOT / "metamorphic.py", ROOT / "manual_pairs.py",
                               ROOT / "make_cases.py", ROOT / "verify_evidence.py")}
(E / "summary.json").write_text(json.dumps(summary, ensure_ascii=False,
                                           indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in summary.items() if k != "sha256"},
                 ensure_ascii=False, indent=2))
