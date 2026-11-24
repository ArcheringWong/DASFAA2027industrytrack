# Frozen D3 and D4 evidence

The files in `d3/` and `d4/` preserve selected original experimental inputs,
implementation, per-case product outputs, final run manifests and relevant logs.
Local path metadata in review copies has been replaced by neutral placeholders.
`provenance.json` maps files to their source-relative paths, original hashes
and review hashes. `../redaction-provenance.json` identifies changed fields.
No runtime databases, pickle files, installed packages,
virtual environments, credentials or private configuration directories are included.

The original scripts are historical implementation evidence. Their paths assume
the original Windows workspace and their end-bound oracle includes equality.
The repaired oracle code is provided separately under the artifact's `code/`.
Use the top-level artifact commands for fresh minimal execution and offline
table reconstruction. Running historical scripts here can overwrite evidence.

`recompute_tables.py` reads the original case configurations and product traces,
rederives valid-pair and single-run outcomes from required and actual target IDs,
and accounts for current runs and prior setup runs in the fixed product calls.
It verifies invalid-case zero execution and reads the archived validity findings.
It verifies the final three schemes agree on the prepared-case outcomes.
It does not use `summary.json` as a count input.

The D4 B JSONs include the final retained bounded state-machine explorations.
The development failure log and pre-fix source are retained separately. The
runner replaced earlier versions of some output files, so these materials
cannot reconstruct a complete development-lifetime exploration or retry cost.
At least three generated traces also retain a batch-list reference that was later
coalesced in place before JSON serialization. Their recorded requests exceed
the count of batches in the saved list. The table recomputation flags those
exact rows, verifies the retained call counters against setup/current-run
structure, and keeps the fixed regression records' stricter layout check.
Shared references can permit further mutations that leave no request/count
contradiction, so exact replay of all saved generated layouts is unestablished.
