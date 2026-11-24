"""Pre-automation paired validity check of the frozen D3 metamorphic relation."""
import json
import os
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
E = ROOT / "evidence"
os.environ["RUNTIME__DLTHUB_TELEMETRY"] = "false"
os.environ["DLT_DATA_DIR"] = str(E / "manual_runtime")
import dlt
import duckdb
import pyarrow as pa


def target(p):
    with p.sql_client() as client:
        exists = client.execute_sql(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='events'"
        )[0][0]
        return client.execute_sql("SELECT id, ts FROM events ORDER BY id") if exists else []


def boundary(prefix):
    con = duckdb.connect(":memory:")
    name = "d3_" + uuid.uuid4().hex[:12]
    p = dlt.pipeline(pipeline_name=name, pipelines_dir=str(E / "manual_runtime"),
                     destination=dlt.destinations.duckdb(credentials=con))
    requested = []

    @dlt.resource(name="events", primary_key="id")
    def events(pages, ts=dlt.sources.incremental("ts", initial_value=0,
                                                 row_order="desc", range_start="closed")):
        for i, page in enumerate(pages, 1):
            requested.append(i)
            yield page

    try:
        p.run(events([[{"id": 1, "ts": 1}]]))
        requested.clear()
        current = [[{"id": 2, "ts": 1}]]
        if prefix:
            current.insert(0, [{"id": 1, "ts": 1}])
        p.run(events(current))
        rows = target(p)
        result = {"mechanism": "confirmed_boundary", "prefix": prefix,
                  "current_batches": current, "requested_batches": requested.copy(),
                  "target_rows": rows, "target_ids": sorted({r[0] for r in rows}),
                  "state": json.loads(json.dumps(p.state, default=str)),
                  "error": None}
    except Exception as exc:
        result = {"mechanism": "confirmed_boundary", "prefix": prefix,
                  "requested_batches": requested.copy(), "error": repr(exc)}
    finally:
        con.close()
    result["expected_ids"] = [1, 2]
    result["missing_ids"] = sorted(set(result["expected_ids"]) - set(result.get("target_ids", []))) if result["error"] is None else []
    return result


def arrow_null(prefix):
    con = duckdb.connect(":memory:")
    name = "d3_" + uuid.uuid4().hex[:12]
    p = dlt.pipeline(pipeline_name=name, pipelines_dir=str(E / "manual_runtime"),
                     destination=dlt.destinations.duckdb(credentials=con))
    requested = []
    batches = []
    if prefix:
        batches.append(pa.table({"id": pa.array([1, 2], type=pa.int64()),
                                 "ts": pa.array([None, None], type=pa.int64())}))
    batches.append(pa.table({"id": [3, 4], "ts": [5, 6]}))

    @dlt.resource(name="events", primary_key="id")
    def events(ts=dlt.sources.incremental("ts", initial_value=0, end_value=10,
                                          row_order="asc", on_cursor_value_missing="exclude")):
        for i, batch in enumerate(batches, 1):
            requested.append(i)
            yield batch

    try:
        p.run(events())
        rows = target(p)
        result = {"mechanism": "excluded_null", "prefix": prefix,
                  "current_batches": [b.to_pylist() for b in batches],
                  "requested_batches": requested.copy(), "target_rows": rows,
                  "target_ids": sorted({r[0] for r in rows}),
                  "state": json.loads(json.dumps(p.state, default=str)),
                  "error": None}
    except Exception as exc:
        result = {"mechanism": "excluded_null", "prefix": prefix,
                  "requested_batches": requested.copy(), "error": repr(exc)}
    finally:
        con.close()
    result["expected_ids"] = [3, 4]
    result["missing_ids"] = sorted(set(result["expected_ids"]) - set(result.get("target_ids", []))) if result["error"] is None else []
    return result


def main():
    runs = [boundary(False), boundary(True)]
    if dlt.__version__ == "1.32.0":
        runs += [arrow_null(False), arrow_null(True)]
    out = E / f"manual_pairs_{dlt.__version__}.json"
    out.write_text(json.dumps(runs, indent=2, default=str), encoding="utf-8")
    print(json.dumps([{"mechanism": r["mechanism"], "prefix": r["prefix"],
                       "requested": r["requested_batches"], "actual": r.get("target_ids"),
                       "missing": r["missing_ids"], "error": r["error"]} for r in runs]))


if __name__ == "__main__":
    main()
