"""Reconstruct Table 1 from saved real product outputs and recorded source inputs.

Uses the standard library only. No product runs and no paper table are inputs.
The dictionary source is the recorded minimal replay at cursor 2, matching the
original two-round fixture. Oracle pair tests at cursor 1 are separate inputs.
"""

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8-sig"))


def flatten(batches):
    return [row for batch in batches for row in batch]


def closed_start_ids(rounds):
    prior, current = rounds
    confirmed = flatten(prior)
    start = max(row["ts"] for row in confirmed)
    required = {row["id"] for row in confirmed}
    required.update(row["id"] for row in flatten(current) if row["ts"] >= start)
    return sorted(required), start


def open_end_ids(batches, start, end):
    return sorted({identity for batch in batches
                   for identity, cursor in zip(batch["id"], batch["ts"])
                   if cursor is not None and start <= cursor < end})


def dictionary_rows():
    source_paths = [f"validation/witnesses-{version}.json" for version in ("1.31.0", "1.32.0")]
    replays = [next(row for row in read(path)["records"] if row["witness"] == "A")
               for path in source_paths]
    require(all(row["row_order"] == "desc" and row["range_start"] == "closed" and
                row["error"] is None for row in replays), "Dictionary replay contract changed")
    source = replays[0]["source_rounds"]
    require(source == replays[1]["source_rounds"], "Dictionary releases have different inputs")
    require(source == [[[{"id": 1, "ts": 2}]],
                       [[{"id": 1, "ts": 2}], [{"id": 2, "ts": 2}]]],
            "Table 1 must use the original cursor-2 two-page shape")
    expected, cursor = closed_start_ids(source)
    result, details, inputs = [], [], source_paths[:]
    for version, replay in zip(("1.31.0", "1.32.0"), replays):
        path = f"archive/support/dlt_{version.replace('.', '_')}.json"
        inputs.append(path)
        original = read(path)
        require(original["dlt_version"] == version, "Wrong original dictionary release")
        record = next(row for row in original["cases"] if row["case"] == "issue_4523")
        require(record.get("error") is None and "state" in record, "Original run did not succeed")
        require(record["first_pages"] == replay["rounds"][0]["requested_pages"] == [1],
                "Prior setup trace changed")
        target = sorted({int(row[0]) for row in record["rows"]})
        checkpoints = [entry["resources"]["events"]["incremental"]["ts"]["last_value"]
                       for entry in record["state"]["sources"].values()]
        require(checkpoints == [cursor], "Original dictionary checkpoint differs from cursor 2")
        require(record["second_pages"] == replay["rounds"][1]["requested_pages"],
                "Original and new replay request traces disagree")
        require(target == replay["rounds"][1]["target_ids"], "Original and replay targets differ")
        wanted_requests = [1] if version == "1.31.0" else [1, 2]
        wanted_target = [1] if version == "1.31.0" else expected
        require(record["second_pages"] == wanted_requests and target == wanted_target,
                "Original dictionary outcome differs from its documented control")
        row = {"run": f"Closed start, dlt {version}", "requested": record["second_pages"],
               "required_ids": expected, "target_ids": target, "error": None}
        result.append(row)
        details.append({"source": path, "cursor": cursor, **row})
    return result, details, inputs


def arrow_rows():
    details, inputs = [], []
    replay_path = "validation/witnesses-1.32.0.json"
    replay = next(row for row in read(replay_path)["records"] if row["witness"] == "B")
    require(replay["initial_value"] == 0 and replay["end_value"] == 10 and
            replay["range_end"] == "open" and replay["null_policy"] == "exclude" and
            replay["row_order"] == "asc", "Arrow replay contract changed")
    inputs.append(replay_path)
    original_sources = []
    issue_results = []
    for version in ("1.29.0", "1.32.0"):
        path = f"archive/support/calibrate_{version}_pipeline.json"
        inputs.append(path)
        records = read(path)
        issue = next(row for row in records if row["mode"] == "issue")
        require(issue["dlt_version"] == version and issue["level"] == "REAL_PIPELINE",
                "Arrow input is not the saved release pipeline")
        source = issue["source_batches"]
        require(source == [{"id": [1, 2], "ts": [None, None]},
                           {"id": [3, 4], "ts": [5, 6]}], "Arrow fixture changed")
        recorded_rows = [[{"id": identity, "ts": cursor}
                          for identity, cursor in zip(batch["id"], batch["ts"])]
                         for batch in source]
        require(recorded_rows == replay["source_batches"], "Arrow original and replay inputs differ")
        original_sources.append(source)
        expected = open_end_ids(source, replay["initial_value"], replay["end_value"])
        require(issue["expected_ids"] == expected, "Source-derived Arrow obligation differs")
        require(issue["requested_batches"] == [1] and issue["output_ids"] == [] and
                issue["error"] is None, "Affected Arrow release outcome changed")
        row = {"run": f"Null-first Arrow, dlt {version}", "requested": issue["requested_batches"],
               "required_ids": expected, "target_ids": issue["output_ids"], "error": issue["error"]}
        issue_results.append(row)
        details.append({"source": path, "mode": "issue", **row})
        if version == "1.32.0":
            control = next(row for row in records if row["mode"] == "no_order")
            require(control["source_batches"] == source, "Control changed the Arrow source")
            require(control["requested_batches"] == [1, 2] and control["output_ids"] == expected and
                    control["expected_ids"] == expected and control["error"] is None,
                    "Arrow unordered control changed")
            control_row = {"run": "Arrow control without row_order, dlt 1.32.0",
                           "requested": control["requested_batches"], "required_ids": expected,
                           "target_ids": control["output_ids"], "error": control["error"]}
            details.append({"source": path, "mode": "no_order", **control_row})
    require(original_sources[0] == original_sources[1], "Affected Arrow releases used different sources")
    require(all(issue_results[0][key] == issue_results[1][key]
                for key in ("requested", "required_ids", "target_ids", "error")),
            "Affected Arrow versions cannot share one Table 1 row")
    grouped = dict(issue_results[0], run="Null-first Arrow, dlt 1.29.0 and 1.32.0")
    return [grouped, control_row], details, inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "validation/table1")
    args = parser.parse_args()
    dictionary, dictionary_details, dictionary_inputs = dictionary_rows()
    arrow, arrow_details, arrow_inputs = arrow_rows()
    rows = dictionary + arrow
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "table1.csv").open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows({key: json.dumps(value) if isinstance(value, list) else
                         ("None" if value is None else value) for key, value in row.items()}
                        for row in rows)
    payload = {"table1": rows, "per_release": dictionary_details + arrow_details,
               "input_hashes": {path: sha256((ROOT / path).read_bytes()).hexdigest()
                                for path in dictionary_inputs + arrow_inputs},
               "derivation": {
                   "dictionary": "Prior confirmed IDs union current IDs at or above the closed start.",
                   "arrow": "Non-null IDs whose source cursor lies in [0,10).",
                   "dictionary_input_source": "Recorded minimal replay source_rounds, same two-round cursor-2 fixture as the original script.",
                   "dictionary_success": "Original successful record contains rows/state; exception records use an error field.",
                   "oracle_pair_distinction": "D3 Oracle pair tests at cursor 1 are not substituted for the Table 1 cursor-2 input.",
                   "excluded_controls": ["tie_same_page", "no_tie_desc", "ascending_newer", "nonnull_first"],
               }, "pass": True}
    (args.output / "table1-recomputed.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"table1_rows": len(rows), "per_release_records": len(payload["per_release"]),
                      "input_files": len(payload["input_hashes"]), "pass": True}))


if __name__ == "__main__":
    main()
