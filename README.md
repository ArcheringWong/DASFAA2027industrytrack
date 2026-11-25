# Successful Loads, Missing Records

This package executes two finite omission witnesses on released dlt, reruns the repaired Oracle boundary checks, and reconstructs Tables 1–3 from saved per-case inputs and outputs. All records are synthetic integer IDs and cursors. Execution uses local in-memory DuckDB. No remote source, account, API credential, or database service is required.

## Environment

Validated on Windows with CPython 3.11.4, dlt 1.31.0 and 1.32.0, DuckDB 1.5.6, PyArrow 26.0.0, and Hypothesis 6.170.15. Keep the two dlt versions in separate environments. Full pinned requirements are in `requirements-1.31.0.txt` and `requirements-1.32.0.txt`. Windows-only packages have platform markers. A complete dependency install is a public package download and requires network access to PyPI. Execution after installation is local, with dlt telemetry disabled. This package contains scripts and data, with no vendored wheels or virtual environments.

From the package directory, create two environments using Python 3.11. On Windows run:

```powershell
py -3.11 -m venv env131
py -3.11 -m venv env132
env131/Scripts/python.exe -m pip install -r requirements-1.31.0.txt
env132/Scripts/python.exe -m pip install -r requirements-1.32.0.txt
env131/Scripts/python.exe -B run_witnesses.py --version 1.31.0 --output replay
env132/Scripts/python.exe -B run_witnesses.py --version 1.32.0 --output replay
env131/Scripts/python.exe -B check_oracle.py --version 1.31.0 --output replay
env132/Scripts/python.exe -B check_oracle.py --version 1.32.0 --output replay
```

On POSIX systems, use the environment's `bin/python` entry point. Product execution was verified on Windows. A fresh POSIX dependency installation has not been tested. Put the extracted package in a short writable path if Windows long-path support is disabled. The product and tests create temporary state beneath the selected output directory and remove it after each run.

`--dependency-path` optionally supplies an existing installed package directory. Repeated paths are searched in the specified order. The submission checks used that option with the previously restored, hash-documented environment, invoked under `python -S -B` to isolate the host's older NumPy. These paths are execution-time arguments and are not required by the code.

## Witnesses and expected observations

| Command | Real execution and acceptance |
|---|---|
| Witnesses 1.31.0 | Dictionary round 1 confirms ID 1 at cursor 2. Round 2 contains old ID 1 on page 1 and new ID 2 at cursor 2 on page 2. Required IDs are `[1,2]`. The affected version requests `[1]` and leaves `[1]`. |
| Witnesses 1.32.0, A | The same two-round Dictionary input requests `[1,2]` and loads `[1,2]`. This is the released-fix control. |
| Witnesses 1.32.0, B | Typed int64 Arrow batches contain IDs 1/2 with null cursors, then IDs 3/4 at cursors 5/6. Ascending range `[0,10)` and null exclusion request only `[1]`, leaving an empty target where `[3,4]` were required. |
| Witnesses 1.32.0, B control | The same Arrow input with ordering omitted requests `[1,2]` and loads `[3,4]`. The package does not claim a released Arrow-fix comparison. |

Acceptance means that the observed version-specific behavior matches this table, including zero product exceptions. The successful reproduction of the affected case still demonstrates missing records. JSON includes all input records, schema, expected and actual IDs, requested pages or batches, observed state, and product error fields. Independent original 1.29.0 Arrow and Dictionary outputs are retained in `archive/support/`.

The Oracle runner reproduces 1 check on 1.31.0 and 11 on 1.32.0. It explicitly tests default and explicit open ends, closed ends, below/start/interior/equal/above-bound records, excluded and included nulls, bounded prior state, the two omission paths, and rejection of changed end modes or non-neutral null prefixes. Repaired adapters in `code/` match the isolated repair byte-for-byte. The historical change is documented in `code/oracle-repair.diff`. Two of the 12 assertions reject transformations before product execution.

## Reconstructing Tables 2 and 3

This step uses only Python's standard library and performs no product execution.

```powershell
python -B verify_artifact.py
python -B recompute_tables.py --output recomputed
```

The script verifies the archive hashes, independently computes required IDs with the corrected integer max-cursor contract, compares them with saved targets and requests, and reconstructs per-version classifications and fixed calls. It expects 28 version-cases, comprising 2 violations, 13 passes, 1 inconclusive base, and 12 invalid transformations. Fixed A/B/C calls are 17/17/34, 25/25/50, 19/19/38 and 18/18/36. Prior-state setup is included.

Run `python -B recompute_table1.py --output recomputed-table1` to independently rebuild Table 1 from recorded source histories, contracts, request traces and target IDs. The four rows are cross-checked against the original per-release observations.

Saved B exploration adds 40/34/30/37 product calls in the four independent snapshots. Counts cover the final retained executions, including prior-state setup. Earlier overwritten development runs prevent reconstruction of lifetime totals. At least three generated histories have visible saved-layout inconsistencies caused by later in-place mutation of the batch list. Other mutations cannot be ruled out solely from request indices. Fixed-history checks pass. `recomputed.json` identifies the affected records and scope limitations.

## Shrinking counts and protocol deviations

These are archived results, not new experiments. The path-redacted summaries retain all counters, operations, inputs and outputs; only local directory metadata is replaced. Original and publication SHA-256 hashes and the modified JSON Pointers are recorded in [supplement-provenance-20261125.json](supplement-provenance-20261125.json).

| Archived shrinking run | Status | Observed scenario executions (`total_real_runs`) | Best witness operations | Budget (`budget`) |
|---|---|---:|---:|---:|
| [Dictionary boundary](archive/support/shrink_d1_summary.json) | `hypothesis_completed` | 5 | 4 | 30 |
| [All-null Arrow batch](archive/support/shrink_generic_summary.json) | `budget_exhausted_best_observed` | 29 | 7 | 30 |

The Dictionary result is one completed automatic shrinking run with five scenario executions, not five independently shrunk cases. It is separate from the earlier manually reduced witness. For Arrow, 29 is the observed execution count, not the budget; the best verified witness has seven operations and automatic shrinking did not finish. Scenario executions are not `pipeline.run()` call counts. These summaries provide evidence for the reported units; they do not rerun the full D1/D2 generation studies or establish a minimal Arrow witness.

The relevant maintenance-study records are:

- [Frozen D4 protocol](archive/d4/D4_EXPERIMENT_PROTOCOL.md), line 7: the original cap was eight scenarios per scheme and version.
- [D4 evidence audit](archive/d4/D4_EVIDENCE_AUDIT.md), line 15: the final 1.32.0 suites retained ten fixed cases for T1/T2 and nine for T3. The cap was not enforced. Calls are charged as actually recorded; the comparison is not a strict equal-budget contest.
- [D4 evidence audit](archive/d4/D4_EVIDENCE_AUDIT.md), line 13: the initial stateful baseline selected only the first six cases. Its revisions expanded case selection, added unconditional reselection, limited retained evaluations, and prioritized the newly added cases. The final baseline was rerun; overwritten or failed earlier attempts do not count as independent samples.
- [Pre-revision state machine](archive/d4/evidence/development_pre_fix_stateful_b.py) and [saved framework failure](archive/d4/evidence/development_B_T1_132_invalid_definition.log) retain the implementation history.

The audit also documents shared input preparation through the paired-input validator and the finite scope of the stateful baseline. The final-snapshot call counts do not establish total development cost, independent preparation effort, or a maintenance advantage. Replay limitations for mutable generated batch histories remain as described above and under Resources and coverage.

## Contents and provenance

- `archive/` contains selected D3/D4 source, fixtures, per-case outputs, manifests, and protocols. Local path metadata has been replaced by neutral placeholders in review copies. `archive/provenance.json` retains both the original and review-file hashes. Frozen historical source retains its original inclusive-end predicate. Use the repaired `code/` for the new Oracle executions.
- `archive/support/` contains original minimal witness outputs and selection records. `support-provenance.json` maps these and the repaired code to their sources.
- `validation/witnesses-*.json` and `validation/oracle-*.json` are actual submission-preparation deterministic executions. `validation/original-oracle-*.json` are earlier repaired-Oracle results. New validation runs are additional correctness checks and do not enter any historical D1–D5 denominator.
- `validation/table_recomputation/` contains offline results derived from the historical traces. `MANIFEST.json` hashes the reviewed package. Verification checks those recorded files and permits new replay output in separate directories.
- `dependency-provenance.json` documents the wheel hashes used in the restored validation environment. Host cache paths have been omitted from this packaging description.
- `redaction-provenance.json` records changed local-path metadata fields and both file hashes. IDs, cursors, inputs, target rows, requests, status labels and costs are preserved. The frozen originals remain outside this review bundle.
- `figure_sources/` contains both SVG/PDF diagrams and original drawing code. `rebuild_figures.py --output figure-rebuild` reproduces the SVGs exactly and validates PDF text and vector content. It requires Pillow, ReportLab, Poppler and the Windows Arial/Segoe UI Symbol fonts. Product witnesses and table recomputation do not require these drawing dependencies.

## Resources and coverage

The tests need a writable directory and a local CPU. They use tiny synthetic histories and an in-memory database. Actual elapsed durations and runtime versions are stored in each validation JSON. Memory use was not benchmarked. Dependency installation time and download size depend on platform and cache.

The minimal package does not rerun the D1/D2 generation studies or the full D5 stopping audit. D3/D4 table reconstruction verifies saved evidence, with invalid classifications relying on the recorded legality findings and zero-execution evidence. The package includes D4 configurations and original implementations for inspection. Exact fresh replay of all B generated histories and all development attempts cannot be recovered from the retained archive. The paper's limits on independent test preparation, developer time, and maintenance advantage remain applicable.

This repository contains the reproducibility package accompanying *Successful Loads, Missing Records: Release-Time Completeness Checks for Cursor-Based Extraction*. It is a publication copy of the path-redacted author-review bundle. `publication-provenance.json` records the source-package hashes and the documentation/index changes; experimental source, fixtures, validation records, and figure files retain their original bytes. `.gitattributes` disables line-ending conversion so recorded hashes remain valid across checkouts.

The repository does not include the paper source, unrelated projects, credentials, or installed dependency environments. See `NOTICE.md` for the licensing status and dependency attribution.
