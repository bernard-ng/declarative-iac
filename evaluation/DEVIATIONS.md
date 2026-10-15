# Deviations from the pre-registration

Every change made after the tag `prereg-v1` to `evaluation/PREREGISTRATION.md` or to a frozen
input (`config/scenarios/`, `config/observer.yaml`, `config/drift.yaml`, `config/faults.yaml`)
is recorded here before the runs it affects, with a new tag.

| # | Date | Tag | What changed | Why | Effect on results |
|---|---|---|---|---|---|
| — | — | — | none yet | — | — |

## Harness checks before the tag

These runs checked that the harness works end to end. They are not part of the pilot or of any
reported result, and they changed no frozen input.

| Date | Run | Outcome |
|---|---|---|
| 2026-10-15 | `live smoke`: one L1 run of `unit-tag` on Dokploy 0.30.6 (`results/live/pilot/smoke/`) | completed; two harness defects found by the first attempt were fixed in the harness before it (Docker configuration redirect, fingerprint key format) |

