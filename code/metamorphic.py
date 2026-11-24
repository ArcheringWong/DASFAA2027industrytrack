"""One conditional neutral-prefix relation, tested against real dlt pipelines."""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from cursor_contract import eligible, end_mode

ROOT = Path(__file__).resolve().parent
E = ROOT / "evidence"
E.mkdir(exist_ok=True)
os.environ["RUNTIME__DLTHUB_TELEMETRY"] = "false"
os.environ["DLT_DATA_DIR"] = str(E / "runtime")
import dlt
import duckdb
import pyarrow as pa


def flatten(batches: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [dict(row) for batch in batches for row in batch]


def ordered(batches: list[list[dict[str, Any]]], order: str | None) -> bool:
    values = [row["ts"] for row in flatten(batches) if row["ts"] is not None]
    if order == "asc":
        return values == sorted(values)
    if order == "desc":
        return values == sorted(values, reverse=True)
    return True


def expected_ids(case: dict[str, Any], current: list[list[dict[str, Any]]]) -> dict[str, Any]:
    prior = flatten(case.get("prior_batches", []))
    end = case.get("end_value")
    mode = end_mode(case.get("range_end", "open"))
    policy = case.get("missing_policy", "exclude")
    prior_good = {row["id"]: row["ts"] for row in prior
                  if eligible(row["ts"], 0, end, mode, policy)}
    # A bounded dlt read always takes its starting value from the configured interval.
    checkpoint = 0 if end is not None else max((value for value in prior_good.values() if value is not None),
                                               default=0)
    current_good = {row["id"] for row in flatten(current)
                    if eligible(row["ts"], checkpoint, end, mode, policy)}
    return {"prior_ids": sorted(prior_good), "new_ids": sorted(current_good - set(prior_good)),
            "final_ids": sorted(set(prior_good) | current_good),
            "model_checkpoint": checkpoint}


def derive_prefix(case: dict[str, Any]) -> list[list[dict[str, Any]]]:
    recipe = case.get("prefix_recipe")
    if recipe is None:
        return [[dict(r) for r in batch] for batch in case.get("prefix_batches", [])]
    if case.get("prefix_batches"):
        raise ValueError("choose a recipe or explicit prefix, not both")
    count = recipe.get("count", 1)
    if not isinstance(count, int) or count < 1:
        raise ValueError("prefix count must be positive")
    if recipe.get("kind") == "confirmed_boundary":
        prior = flatten(case.get("prior_batches", []))
        if case.get("end_value") is not None:
            raise ValueError("bounded reads do not have a persisted cursor checkpoint")
        values = [r["ts"] for r in prior if eligible(r["ts"], 0, None, "open")]
        if not values:
            raise ValueError("no prior boundary to replay")
        boundary = max(values)
        candidates = [r for r in prior if r["ts"] == boundary]
        if count > len(candidates):
            raise ValueError("not enough confirmed boundary identities")
        return [[dict(row)] for row in candidates[:count]]
    if recipe.get("kind") == "excluded_null":
        all_rows = flatten(case.get("prior_batches", [])) + flatten(case.get("base_batches", []))
        first_id = max((int(r["id"]) for r in all_rows), default=0) + 1
        return [[{"id": first_id + i, "ts": None} for i in range(count)]]
    raise ValueError("unknown neutral-prefix recipe")


def transformed_batches(case: dict[str, Any], prefix: list[list[dict[str, Any]]]) -> list[list[dict[str, Any]]]:
    base = [[dict(r) for r in batch] for batch in case.get("base_batches", [])]
    if case.get("coalesce_prefix", False) and prefix and base:
        return prefix[:-1] + [prefix[-1] + base[0]] + base[1:]
    return prefix + base


def validate(case: dict[str, Any]) -> dict[str, Any]:
    base = case.get("base_batches", [])
    try:
        mode = end_mode(case.get("range_end", "open"))
        prefix = derive_prefix(case)
        variant = transformed_batches(case, prefix)
    except (KeyError, TypeError, ValueError) as exc:
        return {"valid": False, "reasons": [f"prefix construction invalid: {exc!r}"],
                "generated_prefix_batches": None, "original_oracle": None,
                "transformed_oracle": None, "variant_batches": None}
    fmt, order, policy = case.get("format"), case.get("row_order"), case.get("missing_policy")
    reasons = []
    if fmt not in ("dict", "arrow") or order not in ("asc", "desc", None):
        reasons.append("unsupported format or order")
    if policy not in ("exclude", "include"):
        reasons.append("unknown null-cursor policy")
    if case.get("range_start", "closed") != "closed":
        reasons.append("this relation requires closed start for confirmed boundary")
    if case.get("write_disposition", "append") not in ("append", "merge"):
        reasons.append("unsupported target write disposition")
    if (case.get("transformed_end_value", case.get("end_value")) != case.get("end_value")
            or case.get("transformed_range_end", mode) != mode):
        reasons.append("read bounds changed")
    if case.get("transformed_write_disposition", case.get("write_disposition", "append")) != case.get("write_disposition", "append"):
        reasons.append("target write semantics changed")
    if not case.get("source_complete", True):
        reasons.append("source coverage not certified")
    if case.get("override_variant_batches") is not None:
        override = case["override_variant_batches"]
        if flatten(override) != flatten(variant):
            reasons.append("original records changed or omitted")
    if not ordered(base, order) or not ordered(variant, order):
        reasons.append("cursor order violated")
    values = [r["ts"] for r in flatten(variant) if r["ts"] is not None]
    if not case.get("stable_ties", True) and len(values) != len(set(values)):
        reasons.append("equal-cursor tie order not certified")
    if any("id" not in r or "ts" not in r for r in flatten(case.get("prior_batches", [])) + flatten(base) + flatten(prefix)):
        reasons.append("row lacks id or ts")
    prior = {r["id"]: r for r in flatten(case.get("prior_batches", []))}
    base_ids = {r["id"] for r in flatten(base)}
    end = case.get("end_value")
    prior_good = {r["id"] for r in prior.values()
                  if eligible(r["ts"], 0, end, mode)}
    prior_checkpoint = max((prior[i]["ts"] for i in prior_good), default=0)
    for row in flatten(prefix):
        excluded_null = row["ts"] is None and policy == "exclude" and row["id"] not in base_ids
        confirmed_boundary = (end is None and row["id"] in prior_good and row == prior[row["id"]]
                              and row["ts"] == prior_checkpoint
                              and case.get("range_start", "closed") == "closed")
        if not (excluded_null or confirmed_boundary):
            reasons.append(f"prefix id {row['id']} is not proven neutral")
    try:
        original = expected_ids(case, base)
        transformed = expected_ids(case, variant)
        if original["final_ids"] != transformed["final_ids"] or original["new_ids"] != transformed["new_ids"]:
            reasons.append("expected eligible identities changed")
    except (KeyError, TypeError, ValueError) as exc:
        original = transformed = None
        reasons.append(f"oracle input invalid: {exc!r}")
    return {"valid": not reasons, "reasons": reasons,
            "generated_prefix_batches": prefix,
            "original_oracle": original, "transformed_oracle": transformed,
            "variant_batches": variant}


def run_product(case: dict[str, Any], batches: list[list[dict[str, Any]]], label: str) -> dict[str, Any]:
    requested: list[int] = []
    prior_requested: list[int] = []
    fmt, order, end = case["format"], case.get("row_order"), case.get("end_value")
    mode = end_mode(case.get("range_end", "open"))
    policy = case["missing_policy"]
    con = duckdb.connect(":memory:")
    name = "d3_" + uuid.uuid4().hex[:12]
    p = dlt.pipeline(pipeline_name=name, pipelines_dir=str(E / "runtime"),
                     destination=dlt.destinations.duckdb(credentials=con))

    @dlt.resource(name="events", primary_key="id", write_disposition=case.get("write_disposition", "append"))
    def events(source_batches, ts=dlt.sources.incremental(
            "ts", initial_value=0, end_value=end, row_order=order,
            range_start="closed", range_end=mode, on_cursor_value_missing=policy)):
        for index, batch in enumerate(source_batches, 1):
            requested.append(index)
            if fmt == "arrow":
                yield pa.table({"id": pa.array([r["id"] for r in batch], type=pa.int64()),
                                "ts": pa.array([r["ts"] for r in batch], type=pa.int64())})
            else:
                yield [dict(r) for r in batch]

    error = None
    rows = []
    state_before = None
    state_after = None
    try:
        if case.get("prior_batches"):
            p.run(events(case["prior_batches"]))
            prior_requested = requested.copy()
            requested.clear()
            with p.sql_client() as client:
                prior_rows = client.execute_sql("SELECT id, ts FROM events ORDER BY id")
            state_before = json.loads(json.dumps(p.state, default=str))
        else:
            prior_rows = []
        p.run(events(batches))
        with p.sql_client() as client:
            exists = client.execute_sql(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='events'"
            )[0][0]
            rows = client.execute_sql("SELECT id, ts FROM events ORDER BY id") if exists else []
        state_after = json.loads(json.dumps(p.state, default=str))
    except Exception as exc:
        error = repr(exc)
        prior_rows = locals().get("prior_rows", [])
        try:
            state_after = json.loads(json.dumps(p.state, default=str))
        except Exception:
            pass
    finally:
        con.close()
    return {"label": label, "dlt_version": dlt.__version__, "pipeline_name": name,
            "prior_batches": case.get("prior_batches", []), "current_batches": batches,
            "prior_requested_batches": prior_requested, "requested_batches": requested.copy(),
            "prior_target_rows": prior_rows, "target_rows": rows,
            "target_ids": sorted({int(r[0]) for r in rows}),
            "state_before": state_before, "state_after": state_after,
            "error": error}


def test_pair(case: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    check = validate(case)
    result = {"name": case.get("name"), "case": case, "validation": check,
              "dlt_version": dlt.__version__, "base": None, "transformed": None}
    if not check["valid"]:
        result["status"] = "INVALID_TRANSFORMATION"
    else:
        base = run_product(case, case["base_batches"], "base")
        transformed = run_product(case, check["variant_batches"], "transformed")
        result["base"], result["transformed"] = base, transformed
        expected = set(check["original_oracle"]["final_ids"])
        base_missing = sorted(expected - set(base["target_ids"])) if base["error"] is None else []
        variant_missing = sorted(expected - set(transformed["target_ids"])) if transformed["error"] is None else []
        result["base_missing_ids"] = base_missing
        result["transformed_missing_ids"] = variant_missing
        if base["error"] or transformed["error"]:
            result["status"] = "EXECUTION_ERROR"
        elif base_missing:
            result["status"] = "INCONCLUSIVE"
        elif variant_missing:
            result["status"] = "TRUE_VIOLATION"
        else:
            result["status"] = "PASS"
        result["duplicate_output_claim"] = "not tested; target identity set only"
    result["elapsed_seconds"] = round(time.perf_counter() - started, 6)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case_file", type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    cases = json.loads(args.case_file.read_text(encoding="utf-8-sig"))
    output = []
    for case in cases:
        if case.get("versions") and dlt.__version__ not in case["versions"]:
            continue
        result = test_pair(case)
        output.append(result)
        path = args.output or E / f"metamorphic_{dlt.__version__}.json"
        path.write_text(json.dumps(output, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(json.dumps({"name": result["name"], "status": result["status"],
                          "base_missing": result.get("base_missing_ids"),
                          "transformed_missing": result.get("transformed_missing_ids")}))


if __name__ == "__main__":
    main()
