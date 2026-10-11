# E1: Spec expressiveness and semantic inventory

**Question.** What semantic information did the authors have to add on top of the OpenAPI contract,
and how is it distributed across kinds? (RQ1; feeds RQ3)

**Inputs.** `specs/**/*.yaml` at the snapshot; optionally `dokploy coverage` from a binary built at the
snapshot commit (the field-classification ledger).

**Outputs.** `kinds.csv` (per-kind profile), `properties.csv` (one row per property, union-arm member,
struct member), `grammar_usage.csv` (kind × grammar feature), `coverage_ledger.csv`, `summary.json`.

**Preliminary result (B1, exploratory).** 36 kinds (19 project, 17 settings), 625 properties
(532 in-place, 49 write-only, 31 create-only, 13 computed; 50 secret, 11 content). 63 write groups;
14 kinds are written through more than one operation. New identities are learned from the create
response for 19 kinds and by diffing the collection for 14; 3 kinds are adopt-only. 0 declared hooks.
Ledger from the pinned B1 release binary (SHA-256 verified): 614 mapped, 32 read-only,
23 ignored, 8 derived, **0 unclassified**; `project` is still `coverage: partial`.

**Threat.** `grammar_usage` counts syntactic presence; it does not prove a feature was necessary.
E7 links each feature to the API behaviour that motivated it.
