"""Apply the three pre-frozen maintenance requests to independent base snapshots."""
import copy
import difflib
import json
import shutil
from pathlib import Path
from engine import validate

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "snapshots" / "base"
boundary = next(c for c in json.loads((BASE / "c_cases.json").read_text(encoding="utf-8"))
                if c["name"] == "confirmed_boundary_prefix")
arrow = next(c for c in json.loads((BASE / "c_cases.json").read_text(encoding="utf-8"))
             if c["name"] == "excluded_null_prefix")


def clone(source, name, statuses, **changes):
    case = copy.deepcopy(source)
    case.update(changes)
    case["name"] = name
    case["expected_status_by_version"] = statuses
    return case


def explicit(case):
    item = copy.deepcopy(case)
    check = validate(case)
    if not check["valid"]:
        item["invalid_reason"] = "; ".join(check["reasons"])
    else:
        item["base_batches"] = check["variant_batches"]
    item.pop("prefix_recipe", None)
    item.pop("coalesce_prefix", None)
    return item


tasks = {
    "T1": [
        clone(boundary, "boundary_three_split", {"1.31.0": "TRUE_VIOLATION", "1.32.0": "PASS"},
              base_batches=[[{"id": 2, "ts": 1}, {"id": 3, "ts": 1}]]),
        clone(boundary, "boundary_three_coalesced", {"1.31.0": "PASS", "1.32.0": "PASS"},
              base_batches=[[{"id": 2, "ts": 1}, {"id": 3, "ts": 1}]], coalesce_prefix=True),
        clone(boundary, "invalid_dropped_original_t1", {"1.31.0": "INVALID_TRANSFORMATION", "1.32.0": "INVALID_TRANSFORMATION"},
              override_variant_batches=[[{"id": 1, "ts": 1}]]),
    ],
    "T2": [
        clone(arrow, "arrow_split_with_null", {"1.32.0": "TRUE_VIOLATION"},
              base_batches=[[{"id": 3, "ts": 5}], [{"id": 4, "ts": 6}]]),
        clone(arrow, "arrow_split_without_null", {"1.32.0": "PASS"},
              base_batches=[[{"id": 3, "ts": 5}], [{"id": 4, "ts": 6}]], prefix_recipe=None),
        clone(arrow, "invalid_mixed_format_t2", {"1.32.0": "INVALID_TRANSFORMATION"},
              format="mixed"),
    ],
    "T3": [
        clone(arrow, "arrow_upper_bound_four", {"1.32.0": "PASS"}, end_value=4),
        clone(arrow, "invalid_include_under_bound", {"1.32.0": "INVALID_TRANSFORMATION"},
              end_value=4, missing_policy="include"),
    ],
}

diff_dir = ROOT / "evidence" / "diffs"
diff_dir.mkdir(parents=True, exist_ok=True)
for task, additions in tasks.items():
    dest = ROOT / "snapshots" / task
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(BASE / "code", dest / "code", dirs_exist_ok=True)
    for scheme in ("a", "b", "c"):
        name = f"{scheme}_cases.json"
        original = (BASE / name).read_text(encoding="utf-8")
        cases = json.loads(original)
        cases += [copy.deepcopy(c) if scheme == "c" else explicit(c) for c in additions]
        updated = json.dumps(cases, ensure_ascii=False, indent=2)
        (dest / name).write_text(updated, encoding="utf-8")
        diff = difflib.unified_diff(original.splitlines(True), updated.splitlines(True),
                                    fromfile=f"base/{name}", tofile=f"{task}/{name}")
        (diff_dir / f"{task}_{scheme}.patch").write_text("".join(diff), encoding="utf-8")
    print(task, len(additions))
