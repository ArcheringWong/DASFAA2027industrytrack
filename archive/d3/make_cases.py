"""Deterministically save finite legal and illegal metamorphic test inputs."""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def clone(base, name, **changes):
    x = copy.deepcopy(base)
    x.update(changes)
    x["name"] = name
    return x


boundary = {
    "name": "confirmed_boundary_prefix",
    "versions": ["1.31.0", "1.32.0"],
    "format": "dict", "row_order": "desc", "end_value": None,
    "missing_policy": "exclude", "range_start": "closed",
    "write_disposition": "append", "stable_ties": True, "source_complete": True,
    "prior_batches": [[{"id": 1, "ts": 1}]],
    "base_batches": [[{"id": 2, "ts": 1}]],
    "prefix_recipe": {"kind": "confirmed_boundary", "count": 1}
}
arrow = {
    "name": "excluded_null_prefix",
    "versions": ["1.32.0"],
    "format": "arrow", "row_order": "asc", "end_value": 10,
    "missing_policy": "exclude", "range_start": "closed",
    "write_disposition": "append", "stable_ties": True, "source_complete": True,
    "prior_batches": [],
    "base_batches": [[{"id": 3, "ts": 5}, {"id": 4, "ts": 6}]],
    "prefix_recipe": {"kind": "excluded_null", "count": 2}
}

cases = [boundary, arrow,
         clone(boundary, "boundary_no_prefix", prefix_recipe=None, prefix_batches=[]),
         clone(boundary, "boundary_same_page", coalesce_prefix=True),
         clone(boundary, "boundary_no_remaining", base_batches=[]),
         clone(arrow, "arrow_no_prefix", prefix_recipe=None, prefix_batches=[]),
         clone(arrow, "arrow_null_after_valid", prefix_recipe=None, prefix_batches=[],
               base_batches=[[{"id": 3, "ts": 5}, {"id": 4, "ts": 6}],
                             [{"id": 1, "ts": None}, {"id": 2, "ts": None}]]),
         clone(arrow, "arrow_null_inside_valid_batch", prefix_recipe=None, prefix_batches=[],
               base_batches=[[{"id": 1, "ts": None}, {"id": 3, "ts": 5},
                              {"id": 4, "ts": 6}]]),
         clone(arrow, "arrow_no_remaining", base_batches=[]),
         clone(arrow, "arrow_no_order", row_order=None),
         clone(boundary, "boundary_upsert_set_only", versions=["1.32.0"],
               write_disposition="merge"),
         clone(boundary, "base_already_incomplete", versions=["1.31.0"],
               base_batches=[[{"id": 1, "ts": 1}], [{"id": 2, "ts": 1}]]),
         clone(boundary, "invalid_new_prefix", prior_batches=[], prefix_recipe=None,
               prefix_batches=[[{"id": 9, "ts": 1}]]),
         clone(arrow, "invalid_null_include", missing_policy="include"),
         clone(boundary, "invalid_unstable_ties", stable_ties=False),
         clone(boundary, "invalid_dropped_original",
               override_variant_batches=[[{"id": 1, "ts": 1}]]),
         clone(arrow, "invalid_changed_bound", transformed_end_value=4),
         clone(boundary, "invalid_changed_write", transformed_write_disposition="merge"),
         clone(arrow, "invalid_incomplete_source", source_complete=False),
         clone(arrow, "invalid_mixed_format", format="mixed")]

(ROOT / "cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote {len(cases)} cases")
