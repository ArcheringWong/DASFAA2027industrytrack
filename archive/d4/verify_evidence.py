"""Independent file-level checks of the saved D4 comparison; no dlt import."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
E = ROOT / "evidence"
summary = json.loads((E / "summary.json").read_text(encoding="utf-8"))
assert hashlib.sha256((ROOT / "engine.py").read_bytes()).hexdigest() == hashlib.sha256(
    (ROOT.parent / "D3_termination_testing" / "metamorphic.py").read_bytes()).hexdigest()
for name, digest in summary["source_sha256"].items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
for task in ("T1", "T2", "T3"):
    for name in ("engine.py", "common.py", "test_a.py", "stateful_b.py", "run_c.py", "run_matrix.py"):
        assert (ROOT / "snapshots" / task / "code" / name).read_bytes() == (
            ROOT / "snapshots" / "base" / "code" / name).read_bytes()

expected_new = {
    "T1": {"boundary_three_split": {"1.31.0": "TRUE_VIOLATION", "1.32.0": "PASS"},
           "boundary_three_coalesced": {"1.31.0": "PASS", "1.32.0": "PASS"},
           "invalid_dropped_original_t1": {"1.31.0": "INVALID_TRANSFORMATION", "1.32.0": "INVALID_TRANSFORMATION"}},
    "T2": {"arrow_split_with_null": {"1.32.0": "TRUE_VIOLATION"},
           "arrow_split_without_null": {"1.32.0": "PASS"},
           "invalid_mixed_format_t2": {"1.32.0": "INVALID_TRANSFORMATION"}},
    "T3": {"arrow_upper_bound_four": {"1.32.0": "PASS"},
           "invalid_include_under_bound": {"1.32.0": "INVALID_TRANSFORMATION"}},
}
report = {}
for task in ("base", "T1", "T2", "T3"):
    report[task] = {}
    for version in ("1.31.0", "1.32.0"):
        by_scheme = {}
        for scheme in ("a", "b", "c"):
            raw = json.loads((E / task / f"{scheme}_{version}.json").read_text(encoding="utf-8"))
            records = raw["deterministic"] if scheme == "b" else raw
            assert all(r["status"] == r["expected_status"] for r in records)
            for r in records:
                if r["status"] == "INVALID_TRANSFORMATION":
                    assert (r["trace"] is None if scheme != "c" else r["base"] is None and r["transformed"] is None)
                elif r["status"] == "TRUE_VIOLATION":
                    missing = r["missing_ids"] if scheme != "c" else r["transformed_missing_ids"]
                    assert missing, (task, scheme, version, r["name"])
            by_scheme[scheme] = {r["name"]: r["status"] for r in records}
            if scheme == "b":
                assert 1 <= len(raw["state_machine_exploration"]) <= 12
        assert by_scheme["a"] == by_scheme["b"] == by_scheme["c"]
        if task != "base":
            for name, versions in expected_new[task].items():
                if version in versions:
                    assert by_scheme["a"][name] == versions[version]
        report[task][version] = by_scheme["a"]
assert report["base"]["1.31.0"]["confirmed_boundary_prefix"] == "TRUE_VIOLATION"
assert report["base"]["1.32.0"]["confirmed_boundary_prefix"] == "PASS"
assert report["base"]["1.32.0"]["excluded_null_prefix"] == "TRUE_VIOLATION"
print(json.dumps({"snapshots": list(report), "schemes_agree": True,
                  "new_tasks": {k: list(v) for k, v in expected_new.items()},
                  "source_hashes_match": True, "code_snapshots_unchanged": True}, indent=2))
