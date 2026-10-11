# Pre-registration

**Status: DRAFT.** Freeze by changing the status to `FROZEN <date> <research commit>` before the
first confirmatory run of E3, E4 or E6. After that, every change goes to `DEVIATIONS.md`.

**Snapshot:** B1 (`5d73d4b`), Dokploy 0.30.6 and 0.30.7 by digest (`config/snapshots.yaml`).

## Hypotheses and decision rules

| ID | Hypothesis | Measure | Supported if |
|----|------------|---------|--------------|
| H1 | Every non-faulted run converges. | k = number of applies until `plan --detailed-exitcode` returns 0 | k ≤ 2 in every run (stricter k = 1 reported separately) |
| H2 | Apply at convergence is idempotent. | mutating calls (non-GET) on one extra apply, from the proxy log | 0 in every run |
| H3 | Converged remote state equals declared state. | O-raw mismatches on owned paths | 0 in every run |
| H4 | Unmanaged resources are untouched. | O-unmanaged snapshot diff | empty in every run (any violation falsifies) |
| H5 | Drift is planned precisely. | plan after a drift operator vs its expected plan (`diac.harness.perturb.DRIFT_OPERATORS`) | exact match in every run |
| H6 | Recovery is safe. | outcome after one injected fault per mutation index | no *unsafe* outcome (any falsifies) |
| H7 | Plans are deterministic. | three consecutive `plan --json` outputs | byte-identical |
| H8 | Round trip holds. | field diff of import(I) vs import(rebuild(I)) after ADR 0011 normalisation | empty on both versions |
| H9 | Grammar saturates. | share of spec-only onboarding events in the last third of kinds (E5) vs the first third | descriptive; no threshold |

## Fixed parameters

- Repetitions per (scenario, condition, version): 5.
- k_max: 2 (H1); runner stops at k_max + 3 and records `not_converged`.
- Settling rule after a deploy: wait for the deployment record to report `done` or `error`, maximum 20 min.
- Drift operators: `owned_field`, `unowned_field`, `delete_managed`, `colliding_sibling`,
  `secret_rotation`, `env_var_added`, `env_var_changed`, `reparent`, `ignored_path`.
- Fault kinds: `drop_before`, `drop_after`, `status_503`, `delay` (30 s).
- Failure classification: Hassan et al. 2024 categories plus `dokploy-specific`.
- Exclusions: a run is excluded only for infrastructure failure *before* the first SUT command
  (image pull, port conflict); every exclusion is listed with its cause.

## Scenario corpus

Listed by file under `experiments/e3_convergence/scenarios/`; the list is frozen with this file.
