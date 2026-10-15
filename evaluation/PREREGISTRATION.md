# Pre-registration of the live evaluation (Section 9)

This document fixes, before any live run, what the live experiments do, what they measure, and
how each hypothesis is decided. It is frozen by the git tag `prereg-v1` on this repository. Any
later change to this file or to the inputs listed in "Frozen inputs" is a deviation and is
recorded in [DEVIATIONS.md](DEVIATIONS.md) with its date, reason and effect, under a new tag
(`prereg-v1.1`, …). Results are always reported against the tag they were run under.

## 1. Disclosure

The author of the system under study (dokploy-iac) also wrote this harness and these scenarios.
The design limits what that can bias:

- the harness never imports or edits the system; it runs the pinned release binary as a black
  box and reads the system's repository only through `git show` at the pinned commit;
- every oracle is independent of the system's kind specifications: expected plans are written
  from the design (Sections 4–6), observations use Dokploy's own response names taken from
  recorded responses (`config/observer.yaml`), and the observer can only call allowlisted GET
  operations;
- scenarios, drift operators, faults, hypotheses and decision rules are fixed here first, and
  every cell is reported, including failures.

## 2. System, versions and host

| Item | Value |
|---|---|
| System | dokploy-iac `0.1.0-beta.1`, commit `5d73d4b932251c9540c0a8dd6358edd5bc076d16` (tag `eval-B1`), snapshot B1 |
| Binary | release build of that commit; sha256 per platform in `config/snapshot.yaml`, recorded in every manifest |
| Dokploy | every version in `specs/versions.yaml` at the commit (0.30.6 and 0.30.7), pulled by image digest |
| Instance | `compose.yaml` of this repository, which mirrors the system's `compose.integration.yaml` at the commit (`provenance verify` reports any other difference), with the system's bootstrap sequence (administrator, organisation, API key); on `127.0.0.1` only |
| Host | Docker with Swarm initialised; Linux or macOS. Host, Docker version and CPU/RAM are recorded in each manifest |

Each repetition starts from a fresh instance: the stack and its volumes are removed, fresh secrets are written, and the stack is started and bootstrapped again. The harness talks to
the instance through its fault proxy in every experiment, so mutation counts are always measured;
outside L3 the proxy injects nothing.

## 3. Frozen inputs

| Input | Path | Checked by |
|---|---|---|
| Scenarios (4 families, 28 scenarios, 40 steps) | `config/scenarios/*.yaml` | S6-scenarios: every document passes `dokploy validate`; two negative controls are rejected |
| Observer read model (16 collections) | `config/observer.yaml` | S6-scenarios: every name occurs in a recorded response |
| Drift operators (7) | `config/drift.yaml` | S6-scenarios: every write is a POST of the contract with known body fields |
| Fault plan (3 scenarios × 4 kinds × 3 ordinals) | `config/faults.yaml` | S6-scenarios |
| This document | `evaluation/PREREGISTRATION.md` | the tag |

The sha256 of every input is recorded in `results/static/S6-scenarios/B1/manifest.json` and in
the manifest of every live cell; a cell whose inputs differ from the tagged ones is not reported
under that tag.

## 4. Experiments and cells

A **cell** is one combination of the factors below; a **run** is one repetition of a cell on a
fresh instance. Secrets get fresh canary values in every run (`diac-canary-<label>-<hex>`).

| Exp. | Question | Factors | Repetitions | Runs |
|---|---|---|---|---|
| L1 | Does the system converge, and stay converged? | scenario (28) × version (2) | 5 | 280 |
| L2 | Does it see exactly the drift it owns? | drift operator (7) × version (2) | 5 | 70 |
| L3 | Is an interrupted apply safe to resume? | fault scenario (3) × kind (4) × ordinal (3) × version (2) | 3 | 216 |
| L4 | Does a populated instance survive import? | seed (1) × version (2) | 5 | 10 |

L3 uses three repetitions because the fault is placed deterministically (by mutation ordinal);
repetitions only vary timing. L4's seed is the union of `realistic-webapp`, `realistic-compose`
and `unit-application-children`, applied to one instance.

### 4.1 Procedure

Every command is the system's CLI, run by the harness in the run's workspace with an isolated
environment (`PATH`, a private `HOME`, `DOKPLOY_URL`, `DOKPLOY_API_KEY`, a fixed
`DOKPLOY_FINGERPRINT_KEY`, the step's secrets, `NO_COLOR`). Output, exit codes, durations and
the proxy log are kept under `results/live/<exp>/B1/<version>/<cell>/<run>/raw/`.

**Settling.** After every apply and every harness write, the observer reads its collections every
2 s until two consecutive snapshots are equal, for at most 60 s. A run that does not settle is
marked `unsettled`; it still counts for every hypothesis except H3.

**L1, per step of the scenario.** (1) Apply the step's seed writes, if any. (2) Snapshot the
observer (baseline). (3) Materialise the step. (4) `plan` twice (P1, P1′). (5) Repeat `apply --auto-approve`
(plus the step's `apply_flags`) and `plan` until the plan reports no changes (exit 0) or
`k_max = 3` applies have run; k is the number of applies. (6) `plan` again (P2) and
`apply --auto-approve` on the converged workspace (A0). (7) Settle, snapshot, check observations
and the step's expectation. For a step whose expectation has `apply_exit` or `refused`, step 5 is
a single apply and the next step starts from whatever it left.

**L2.** Run L1 up to the operator's start step; snapshot; make the operator's write through
Dokploy's API (the only harness mutation); settle; `plan` (PD); apply until converged
(`k_max = 3`); snapshot.

**L3.** First, one fault-free reference apply of the scenario's first step on the same version
gives its mutation count m, which fixes the ordinals (1, ⌈m/2⌉, m) before the faulted runs.
Then: materialise; `apply` through the proxy with the fault armed; `recover --file <document>
--auto-approve` for every document; apply until converged (`k_max = 3`); snapshot; classify.

**L4.** On instance A: converge the seed (as L1); `import all --directory import-1 --env file`
and again into `import-1b`; in `import-1`, `plan` (PI). Then on a fresh instance B of the same
version: copy `import-1` without `.dokploy/state/`, apply until converged (`k_max = 3`), and
`import all` into `import-2`.

## 5. Hypotheses and decision rules

Each hypothesis is a property that should hold in **every** run. It is **supported** if no run
violates it and **refuted** otherwise; each violating run is reported individually. For every
hypothesis we also report the proportion of runs satisfying it with a Wilson 95% interval, per
version and pooled across versions (never across snapshots).

| | Hypothesis | Measure | Runs |
|---|---|---|---|
| H1 | **Convergence.** Every step converges within two applies. | k ≤ 2 (k = 1 reported separately) | L1, L2, L3, L4 |
| H2 | **Quiescence.** No plan mutates Dokploy, and an apply on a converged workspace makes no mutation. | POST count in the proxy log during every plan, and during A0, is 0 | all |
| H3 | **Observed agreement.** After convergence, every observation of the step holds in Dokploy. | `observe` assertions, evaluated on the settled snapshot | L1 (settled runs) |
| H4 | **Containment.** Nothing outside the declared configuration changes. | Every baseline object whose name is not declared by the step is identical in the final snapshot (`diff_snapshots`); L2's `untouched` objects likewise | L1, L2, L3 |
| H5 | **Exact drift.** The plan after a drift write contains exactly the expected changes. | Multiset of (`kind`, address suffix) in PD equals the operator's `expect.changes` | L2 |
| H6 | **Safe interruption.** No faulted run ends in an unsafe outcome (§6). | Outcome class | L3 |
| H7 | **Determinism.** Plans depend only on configuration and state. | (a) P1 and P1′ are byte-identical; (b) the first plans of a cell's runs are equal after removing `lineage`, `stateSerial` and `configDigest` (the digest covers secret fingerprints, and canaries differ between runs) | L1 |
| H8 | **Round trip.** An import of a converged instance is a fixed point, and rebuilding from it reproduces it. | PI reports no changes; `import-1` and `import-1b` are byte-identical; B converges; `import-1` and `import-2` are byte-identical, excluding `.dokploy/state/` | L4 |

Lifecycle steps also have an expectation (`expect` in the scenario): the exact changes of the
step's first plan, and for some steps the apply exit code, a mutation count, or objects that must
be present or absent afterwards. A failed expectation is reported with H5 as a planning error.

Secondary, descriptive measures (no hypothesis): plan size, mutations per apply, wall time per
command, k = 1 rate, and differences between Dokploy versions.

**Secret handling** is checked in every run: no canary may appear in any captured output, plan,
state file or other workspace file outside `.dokploy/secrets/` (`canary.scan`). A hit is an
unsafe outcome (U5) wherever it occurs and is reported under H6 for L3 and as a separate count
for the other experiments.

## 6. Outcome classes for L3

| Class | Meaning | Safe |
|---|---|---|
| C1 converged | after recovery the workspace converges within `k_max`, H3/H4 hold, nothing duplicated | yes |
| C2 blocked | the system stops with a diagnostic that names the affected resource and needs an operator decision; no unsafe effect | yes |
| U1 duplicate | two Dokploy objects for one declared resource | no |
| U2 orphan | an object the system created is neither tracked nor reported | no |
| U3 collateral | an undeclared object changed (H4 violated) | no |
| U4 wrong value | the system reports convergence while an observation fails | no |
| U5 leak | a canary appears outside the secrets directory | no |
| U6 crash | an exit code other than 0, 1 or 2, a panic, or no diagnostic on failure | no |

A run is assigned the first class in the order U5, U1, U2, U3, U4, U6, C2, C1 that it meets.
Each unsafe run is also coded against the eight categories of state-reconciliation defects of
[Hassan et al. 2024](https://doi.org/10.1145/3660790), using that paper's definitions; the
coding is the author's alone and is reported as such.

## 7. Exclusions, reruns and stopping

- A run is rerun (up to twice) only if the instance fails before the system's first command:
  the image cannot be pulled, the stack does not become healthy, or the API key cannot be
  created. Every rerun is logged with its cause.
- Once the system's first command has run, the run counts, whatever happens.
- There is no adaptive stopping: all runs in §4 are executed. If the host cannot complete them,
  the missing runs are listed and no hypothesis is reported as supported on partial data.

## 8. Pilot

Before the confirmatory runs, one repetition of every L1 cell on 0.30.6 checks that each scenario
is feasible on a bare instance (for example, that a registry or backup destination can be
created without a reachable endpoint). The pilot is not counted. A scenario found infeasible is
removed or changed before the confirmatory runs, recorded in DEVIATIONS.md, and tagged
`prereg-v1.1`; the pilot's results are reported in an appendix.

## 9. What these experiments do not test

Git-provider, server, Vault, DNS-provider, SSH-key and certificate kinds (9 of 36) need external
accounts, a second host or key material, and are not exercised; S6-scenarios lists them. The
notification kind is applied but not observed (no recorded response to ground an observer in).
Deployments (`deploy`) are not part of these experiments. These limits are reported in Section 10.
