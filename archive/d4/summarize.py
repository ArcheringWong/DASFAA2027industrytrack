"""Recompute D4 metrics from saved raw traces; no product execution."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
E = ROOT / "evidence"
out = {"snapshots": {}, "diffs": {}, "source_sha256": {}}
for snapshot in ("base", "T1", "T2", "T3"):
    records = []
    manifest = json.loads((E / snapshot / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest:
        scheme, version = item["scheme"], item["version"]
        path = E / snapshot / f"{scheme}_{version}.json"
        content = json.loads(path.read_text(encoding="utf-8"))
        fixed = content["deterministic"] if scheme == "b" else content
        generated = content["state_machine_exploration"] if scheme == "b" else []
        calls = sum(r["pipeline_calls"] for r in fixed) if scheme != "c" else sum(
            2 * (1 + bool(r["case"].get("prior_batches"))) for r in fixed if r["validation"]["valid"])
        generated_calls = sum(r["pipeline_calls"] for r in generated)
        row = {"scheme": scheme, "version": version, "cases": len(fixed),
               "statuses": dict(Counter(r["status"] for r in fixed)),
               "expected_match": all(r["status"] == r["expected_status"] for r in fixed),
               "deterministic_pipeline_calls": calls, "generated_pipeline_calls": generated_calls,
               "generated_cases": len(generated), "wall_seconds_including_generated": item["wall_seconds"],
               "case_elapsed_seconds": round(sum(r["elapsed_seconds"] for r in fixed), 6)}
        records.append(row)
        assert row["expected_match"] and item["exit_code"] == 0
    out["snapshots"][snapshot] = records
for task in ("T1", "T2", "T3"):
    out["diffs"][task] = {}
    for scheme in ("a", "b", "c"):
        lines = (E / "diffs" / f"{task}_{scheme}.patch").read_text(encoding="utf-8").splitlines()
        out["diffs"][task][scheme] = {
            "added_physical_lines": sum(s.startswith("+") and not s.startswith("+++") for s in lines),
            "deleted_physical_lines": sum(s.startswith("-") and not s.startswith("---") for s in lines),
            "changed_case_file_count": 1, "changed_code_file_count": 0,
            "added_cases": len(json.loads((ROOT / "snapshots" / task / f"{scheme}_cases.json").read_text(encoding="utf-8"))) - 8}
for name in ("engine.py", "common.py", "test_a.py", "stateful_b.py", "run_c.py", "build_base.py", "build_tasks.py"):
    out["source_sha256"][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
(E / "summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps({"diffs": out["diffs"], "calls": {
    k: [{"scheme": r["scheme"], "version": r["version"], "fixed": r["deterministic_pipeline_calls"],
         "extra_stateful": r["generated_pipeline_calls"]} for r in v]
    for k, v in out["snapshots"].items()}}, indent=2))
