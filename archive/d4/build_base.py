"""Freeze equivalent baseline inputs for A/B/C before maintenance edits."""
import copy
import json
from pathlib import Path
from engine import validate

ROOT = Path(__file__).resolve().parent
source = json.loads((ROOT.parent / "D3_termination_testing" / "cases.json").read_text(encoding="utf-8"))
names = {"confirmed_boundary_prefix", "excluded_null_prefix", "boundary_same_page",
         "boundary_no_prefix", "arrow_null_after_valid", "arrow_no_order",
         "invalid_null_include", "base_already_incomplete"}
base = [copy.deepcopy(c) for c in source if c["name"] in names]
assert len(base) == len(names)


def status(name, version):
    if name == "confirmed_boundary_prefix":
        return "TRUE_VIOLATION" if version == "1.31.0" else "PASS"
    if name == "excluded_null_prefix":
        return "TRUE_VIOLATION"
    if name == "invalid_null_include":
        return "INVALID_TRANSFORMATION"
    if name == "base_already_incomplete":
        return "INCONCLUSIVE"
    return "PASS"


def explicit(case):
    x = copy.deepcopy(case)
    if case["name"] == "invalid_null_include":
        x["invalid_reason"] = "null prefix is not neutral under include policy"
        return x
    if case["name"] == "base_already_incomplete":
        x["baseline_incomplete"] = True
        return x
    check = validate(case)
    assert check["valid"], (case["name"], check["reasons"])
    x["base_batches"] = check["variant_batches"]
    x.pop("prefix_recipe", None)
    x.pop("coalesce_prefix", None)
    return x


for case in base:
    case["expected_status_by_version"] = {v: status(case["name"], v) for v in case["versions"]}
out = ROOT / "snapshots" / "base"
out.mkdir(parents=True, exist_ok=True)
for scheme in ("a", "b", "c"):
    items = [copy.deepcopy(c) if scheme == "c" else explicit(c) for c in base]
    for item in items:
        item["expected_status_by_version"] = item.pop("expected_status_by_version")
    (out / f"{scheme}_cases.json").write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
print("base cases", len(base))
