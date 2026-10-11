# Methodology (version 2)

*Version 2, written after the beta of dokploy-iac (snapshot B1, commit `5d73d4b`, 2026-10-10).
The study evaluates the beta only. What changed from version 1, and why, is in §9.
Preliminary numbers quoted here come from exploratory runs of E0, E1 and E5 and will be
re-computed on the frozen snapshot before they are reported as results.*

## 1. Aim and research questions

The study asks whether a declarative control plane can be built over an API that exposes
procedures rather than resources, what has to be added to the API description to make that
possible, and what it costs. The case is Dokploy, a self-hosted deployment platform whose tRPC
API is exported as an OpenAPI 3.1 document with 604 operations. The system under study (SUT) is
dokploy-iac, a spec-driven IaC engine for Dokploy.

- **RQ1 (semantics).** What semantic information must be added to a procedure-oriented API
  description so that resources can be planned, applied, imported and verified declaratively, and
  how much of it could be inferred automatically?
- **RQ2 (reliability).** Does a kind-agnostic engine driven by that information converge, stay
  idempotent, recover safely from uncertain outcomes, and round-trip an instance?
- **RQ3 (obstacles).** Which properties of the API forced extensions of the specification grammar
  or kind-specific code?
- **RQ4 (effort).** How much of the work of supporting a resource kind is carried by its
  specification rather than by engine code, and how does that compare with what a general-purpose
  OpenAPI generator recovers from the same contract?

## 2. Research design

The study combines three strategies, each matched to the questions it can answer.

1. **Design-science evaluation of an artefact** ([Hevner et al. 2004](https://doi.org/10.2307/25148625);
   [Wieringa 2014](https://doi.org/10.1007/978-3-662-43839-8)). The artefact is the specification
   language plus the kind-agnostic engine. It is evaluated against explicit criteria: the 29
   invariants of the SUT and the hypotheses in §6.
2. **Embedded single-case study** of Dokploy, reported following
   [Runeson & Höst 2009](https://doi.org/10.1007/s10664-008-9102-8). It is used for RQ1 and RQ3:
   the API, the specs, the ADRs and the history are analysed as case data.
3. **Controlled experiments** on disposable, digest-pinned Dokploy instances
   ([Wohlin et al. 2012](https://doi.org/10.1007/978-3-642-29044-2)). They are used for RQ2, plus a
   **repository-history analysis** of the beta for RQ4.

Two tiers of evidence are kept apart throughout, because they differ in independence:

- **Developer evidence** is produced by the SUT's own test machinery: the coverage ledger, the
  spec-derived conformance suite on the simulator, the live suite and the round-trip gate. It is
  reported as the SUT's verification claims, with counts.
- **Independent evidence** is produced by this repository's harness. The harness is written in Python,
  imports no SUT crate, reads the SUT only through `git show` at the snapshot commit, runs the CLI as a
  black box, and observes Dokploy through a read-only HTTP client and a recording proxy. Findings in
  the paper's Results come from this tier unless labelled otherwise.

## 3. System under study and snapshots

Snapshots are defined in `config/snapshots.yaml` and every output is stored under
`results/<experiment>/<snapshot>/` with a manifest recording the SUT commit, the research-repository
commit, the command and the time.

| Snapshot | Commit | Role |
|----------|--------|------|
| **B1** | `5d73d4b` (0.1.0-beta.1, 2026-10-10) | Object of evaluation; Dokploy 0.30.6 and 0.30.7 |

B1 is frozen for confirmatory runs once the code-review blockers are resolved
(`docs/code-review.md`, F1 live failures; F8, the tag and binary hash, was resolved on 2026-10-11). If the SUT changes afterwards, a
new snapshot (B2, ...) is added and earlier experiments are re-run on it; results are reported per
snapshot and never pooled. Dokploy images are pinned by digest (`specs/versions.yaml` at B1).

## 4. Experiments

The experiment folders hold runnable code and a README each; this section gives the method.

### E0 – API census (RQ1, RQ3)

All operations of both pinned OpenAPI documents were enumerated. Each was assigned a lexical role
from its procedure name (create, read_one, list, update, delete, other), its request-field count, and
whether its 200 response schema is the closed empty object. Operations were then joined with the
roles the B1 specs give them (create, update, remove, deploy, read_list, read_one, read_singleton,
write_group, membership, entry). The specs serve as an expert annotation of which operations a
declarative engine needs. *Exploratory result:* 604 operations in 57 routers on both versions, with
no operation added or removed between them; all 604 responses are untyped. The specs use 223
operations in 37 routers, and 78 of those (35%) lack a CRUD-like name.

### E1 – Specification inventory (RQ1)

Every kind spec at B1 was parsed with an independent YAML loader. For each kind the following were
recorded: identity strategy, read mode and authority, write groups by shape, mutability and value
class of every property (including union-arm and struct members), and the grammar constructs it
uses. The field-classification ledger was captured with `dokploy coverage` from a binary built at the
snapshot. The binary's build time is checked against the snapshot commit and a mismatch is recorded
in the manifest. *Exploratory result:* 36 kinds, 625 properties, 63 write groups, 0 declared hooks;
ledger 614 mapped, 32 read-only, 23 ignored, 8 derived, 0 unclassified (pinned B1 release binary).

### E2 – Automatic inference against the specs (RQ1)

The B1 specs are the gold standard. To reduce single-author bias, a second annotator independently
re-derives a stratified sample of 9 kinds (three flat settings kinds, three project leaves, three
services) from the OpenAPI document, the fixtures and the Dokploy UI. Agreement is reported per
target as Cohen's κ ([Cohen 1960](https://doi.org/10.1177/001316446002000104)), and disagreements
are adjudicated and logged. An inference prototype then predicts, for every kind:

- operation roles and the write-group partition;
- the id field and parameter;
- the create-identity strategy;
- the parent attachment field;
- the mutability class, the value class and nullability of each field.

The prototype uses cumulative sources: (1) names, (2) request schemas, (3) recorded fixtures, and
(4) optional live probing, where a field is created, updated and read back. Precision, recall and F1
are reported per target and source level, together with the share of spec content that no source
recovers ("irreducible annotation"). The E0 lexical mapping is the baseline. This design adapts
dependency inference from REST testing ([Atlidakis et al. 2019](https://doi.org/10.1109/icse.2019.00083))
to the different goal of resource-model inference.

### E3 – Convergence, idempotency and safety (RQ2)

**Scenarios.** Scenarios are generated systematically:

- **S-unit:** one per kind, with minimal and maximal field sets.
- **S-topology:** containment and reference graphs, from a single chain to a project with several
  environments, services, databases and domains, including several-parent kinds.
- **S-lifecycle:** moves, removals with retain and destroy, `ignore_changes`, protection,
  `create_only` changes that force replacement, and adopt-only settings.
- **S-realistic:** stacks taken from Dokploy templates.

**Initial conditions.**

- `empty`: a fresh instance and no state.
- `engine_partial`: a converged workspace, then a subset of resources deleted through the
  imperative CLI.
- `brownfield`: resources created imperatively, then adopted with `import all`.
- `drifted:<operator>`: a converged workspace, then one pre-registered drift operator applied
  (§6, H5).

Each (scenario, condition) cell runs five times on each Dokploy version.

**Procedure.** Each run starts from a fresh workspace and a fresh instance. The harness constructs the
condition, then alternates `apply` and `plan --detailed-exitcode` until the plan exit code is 0, with
an upper bound of k_max + 3 applies. After convergence it applies the oracles below.

**Oracles.**

- O-plan: the SUT's own plan.
- O-raw: field checks written from Dokploy responses, not from the specs.
- O-traffic: mutation count on one further apply, from the recording proxy.
- O-unmanaged: an instance snapshot before and after, excluding managed identities.
- Determinism: three consecutive plans must be byte-identical.
- Canary scan: every secret is given a canary value; the workspace and all captured output are scanned.

**Measures.** Convergence rate with Wilson 95% intervals, the distribution of k, reads and mutations
per apply, and wall time. Every failure is classified with the state-reconciliation categories of
[Hassan et al. 2024](https://doi.org/10.1145/3660790) plus a Dokploy-specific residual category.

### E4 – Fault injection and recovery (RQ2)

For each scenario plan with n mutations, one fault is injected at mutation i = 1..n by the recording
proxy. The fault kinds are a dropped request, a response lost after Dokploy committed the change, a
503, and a delay. The harness then runs `recover --auto-approve` followed by `apply`. Outcomes are
**converged**, **refused with evidence**, or **unsafe** (duplicate remote object, lost identity,
dangling reference, or a repeated mutation visible in the call log). The fault classes are those of
the SUT's simulator, so E4 also tests whether the simulator's fault model holds on a real instance.
The perturbation approach follows [Sun et al. 2022 (Sieve, OSDI)](https://www.usenix.org/conference/osdi22/presentation/sun),
adapted from controller state views to an RPC transport.

### E5 – Where the per-kind effort goes (RQ4)

The beta's own history is analysed from the commit that introduced the first kind spec (`c1606aa`)
to B1. The measures are:

- non-generated Rust lines per crate at B1, split into `src/` and `tests/`, and spec lines per kind;
- for each kind, the commit that introduced its spec and the kernel and engine lines added in that
  commit, giving spec-only and spec-plus-engine onboarding events;
- the engine lines added per onboarding event over time, to test whether the grammar saturates (H9).

Elapsed time is not used: 60 of the 90 commits in the window carry an AI-assistant co-author
trailer, so commit timestamps do not measure human effort. *Exploratory result:*

- B1 has 40,836 src and 21,221 test lines of non-generated Rust, and 3,272 spec lines for 36 kinds
  (median 70 lines per kind).
- 7 of 36 kinds were spec-only at onboarding; 29 needed engine changes (6,873 lines over 18
  onboarding commits).
- Engine lines per third of the onboarding events were 3,549, 1,093 and 2,231, so the data do not
  yet show saturation.

### E6 – Round trip across versions (RQ2, RQ3)

The SUT's seeding script populates a rich instance. Then `import all` is run, the instance is
rebuilt fresh, the workspace is applied and deployed, and `import all` is run again. The two
workspaces are compared field by field by this repository, using ADR 0011's normalisation as
written, and the rebuilt instance is checked with O-raw. The procedure is repeated on 0.30.6 and
0.30.7. Differences are classified as a normalisation gap, a spec defect, or an API behaviour change.

### E7 – Obstacle catalogue and scorecard (RQ3)

Three sources are coded:

1. every grammar construct in E1, linked to the ADR or commit that introduced it and the API
   behaviour that motivated it;
2. every residual kind-name branch in engine code (13 production sites at B1);
3. a per-router scorecard of declarative-friendliness criteria derived from Google AIP-121/128
   and the ADRs (`experiments/e7_api_friendliness/scorecard.yaml`).

Two coders code independently, and agreement is reported. The output links each API property
to the grammar feature or code it required, the kinds affected, and any E3, E4 or E6 failure it
explains.

### E8 – General-purpose generator baseline (RQ4)

HashiCorp's `tfplugingen-openapi` is run on the same pinned OpenAPI document with a minimal mapping
configuration per B1 kind. For each kind the comparison records: kinds mapped, attributes typed,
computed/required/optional classification, configuration lines needed, and the B1 constructs the
generator cannot express (empty response schemas, multiple write operations, union-dispatched
writes, write-only secrets, relations, singletons).

## 5. Execution environment

Git-only experiments (E0, E1, E2 sources 1–3, E5, E7) run anywhere with Python ≥ 3.11 and the
packages in `pyproject.toml`. Live experiments (E2 source 4, E3, E4, E6) need Docker, the SUT's
`compose.integration.yaml`, the digest-pinned Dokploy images, and a release binary built at the
snapshot commit whose SHA-256 is recorded in `config/snapshots.yaml`. One host is used for all live
runs; its CPU, memory, operating system and Docker version are recorded in each manifest.

## 6. Hypotheses

The hypotheses, stated in full in `evaluation/PREREGISTRATION.md`, are:

- **H1:** convergence within k ≤ 2.
- **H2:** zero mutations on an apply at convergence.
- **H3:** O-raw agreement on every owned path.
- **H4:** no change outside the managed set.
- **H5:** the plan for a drift operator equals the operator's expected plan.
- **H6:** no unsafe outcome after any injected fault.
- **H7:** byte-identical plans.
- **H8:** round-trip equality under ADR 0011's normalisation on both versions.
- **H9:** spec-only onboarding becomes the norm once the grammar covers a kind family (a descriptive
  test on E5 data).

## 7. Threats to validity

- **Construct.**
  - An empty plan is circular evidence of convergence if the projection is wrong. O-raw and O-traffic
    are independent of it.
  - Lines of code measure size, not effort. Onboarding events and grammar growth complement them.
  - "0 unclassified" is bounded by the captured fixtures (code-review F7).
- **Internal.**
  - The author designed both the SUT and the evaluation. This is mitigated by pre-registration, a
    second annotator and coder, and a harness that shares no code with the SUT.
  - The simulator is derived from the specs, so simulator results are reported only as developer
    evidence (F5).
  - Asynchronous Dokploy work can make outcomes flaky. This is mitigated by repetitions and explicit
    settling rules in the pre-registration.
- **External.**
  - The study has one platform, two adjacent Dokploy versions and one engine. The E7 scorecard is
    applied to one or two other self-hosted platform APIs to test whether the obstacles recur.
  - The history analysis covers one developer and one platform; its onboarding curve is reported
    descriptively, not as a cost model for other APIs.
- **Conclusion.**
  - There are few runs per cell, so counts and intervals are reported rather than significance tests.
  - Any H4 or H6 violation counts as a falsifier regardless of its rate.
- **Disclosure.** The SUT was developed with AI coding assistance (E5). The paper states this and
  avoids effort claims that depend on human time.

## 8. Order of work

1. Resolve code-review blocker F1 (F8 is done: `eval-B1` tagged, binary hash pinned), then freeze
   the pre-registration.
2. Re-run E0, E1 and E5 on the frozen snapshot, then E7 coding and the E2 annotation sample.
3. E3 and E4 on 0.30.6, then on 0.30.7, then E6.
4. E8.
5. Write Methods and Results first, following the local `science-research-writing` workflow.

## 9. Changes from methodology version 1

| Version 1 assumed | At B1 | Consequence |
|-------------------|-------|-------------|
| Per-kind adapters over a typed SDK | Kind specs plus a kind-agnostic engine (ADRs 0002, 0003, 0016) | The specification language becomes the primary artefact (RQ1, RQ4) |
| Evaluation phases E1–E4 aligned with unfinished phases | The beta is complete; import, recovery and deploy exist | All conditions, including brownfield, can run on B1 |
| RQ1 to be answered by a new annotation of all 604 operations | The specs already annotate the 223 operations the engine needs | The specs are the gold standard; E2 measures inferability |
| A new harness had to build every oracle | The SUT ships ledger, conformance, simulator, live and round-trip evidence | Two evidence tiers; the independent harness concentrates on live behaviour |
| Effort from commit timestamps | Most commits of the beta are AI-assisted | Size and onboarding events only |
| RQ4 compared per-kind adapters with generated code | Every kind is a spec; the question is how much still needs engine code | E5 measures the spec/engine split and onboarding curve; E8 is the external comparison |
