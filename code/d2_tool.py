"""Bounded cross-mechanism incremental completeness experiment on real dlt."""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import uuid
from dataclasses import asdict, dataclass
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
from hypothesis import HealthCheck, Phase, find, settings, strategies as st
from hypothesis.errors import NoSuchExample


@dataclass(frozen=True)
class Row:
    id: int
    cursor: int | None
    commit_step: int


@dataclass(frozen=True)
class Operation:
    kind: str
    rows: tuple[Row, ...] = ()
    format: str | None = None
    value: int | str | None = None


def make_scenario(first_shape: str, fmt: str, order: str | None,
                  bounded: bool, later_value: int, later_count: int,
                  extra_null: bool) -> list[Operation]:
    """Independent knobs create legal source batches and read settings."""
    if first_shape == "all_null":
        first = (Row(1, None, 1), Row(2, None, 2))
    elif first_shape == "mixed":
        first = (Row(1, None, 1), Row(2, 1, 2))
    else:
        first = (Row(1, 1, 1), Row(2, 2, 2))
    later = tuple(Row(2 + i, later_value + i - 1, 2 + i)
                  for i in range(1, later_count + 1))
    ops = [Operation("set_format", value=fmt),
           Operation("set_row_order", value=order),
           Operation("set_end_value", value=10 if bounded else None),
           Operation("append_batch", rows=first)]
    if extra_null:
        ops.append(Operation("append_batch", rows=(Row(9, None, 9),)))
    ops.extend([Operation("append_batch", rows=later), Operation("run_incremental_sync")])
    return ops


def strategy(kind: str):
    if kind == "generic":
        return st.builds(make_scenario,
                         st.sampled_from(["valid", "mixed", "all_null"]),
                         st.sampled_from(["dict", "arrow"]),
                         st.sampled_from([None, "asc"]),
                         st.sampled_from([False, True]),
                         st.integers(5, 8), st.integers(1, 2), st.booleans())
    if kind == "guided":
        return st.builds(make_scenario,
                         st.sampled_from(["valid", "all_null", "all_null", "all_null", "mixed"]),
                         st.sampled_from(["dict", "arrow", "arrow", "arrow"]),
                         st.sampled_from([None, "asc", "asc"]),
                         st.sampled_from([False, True, True]),
                         st.integers(5, 8), st.integers(1, 2), st.booleans())
    raise ValueError(kind)


def render_ops(ops: list[Operation]) -> list[dict[str, Any]]:
    return [{**asdict(op), "rows": [asdict(r) for r in op.rows]} for op in ops]


def load_ops(obj: list[dict[str, Any]]) -> list[Operation]:
    return [Operation(kind=x["kind"], rows=tuple(Row(**r) for r in x.get("rows", [])),
                      format=x.get("format"), value=x.get("value")) for x in obj]


def source_oracle(ops: list[Operation]) -> dict[str, Any]:
    batches: list[list[Row]] = []
    fmt, order, end = "dict", None, None
    range_end = "open"
    for op in ops:
        if op.kind == "set_format":
            fmt = op.value
        elif op.kind == "set_row_order":
            order = op.value
        elif op.kind == "set_end_value":
            end = op.value
        elif op.kind == "set_range_end":
            range_end = end_mode(op.value)
        elif op.kind == "append_batch":
            batches.append(list(op.rows))
        elif op.kind != "run_incremental_sync":
            raise ValueError(op.kind)
    if not ops or ops[-1].kind != "run_incremental_sync":
        raise ValueError("scenario must end in sync")
    if fmt not in ("dict", "arrow") or order not in (None, "asc"):
        raise ValueError("invalid mode")
    ids = [r.id for batch in batches for r in batch if eligible(r.cursor, 0, end, range_end)]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate valid ID")
    return {"batches": batches, "format": fmt, "row_order": order,
            "end_value": end, "range_end": range_end, "expected_ids": sorted(ids),
            "all_committed_ids": [r.id for b in batches for r in b]}


class DltAdapter:
    """Product-specific edge: source batches -> dlt -> local DuckDB."""

    def run(self, spec: dict[str, Any]) -> dict[str, Any]:
        requested: list[int] = []
        fmt, order, end = spec["format"], spec["row_order"], spec["end_value"]

        @dlt.resource(name="events", primary_key="id")
        def events(ts=dlt.sources.incremental("ts", initial_value=0, end_value=end,
                                              row_order=order,
                                              range_end=spec.get("range_end", "open"),
                                              on_cursor_value_missing="exclude")):
            for index, batch in enumerate(spec["batches"], 1):
                requested.append(index)
                rows = [{"id": r.id, "ts": r.cursor} for r in batch]
                if fmt == "arrow":
                    yield pa.table({"id": pa.array([r["id"] for r in rows], type=pa.int64()),
                                    "ts": pa.array([r["ts"] for r in rows], type=pa.int64())})
                else:
                    yield rows

        con = duckdb.connect(":memory:")
        name = "d2_" + uuid.uuid4().hex[:12]
        p = dlt.pipeline(pipeline_name=name, pipelines_dir=str(E / "runtime"),
                         destination=dlt.destinations.duckdb(credentials=con))
        try:
            p.run(events())
            with p.sql_client() as client:
                exists = client.execute_sql(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='events'"
                )[0][0]
                rows = client.execute_sql("SELECT id, ts FROM events ORDER BY id") if exists else []
            error = None
            state = json.loads(json.dumps(p.state, default=str))
        except Exception as exc:
            rows, error = [], repr(exc)
            state = json.loads(json.dumps(p.state, default=str))
            exists = False
        finally:
            con.close()
        return {"requested_batches": requested, "target_rows": rows,
                "target_ids": sorted({int(r[0]) for r in rows}),
                "target_table_exists": bool(exists), "dlt_state": state,
                "connector_error": error, "pipeline_name": name}


def run_case(ops: list[Operation], label: str) -> dict[str, Any]:
    start = time.perf_counter()
    spec = source_oracle(ops)
    actual = DltAdapter().run(spec)
    missing = sorted(set(spec["expected_ids"]) - set(actual["target_ids"])) if not actual["connector_error"] else []
    return {"label": label, "dlt_version": dlt.__version__,
            "duckdb_version": duckdb.__version__, "pyarrow_version": pa.__version__,
            "python": sys.version, "ops": render_ops(ops),
            "batches": [[asdict(r) for r in b] for b in spec["batches"]],
            "format": spec["format"], "row_order": spec["row_order"],
            "end_value": spec["end_value"], "range_end": spec["range_end"], "expected_ids": spec["expected_ids"],
            **actual, "missing_ids": missing,
            "failure_type": ("connector_error" if actual["connector_error"] else
                             "record_omission" if missing else None),
            "elapsed_seconds": round(time.perf_counter() - start, 6)}


def explore(kind: str, seed: int, count: int = 10) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    def assess(ops: list[Operation]) -> bool:
        if len(results) >= count:
            return False
        result = run_case(ops, f"{kind}_{seed}_{len(results)+1}")
        results.append(result)
        (E / f"explore_{kind}_{seed}.json").write_text(
            json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return False

    try:
        find(strategy(kind), assess, random=random.Random(seed),
             settings=settings(max_examples=count, phases=(Phase.generate,),
                               deadline=None, database=None,
                               suppress_health_check=(HealthCheck.too_slow,)))
    except NoSuchExample:
        pass
    return results


def shrink(kind: str, witness: list[Operation], budget: int = 30) -> dict[str, Any]:
    if budget < 3:
        raise ValueError("budget must allow original, search, and final validation")
    attempts: list[dict[str, Any]] = []
    original = run_case(witness, "shrink_original_validation")
    best = original if original["failure_type"] == "record_omission" else None

    class BudgetReached(Exception):
        pass

    def fails(ops: list[Operation]) -> bool:
        nonlocal best
        if len(attempts) >= budget - 2:
            raise BudgetReached()
        result = run_case(ops, f"shrink_{kind}_{len(attempts)+1}")
        attempts.append(result)
        (E / f"shrink_{kind}.json").write_text(
            json.dumps(attempts, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        if result["failure_type"] == "record_omission":
            if best is None or (len(result["ops"]), sum(len(b) for b in result["batches"])) < (
                    len(best["ops"]), sum(len(b) for b in best["batches"])):
                best = result
            return True
        return False

    final_validation_ran = False
    try:
        answer = find(strategy(kind), fails, random=random.Random(907),
                      settings=settings(max_examples=budget, phases=(Phase.generate, Phase.shrink),
                                        deadline=None, database=None,
                                        suppress_health_check=(HealthCheck.too_slow,)))
        final = run_case(answer, "shrink_final_validation")
        final_validation_ran = True
        status = "hypothesis_completed" if final["failure_type"] == "record_omission" else "unstable_failure"
        best = final if final["failure_type"] == "record_omission" else best
    except (BudgetReached, NoSuchExample):
        status = "budget_exhausted_best_observed"
    summary = {"status": status, "budget": budget,
               "hypothesis_real_runs": len(attempts),
               "extra_original_and_final_validations": 1 + int(final_validation_ran),
               "total_real_runs": len(attempts) + 1 + int(final_validation_ran),
               "best_ops": best["ops"] if best else None,
               "best_result": best}
    (E / f"shrink_{kind}_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["explore", "replay", "shrink"])
    ap.add_argument("--kind", choices=["generic", "guided"])
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--witness", type=Path)
    ap.add_argument("--budget", type=int, default=30)
    args = ap.parse_args()
    if args.mode == "explore":
        if not args.kind:
            ap.error("--kind required")
        results = explore(args.kind, args.seed)
        print(json.dumps({"count": len(results),
                          "omissions": sum(r["failure_type"] == "record_omission" for r in results),
                          "errors": sum(r["failure_type"] == "connector_error" for r in results)}))
    elif args.mode == "shrink":
        if not args.kind or not args.witness:
            ap.error("--kind and --witness required")
        ops = load_ops(json.loads(args.witness.read_text(encoding="utf-8-sig")))
        summary = shrink(args.kind, ops, args.budget)
        print(json.dumps({"status": summary["status"],
                          "runs": summary["hypothesis_real_runs"],
                          "best_ops": len(summary["best_ops"] or [])}))
    else:
        if not args.witness:
            ap.error("--witness required")
        ops = load_ops(json.loads(args.witness.read_text(encoding="utf-8-sig")))
        result = run_case(ops, "replay")
        out = E / f"replay_{dlt.__version__}.json"
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(json.dumps({"failure": result["failure_type"],
                          "missing": result["missing_ids"],
                          "requested": result["requested_batches"]}))


if __name__ == "__main__":
    main()
