# Architecture and code review of dokploy-iac at snapshot B1

*Snapshot B1 = commit `5d73d4b` (2026-10-10), version `0.1.0-beta.1`, Dokploy 0.30.6 and 0.30.7.
Reviewed from the repository read-only: ADRs 0001–0020, `docs/design/*`, `ARCHITECTURE.md`,
`CONTEXT.md`, the 36 kind specs, the engine sources, CI configuration, local CI logs under
`target/`, and the git history of the spec-driven engine (from `c1606aa`, the first kind spec).
Quantities come from E0, E1 and E5 in this repository (`results/*/B1/`).*

## 1. Summary for the paper

The beta has a **spec-driven architecture**: each Dokploy kind is described once, as data, in a YAML *kind spec*, and a
kind-agnostic engine derives everything else from it — parser, JSON Schema, discovery, projection,
create/update bodies, import, convergence proof, conformance scenarios and simulator behaviour.
This makes the paper's central artefact **an intermediate
specification language that supplies the declarative semantics a procedure-oriented API lacks**,
together with the evidence machinery that keeps those specs honest against the real API.

The architecture is coherent and unusually well documented. The safety model is explicit (29
invariants). The verification pipeline — a field-classification ledger, spec-derived conformance
suite, simulator, live suite and round-trip gate — is stronger than what most published IaC tools
report. The findings below do not undermine the design. They are places where the documentation
claims more than the code does, where the evidence is internal rather than independent, or where
a claim needs re-framing before it appears in a paper.

## 2. The system as a research artefact

| Layer | What it is at B1 | Size (non-generated) |
|-------|------------------|----------------------|
| Contract | Pinned OpenAPI 3.1 for 0.30.6 and 0.30.7 (604 operations, 57 routers, every 200 response an empty object) and 731 recorded live fixtures (366 for 0.30.6, 365 for 0.30.7) | — |
| Generated transport | `dokploy-api` bindings and `dokploy api <resource> <operation>` for all 604 operations | ≈55,600 generated lines |
| **Kind specs** | 36 kinds (19 project, 17 settings), 625 properties, 63 write groups, 0 declared hooks | 3,288 YAML lines |
| Spec tooling | `dokploy-spec` (grammar, registry, ledger), `dokploy-model` (documents) | 6,800 src lines |
| Kernel | `dokploy-core` (pure planner), `dokploy-state` (state v5, journal, lock, fingerprints) | 10,344 src lines |
| Engine | `dokploy-engine`: discover, compile, project, plan, apply, recover, deploy, import | 10,446 src lines |
| Evidence | `dokploy-conformance`, `dokploy-sim`, live suite, round-trip gate, upstream watch | 4,573 src lines |

Four contributions are separable and each can be evaluated on its own terms:

1. **C1, a specification language for RPC-to-declarative bridging.** Its constructs name exactly the
   semantics the API leaves implicit: natural key and collision rule; role of each operation;
   *write groups* (one object written by several endpoints, `partial`/`full`/`by_variant`); how a new
   identity is learned (`from_response`, `diff_collection`, `none`); read *authority* (`authoritative`,
   `partial`, `agree`); mutability (`in_place`, `create_only`, `reparent`, `write_only`, `computed`);
   value class (public, secret, content); and structural shapes (unions planned per member,
   several parents, selector sets, relations changed one member at a time, singletons, asymmetric
   nullability).
2. **C2, a kind-agnostic reconciliation engine** over a pure planner, with journaled steps, read-back
   verification, outcome-unknown handling and evidence-based recovery.
3. **C3, a completeness and conformance method.** The *coverage ledger* fails CI on any request or
   response field of a used operation that is not classified (`mapped`, `readonly`, `action`, `ignored`
   with a reason, or `derived`). Conformance scenarios are generated from each spec. A simulator
   driven by the same specs is checked against live Dokploy. The round-trip contract states when an
   instance counts as reproduced.
4. **C4, the Dokploy case** as empirical evidence for C1–C3.

## 3. Strengths

- **Completeness is checkable.** At B1 the ledger reports 614 mapped, 32 read-only, 23 ignored,
  8 derived and 0 unclassified fields across 36 kinds (E1). This is an operational answer to "what
  fraction of the API is managed", which most IaC tools cannot give.
- **Presence semantics are precise.** Omitted means unmanaged, `null` means cleared, and a value means
  managed (ADR 0004), extended consistently to environment blocks, selector sets and relations
  (ADRs 0010, 0019). This matches the ownership models of Kubernetes server-side apply and makes
  "the document owns what it names" testable.
- **Uncertain outcomes are first-class.** A mutation is sent once, a transport failure after sending is
  *outcome unknown*, and `recover` decides from a fresh read against the journaled target state, with
  "a person decides" as the explicit fallback (`docs/design/engine.md`, recovery table).
- **Read-back verification per step** turns invariant 22 into a local check (ADR 0008).
- **Fail-closed discovery.** Partial collections, collections that contradict direct reads, foreign
  parents and oversized lists make exactly the affected addresses unavailable rather than guessed.
- **Secrets never enter state or plans.** Receipts are keyed HMAC-SHA-256 values bound to instance,
  address and path, and every conformance scenario runs a canary scan.
- **Version drift is a CI event.** A scheduled upstream watch diffs new OpenAPI releases against the
  ledger (ADR 0014).

## 4. Findings that affect the paper

Severity: **B** = blocks freezing B1 for confirmatory runs; **D** = must be disclosed or resolved
before a claim is made; **M** = minor.

| # | Finding | Evidence | Sev. | Action |
|---|---------|----------|------|--------|
| F1 | The last local CI logs show live-suite failures: `an_environment_value_and_a_content_edited_at_dokploy_are_drift_the_engine_repairs` (plan blocked, `DOKPLAN005`) and `an_application_reaches_done_through_the_deployment_engine`. An earlier run also failed the organization test, which ADR 0020 then addressed. | `target/ci-38043579124-live-0307.log` (13 passed, 2 failed), `target/ci-38040363432/live-0306.log` (12/3) | B | Confirm CI is green at `5d73d4b` on both versions. If not, fix and move B1, or freeze with the failures recorded as known defects. |
| F2 | Documentation describes behaviour the engine does not implement. (a) ADR 0008: "later independent steps still run; dependents of a failed step are skipped". `apply/run.rs` returns at the first failed change, as `engine.md` states. (b) ADR 0008 and ADR 0017 give `apply --parallelism`; only `deploy` takes it. (c) ADR 0008 says the spec states the replacement order. The grammar has no such field, and `spec-format.md` says replacement always deletes first. | `crates/dokploy-engine/src/apply/run.rs:93-101`, `crates/dokploy-cli/src/cli.rs:178`, `docs/design/spec-format.md` (Property paths) | D | Amend ADRs 0008 and 0017 to match the code, or implement. The paper must describe the implemented semantics. |
| F3 | The cost model held for a minority of kinds. ADRs 0002 and 0015 target "a flat kind adds a spec file; no Rust". At onboarding, 7 of 36 kinds were spec-only (port, security, five databases). 29 arrived with kernel/engine changes, 6,873 engine lines in total, mostly new grammar. | E5 `kind_onboarding.csv` | D | Re-frame as **grammar saturation**: the grammar grew while new API patterns appeared. Report onboarding cost over time and per pattern (E7). |
| F4 | "Kind-agnostic engine" is nearly but not fully true: 0 declared hooks, but 13 production code sites in engine sources test a kind name (3 further matches are in an inline test module) (`server` local selector in `selectors.rs`, `project.rs`, `compile.rs`, `import.rs`; `vault_provider` in `discover.rs`; application/compose deployment types in `deploy.rs` and `recover.rs`; `github_provider` and `project` in `import.rs`). | `grep` over `crates/dokploy-engine/src` | D | Declare them as hooks with reasons (invariant 25) or move them into the grammar. Report the residual count in the paper. |
| F5 | The simulator is derived from the same specs and fixtures as the engine, so conformance against it shows *engine–spec consistency*, not *spec–Dokploy correctness*. ADR 0015 says the same scenarios run live; the live engine suite in the CI logs has 15 tests. | ADR 0015 layer 6; CI logs | D | Report which (scenario, kind) pairs run live. E3/E4 add an independent live check. |
| F6 | `project`, the root kind of every project document, has `coverage: partial`. | `specs/project/project.yaml`; ledger | M | Complete it or state the gap. |
| F7 | Response-side completeness is bounded by the fixtures: a field that no capture shows cannot be classified, so "0 unclassified" means relative to the 366 (0.30.6) and 365 (0.30.7) captured fixtures. | ADR 0002; `fixtures/api/live/` | D | State the bound. Optionally measure fixture coverage per used read operation. |
| F8 | Reproducibility of evidence: the SUT had no tags, and the only local binary was built 30 min before B1. | `git tag` (empty); E1 provenance | B | **Resolved 2026-10-11:** tag `eval-B1` → `5d73d4b`; release binary built on a clean tree, SHA-256 `55ec8a81…497c` pinned in `config/snapshots.yaml`. The ledger from the release binary is identical to the earlier one for all 36 kinds. |
| F9 | 60 of the 90 commits since the first kind spec carry an AI-assistant co-author trailer. | E5 summary | D | Disclose in the paper. Do not use elapsed time as an effort measure. Use code and spec size, and onboarding events. |
| F10 | `validate` defaults to `dokploy.yaml` while `plan` defaults to the workspace manifest. Confirmed on the B1 release binary: in a manifest-only workspace, `dokploy validate` exits 1 (`cannot read dokploy.yaml`). | `dokploy validate --help`; run in `experiments/e3_convergence/scenarios/templates/tag` | M | Make `validate` default to the manifest, like `plan`. Until then the harness passes `--file`. |

## 5. What this means for the research questions

- **RQ1** can now be answered concretely. The kind specs are a human-authored annotation of the API,
  so the question becomes how much of that annotation is irreducible human knowledge and how much a
  tool could infer (E2). E0 gives the first data point: 35% of the operations the specs need have
  names a CRUD heuristic would not recognise.
- **RQ2** already has strong developer-side evidence (conformance, live suite, round-trip gate). The
  paper needs an *independent* evaluation as well (E3, E4, E6), because that internal evidence shares
  its specs with the system under test (F5).
- **RQ3** has a natural data source: every grammar extension and every residual kind branch is an
  API property that resisted the generic model (ADRs 0018–0020, F3, F4).
- **RQ4** can be measured inside the beta, as the split of per-kind work between specs and engine
  code and its onboarding curve (E5), with a general-purpose generator as external comparison (E8).

## 6. Checklist before confirmatory runs

1. Resolve F1 (F8 is resolved).
2. Resolve or document F2 and F4 in the SUT's ADRs, so the paper and the code agree.
3. Freeze `evaluation/PREREGISTRATION.md` (status → `frozen`, with date and research-repo commit).
4. Run E0, E1 and E5 again on the frozen snapshot, then E3/E4/E6 with Docker.
