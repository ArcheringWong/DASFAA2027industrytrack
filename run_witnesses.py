"""Execute finite synthetic histories on released dlt and query actual DuckDB IDs."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time

from runtime import arguments, prepare


def dictionary(dlt, duckdb, work):
    source = [
        [[{"id": 1, "ts": 2}]],
        [[{"id": 1, "ts": 2}], [{"id": 2, "ts": 2}]],
    ]
    requested = []

    @dlt.resource(name="events", primary_key="id")
    def events(pages, ts=dlt.sources.incremental(
            "ts", initial_value=0, range_start="closed", row_order="desc")):
        for index, page in enumerate(pages, 1):
            requested.append(index)
            yield page

    con = duckdb.connect(":memory:")
    pipeline = dlt.pipeline(pipeline_name="witness_dictionary",
                            pipelines_dir=str(work / "dictionary"),
                            destination=dlt.destinations.duckdb(credentials=con))
    record = {"witness": "A", "source_rounds": source, "cursor_field": "ts",
              "row_order": "desc", "range_start": "closed", "expected_ids": [1, 2],
              "error": None, "rounds": []}
    try:
        for pages in source:
            requested.clear()
            info = pipeline.run(events(pages))
            with pipeline.sql_client() as client:
                rows = client.execute_sql("SELECT id, ts FROM events ORDER BY id")
            record["rounds"].append({
                "requested_pages": list(requested),
                "target_rows": rows,
                "target_ids": [int(row[0]) for row in rows],
                "state": json.loads(json.dumps(pipeline.state, default=str)),
                "has_failed_jobs": info.has_failed_jobs,
            })
        final = record["rounds"][-1]
        record["missing_ids"] = sorted(set(record["expected_ids"]) - set(final["target_ids"]))
        expected_target = [1] if dlt.__version__ == "1.31.0" else [1, 2]
        expected_requests = [1] if dlt.__version__ == "1.31.0" else [1, 2]
        record["acceptance"] = {
            "target_ids": expected_target, "requested_pages": expected_requests,
            "prior_target_ids": [1], "prior_requested_pages": [1],
        }
        record["pass"] = (
            record["rounds"][0]["target_ids"] == [1]
            and record["rounds"][0]["requested_pages"] == [1]
            and final["target_ids"] == expected_target
            and final["requested_pages"] == expected_requests
            and not any(row["has_failed_jobs"] for row in record["rounds"])
        )
    except Exception as error:
        record["error"] = repr(error)
        record["pass"] = False
    finally:
        con.close()
    return record


def arrow(dlt, duckdb, pa, work, ordered):
    source = [[{"id": 1, "ts": None}, {"id": 2, "ts": None}],
              [{"id": 3, "ts": 5}, {"id": 4, "ts": 6}]]
    requested = []
    name = "arrow_ordered" if ordered else "arrow_control"

    @dlt.resource(name="events", primary_key="id")
    def events(ts=dlt.sources.incremental(
            "ts", initial_value=0, end_value=10, range_end="open",
            row_order="asc" if ordered else None, on_cursor_value_missing="exclude")):
        schema = pa.schema([("id", pa.int64()), ("ts", pa.int64())])
        for index, batch in enumerate(source, 1):
            requested.append(index)
            yield pa.Table.from_pylist(batch, schema=schema)

    con = duckdb.connect(":memory:")
    pipeline = dlt.pipeline(pipeline_name=name, pipelines_dir=str(work / name),
                            destination=dlt.destinations.duckdb(credentials=con))
    record = {"witness": "B" if ordered else "B_control", "source_batches": source,
              "schema": {"id": "int64", "ts": "int64"}, "cursor_field": "ts",
              "initial_value": 0, "end_value": 10, "range_end": "open",
              "null_policy": "exclude", "row_order": "asc" if ordered else None,
              "expected_ids": [3, 4], "error": None}
    try:
        info = pipeline.run(events())
        with pipeline.sql_client() as client:
            exists = client.execute_sql(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='events'")[0][0]
            rows = client.execute_sql("SELECT id, ts FROM events ORDER BY id") if exists else []
        record.update(target_rows=rows, target_ids=[int(row[0]) for row in rows],
                      target_table_exists=bool(exists), has_failed_jobs=info.has_failed_jobs,
                      state=json.loads(json.dumps(pipeline.state, default=str)))
        record["missing_ids"] = sorted(set(record["expected_ids"]) - set(record["target_ids"]))
        wanted_ids, wanted_requests = ([], [1]) if ordered else ([3, 4], [1, 2])
        record["acceptance"] = {"target_ids": wanted_ids, "requested_batches": wanted_requests}
        record["pass"] = (record["target_ids"] == wanted_ids
                          and requested == wanted_requests and not info.has_failed_jobs)
    except Exception as error:
        record["error"] = repr(error)
        record["pass"] = False
    finally:
        record["requested_batches"] = list(requested)
        con.close()
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    arguments(parser)
    args = parser.parse_args()
    started = time.monotonic()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="w-", dir=args.output) as directory:
        work = Path(directory)
        dlt = prepare(args, work)
        import duckdb
        import pyarrow as pa

        records = [dictionary(dlt, duckdb, work)]
        if args.version == "1.32.0":
            records.extend(arrow(dlt, duckdb, pa, work, ordered) for ordered in (True, False))
        payload = {
            "validation_kind": "submission_preparation_deterministic_replay",
            "observed_at_utc": datetime.now(timezone.utc).isoformat(),
            "environment": {"python": sys.version, "dlt": dlt.__version__,
                            "duckdb": duckdb.__version__, "pyarrow": pa.__version__},
            "elapsed_seconds": time.monotonic() - started,
            "records": records, "all_pass": all(record["pass"] for record in records),
        }
    path = args.output / f"witnesses-{args.version}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    print(json.dumps({"output": path.name, "all_pass": payload["all_pass"],
                      "records": len(records)}, ensure_ascii=False), flush=True)
    return 0 if payload["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
