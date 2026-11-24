"""Reconstruct Tables 2 and 3 from archived per-case inputs and product traces.

Uses only Python's standard library. No product execution and no summary JSON
is used as a numerical input. All original archive files are hash checked first.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VERSIONS = ("1.31.0", "1.32.0")
SNAPSHOTS = ("base", "T1", "T2", "T3")
STATUSES = ("TRUE_VIOLATION", "PASS", "INCONCLUSIVE", "INVALID_TRANSFORMATION")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def verify_archive():
    provenance = load(ROOT / "archive/provenance.json")
    for item in provenance["files"]:
        path = ROOT / item["archive_path"]
        require(path.is_relative_to(ROOT / "archive"), f"Invalid archive path: {path}")
        require(sha256(path.read_bytes()).hexdigest() == item["sha256"],
                f"Archive hash mismatch: {path}")
    return len(provenance["files"])


def required_ids(case, batches):
    """Independent integer max-cursor obligation with explicit range-end mode."""
    end = case.get("end_value")
    end_mode = case.get("range_end", "open")
    policy = case.get("missing_policy", "exclude")
    require(end_mode in ("open", "closed"), "Unsupported end mode")

    def eligible(row, start):
        value = row["ts"]
        if value is None:
            return policy == "include"
        within_end = end is None or value < end or (value == end and end_mode == "closed")
        return value >= start and within_end

    prior = [row for batch in case.get("prior_batches", []) for row in batch if eligible(row, 0)]
    prior_ids = {row["id"] for row in prior}
    checkpoint = 0
    if end is None:
        checkpoint = max((row["ts"] for row in prior if row["ts"] is not None), default=0)
    current_ids = {row["id"] for batch in batches for row in batch if eligible(row, checkpoint)}
    return prior_ids | current_ids


def trace_calls(trace, *, check_current_layout=True):
    """Each completed adapter trace contains a current call and optional setup call."""
    require(trace["error"] is None, "Saved product error requires separate call accounting")
    require(trace["target_ids"] == sorted({int(row[0]) for row in trace["target_rows"]}),
            "Target rows and target IDs differ")
    for batches_key, requests_key in (("prior_batches", "prior_requested_batches"),
                                      ("current_batches", "requested_batches")):
        requested = trace[requests_key]
        require(requested == list(range(1, len(requested) + 1)), "Non-prefix source request trace")
        if check_current_layout or batches_key == "prior_batches":
            require(len(requested) <= len(trace[batches_key]), "Requests exceed supplied source batches")
    return 1 + int(bool(trace["prior_batches"]))


def pair_outcome(record, case):
    check = record["validation"]
    if not check["valid"]:
        require(check["reasons"] and record["base"] is None and record["transformed"] is None,
                "Invalid pair unexpectedly executed")
        return "INVALID_TRANSFORMATION", 0
    base = record["base"]
    variant = record["transformed"]
    require(base["current_batches"] == case["base_batches"], "Base input mismatch")
    require(variant["current_batches"] == check["variant_batches"], "Variant input mismatch")
    expected = required_ids(case, case["base_batches"])
    require(expected == required_ids(case, check["variant_batches"]), "Pair changes the ID obligation")
    require(sorted(expected) == check["original_oracle"]["final_ids"] ==
            check["transformed_oracle"]["final_ids"], "Saved valid-pair oracle differs")
    calls = trace_calls(base) + trace_calls(variant)
    base_missing = sorted(expected - set(base["target_ids"]))
    variant_missing = sorted(expected - set(variant["target_ids"]))
    require(base_missing == record["base_missing_ids"] and
            variant_missing == record["transformed_missing_ids"], "Saved omission list differs")
    if base_missing:
        return "INCONCLUSIVE", calls
    if variant_missing:
        return "TRUE_VIOLATION", calls
    return "PASS", calls


def single_outcome(record, case, *, check_current_layout=True):
    if case.get("invalid_reason"):
        require(record["trace"] is None and record["pipeline_calls"] == 0,
                "Prepared-invalid case unexpectedly executed")
        return "INVALID_TRANSFORMATION", 0
    trace = record["trace"]
    require(trace["current_batches"] == case["base_batches"], "Single-run input mismatch")
    expected = required_ids(case, trace["current_batches"])
    missing = sorted(expected - set(trace["target_ids"]))
    require(sorted(expected) == record["expected_ids"] and missing == record["missing_ids"],
            "Saved single-run identity diagnosis differs")
    calls = trace_calls(trace, check_current_layout=check_current_layout)
    require(calls == record["pipeline_calls"], "Saved call counter differs from trace structure")
    if case.get("baseline_incomplete"):
        return "INCONCLUSIVE", calls
    return ("TRUE_VIOLATION" if missing else "PASS"), calls


def d3_table():
    directory = ROOT / "archive/d3"
    cases = load(directory / "cases.json")
    table = []
    details = []
    calls = 0
    for version in VERSIONS:
        inputs = [case for case in cases if version in case["versions"]]
        records = load(directory / "evidence" / f"metamorphic_{version}.json")
        require([record["name"] for record in records] == [case["name"] for case in inputs],
                f"D3 case selection differs for {version}")
        counts = Counter()
        for case, record in zip(inputs, records):
            require(record["case"] == case and record["dlt_version"] == version,
                    "D3 embedded case/version differs")
            status, product_calls = pair_outcome(record, case)
            require(status == record["status"], f"D3 classification differs: {version}/{case['name']}")
            counts[status] += 1
            calls += product_calls
            details.append({"version": version, "name": case["name"], "status": status,
                            "pipeline_calls": product_calls})
        table.append({"version": version, **{status: counts[status] for status in STATUSES},
                      "total": len(records)})
    totals = {status: sum(row[status] for row in table) for status in STATUSES}
    require(totals == {"TRUE_VIOLATION": 2, "PASS": 13, "INCONCLUSIVE": 1,
                       "INVALID_TRANSFORMATION": 12}, "Table 2 differs from paper")
    require(calls == 52, "D3 product-call total differs")
    return table, details, calls


def d4_tables():
    directory = ROOT / "archive/d4"
    table = []
    details = []
    exploration = []
    layout_findings = []
    expected_calls = ((17, 17, 34), (25, 25, 50), (19, 19, 38), (18, 18, 36))
    for snapshot, expected_row in zip(SNAPSHOTS, expected_calls):
        manifest = load(directory / "evidence" / snapshot / "manifest.json")
        require({(item["scheme"], item["version"]) for item in manifest} ==
                {(scheme, version) for scheme in ("a", "b", "c") for version in VERSIONS}
                and len(manifest) == 6 and all(item["exit_code"] == 0 for item in manifest),
                f"Incomplete final snapshot manifest: {snapshot}")
        sums = Counter()
        by_version = {version: {} for version in VERSIONS}
        for scheme in ("a", "b", "c"):
            cases = load(directory / "snapshots" / snapshot / f"{scheme}_cases.json")
            for version in VERSIONS:
                inputs = [case for case in cases if version in case["versions"]]
                raw = load(directory / "evidence" / snapshot / f"{scheme}_{version}.json")
                records = raw["deterministic"] if scheme == "b" else raw
                require([record["name"] for record in records] == [case["name"] for case in inputs],
                        f"D4 inputs differ: {snapshot}/{scheme}/{version}")
                outcomes = {}
                for case, record in zip(inputs, records):
                    status, calls = (pair_outcome(record, case) if scheme == "c"
                                     else single_outcome(record, case))
                    require(status == record["status"] == record["expected_status"] ==
                            case["expected_status_by_version"][version], "D4 fixed classification differs")
                    sums[scheme] += calls
                    outcomes[case["name"]] = status
                    details.append({"snapshot": snapshot, "scheme": scheme, "version": version,
                                    "name": case["name"], "status": status, "pipeline_calls": calls})
                by_version[version][scheme] = outcomes
                if scheme == "b":
                    input_by_name = {case["name"]: case for case in inputs}
                    generated = raw["state_machine_exploration"]
                    generated_calls = 0
                    for index, record in enumerate(generated):
                        case = dict(input_by_name[record["name"]])
                        case["base_batches"] = record["trace"]["current_batches"]
                        status, calls = single_outcome(record, case, check_current_layout=False)
                        require(status == record["status"], "D4 exploration classification differs")
                        trace = record["trace"]
                        if len(trace["requested_batches"]) > len(trace["current_batches"]):
                            layout_findings.append({"snapshot": snapshot, "version": version,
                                                    "exploration_index": index,
                                                    "name": record["name"],
                                                    "requested_batches": trace["requested_batches"],
                                                    "saved_current_batch_count": len(trace["current_batches"]),
                                                    "finding": "Generated batch list retained by reference and later coalesced before serialization."})
                        generated_calls += calls
                    exploration.append({"snapshot": snapshot, "version": version,
                                        "recorded_histories": len(generated),
                                        "recorded_pipeline_calls": generated_calls,
                                        "scope": "final_saved_snapshot_only"})
        require(all(arms["a"] == arms["b"] == arms["c"] for arms in by_version.values()),
                "Schemes disagree on final prepared outcomes")
        require(tuple(sums[scheme] for scheme in ("a", "b", "c")) == expected_row,
                "Table 3 differs from paper")
        if snapshot == "base":
            added_cases = 0
        else:
            added = [len(load(directory / "snapshots" / snapshot / f"{scheme}_cases.json")) -
                     len(load(directory / "snapshots/base" / f"{scheme}_cases.json"))
                     for scheme in ("a", "b", "c")]
            require(len(set(added)) == 1, "Schemes added different case counts")
            added_cases = added[0]
        table.append({"snapshot": snapshot, "added_cases": added_cases,
                      **{scheme.upper(): sums[scheme] for scheme in ("a", "b", "c")}})
    return table, details, exploration, layout_findings


def write_csv(path, rows):
    with path.open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "validation/table_recomputation")
    args = parser.parse_args()
    archive_files = verify_archive()
    table2, d3_details, d3_calls = d3_table()
    table3, d4_details, exploration, layout_findings = d4_tables()
    args.output.mkdir(parents=True, exist_ok=True)
    for filename, rows in (("table2-by-version.csv", table2), ("d3-case-classification.csv", d3_details),
                           ("table3-fixed-calls.csv", table3), ("d4-fixed-case-calls.csv", d4_details),
                           ("d4-recorded-exploration.csv", exploration)):
        write_csv(args.output / filename, rows)
    result = {"archive_hashes_checked": archive_files, "table2": table2, "table3": table3,
              "d3_pipeline_calls": d3_calls, "d4_recorded_exploration": exploration,
              "d4_exploration_layout_findings": layout_findings,
              "checks": {"status_rederived_from_targets_and_validity_evidence": True,
                         "independent_integer_open_end_obligation": True,
                         "fixed_calls_rederived_from_current_and_prior_run_traces": True,
                         "all_three_final_scheme_outcomes_agree": True,
                         "no_summary_json_used_for_counts": True},
              "limitations": [
                  "Invalid classifications use saved validity findings and zero-execution evidence.",
                  "A/B invalid and baseline-incomplete flags are prepared labels; construction is not independent of C.",
                  "Final successful snapshots overwrite some development attempts. Recorded exploration totals exclude unretained attempts.",
                  "At least three generated traces visibly retain a batch-list reference subsequently coalesced in place. Their original page layout cannot be fully reconstructed; further mutations need not produce a visible request/count contradiction. Fixed records pass layout checks.",
                  "The archive contains historical inclusive-end code. Independent recomputation uses corrected eligibility; repaired execution code is under code/.",
                  "This program verifies saved execution traces and does not rerun D3 or D4.",
              ]}
    (args.output / "recomputed.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    markdown = ["# Tables recomputed from saved per-case evidence", "",
                "| Table 2 outcome | 1.31.0 | 1.32.0 | Total |", "|---|---:|---:|---:|"]
    for status in STATUSES:
        values = [row[status] for row in table2]
        markdown.append(f"| {status} | {values[0]} | {values[1]} | {sum(values)} |")
    markdown.extend(("", "| Table 3 snapshot | Added cases | A | B | C |", "|---|---:|---:|---:|---:|"))
    for row in table3:
        markdown.append(f"| {row['snapshot']} | {row['added_cases']} | {row['A']} | {row['B']} | {row['C']} |")
    markdown.extend(("", "Recorded B exploration is reported separately by version in d4-recorded-exploration.csv.",
                     "These files cover the final retained snapshots. Earlier overwritten attempts prevent a full development-lifetime total.",
                     f"{len(layout_findings)} generated records have directly visible saved-layout inconsistencies after execution; see recomputed.json for the exact records. Shared list references allow further undetectable layout mutations. Fixed records pass the source-request bounds check.", ""))
    (args.output / "tables.md").write_text("\n".join(markdown), encoding="utf8")
    print(json.dumps({"verified_archive_files": archive_files, "table2_version_cases": len(d3_details),
                      "d3_pipeline_calls": d3_calls, "table3": table3,
                      "recorded_exploration_calls": sum(row["recorded_pipeline_calls"] for row in exploration),
                      "generated_layout_findings": len(layout_findings),
                      "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
