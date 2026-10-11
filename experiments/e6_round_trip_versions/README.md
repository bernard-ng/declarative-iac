# E6: Round trip and cross-version behaviour

**Question.** Does `import(apply(import(I)))` equal `import(I)` under the normalisation of ADR 0011, on
both supported Dokploy versions, and what changes between versions? (RQ2, RQ3)

**Design.** Reuse the SUT's seeding script for a rich instance, then verify independently: a field-wise
diff of the two imported workspaces computed by this repository (not by the SUT's gate), plus O-raw
checks of the rebuilt instance. Repeat for 0.30.6 and 0.30.7, and record the ledger diff between the
two OpenAPI documents (E0 shows no added or removed operations between them).

**Status.** Designed. Depends on the SUT's `scripts/integration/test-round-trip-live.sh` for seeding.
