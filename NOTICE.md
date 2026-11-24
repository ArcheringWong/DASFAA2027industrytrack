# Notices and scope

This repository publishes a reproducibility artifact for *Successful Loads, Missing Records: Release-Time Completeness Checks for Cursor-Based Extraction*.

No blanket MIT, Apache, or other open-source license grant has been added to this repository. Public accessibility should not be interpreted as a new license grant. Original notices, provenance and source references are retained.

The runtime dependencies dlt, DuckDB, PyArrow and Hypothesis are installed separately from the pinned requirements. Their respective licenses continue to apply; dependency wheels and environments are not distributed here.

- dlt: https://github.com/dlt-hub/dlt
- DuckDB: https://github.com/duckdb/duckdb
- PyArrow: https://github.com/apache/arrow
- Hypothesis: https://github.com/HypothesisWorks/hypothesis

The two dlt defects and repair references are identified in the archived protocols, source comments, and support provenance. These references do not imply that the artifact authors discovered the upstream defects. All fixture records are synthetic. The README describes the limitations of replaying historical exploration runs.
