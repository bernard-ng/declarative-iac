# Evaluation harness: design brief

This brief frames the harness that produces and checks every number in the paper. It follows the
repository's design skills: `frame-design-problem` for the story, themes and constraints, then
`responsibility-driven-design` and `domain-driven-design` for roles and boundaries.

## Design story

The paper makes two kinds of quantitative claim about dokploy-iac at tag `eval-B1`. Structural claims
(Sections 3, 5 and 7) count things in the API contract, the kind specifications and the recorded
responses. Behavioural claims (Section 9) report how the engine behaves on real Dokploy instances:
whether it converges, stays idempotent, repairs drift, recovers from lost requests and reproduces an
instance. A reviewer must be able to recompute every claim from pinned inputs and to check, without
rerunning anything, that the published results support the numbers printed in the paper.

What is clear: the inputs (one commit of the system under study, two digest-pinned Dokploy images,
their OpenAPI documents) and the structural measures, which are deterministic. What is hard: live runs
depend on a Docker host and on asynchronous work inside Dokploy, faults must be injected without
changing the system under study, and the oracles must not inherit the system's own assumptions. The
author built both the system and the harness, so independence has to be designed in.

## Themes

1. **Provenance.** Every result names the exact inputs, tools and host that produced it.
2. **Independence.** The harness never imports or modifies the system under study; it reads it
   through `git show`, runs its CLI as a black box, and observes Dokploy through its own client.
3. **Claims as data.** Every number in the paper is a registered claim that points to the result
   that produces it, and a checker compares the two.
4. **Controlled live runs.** Disposable instances, pre-registered scenarios and faults, fixed
   repetitions, and explicit settling rules.
5. **Generated reporting.** Tables and figures are produced from results only.

## Boundary

Inside: the harness package, its configuration, scenarios, claims, results and generated tables.
Outside, as actors: the system under study (a git repository and a release binary), Dokploy instances
(Docker containers), Docker itself, the Rust toolchain container, and the reviewer, who runs commands.

## Problem frames

- **Transformation** (static experiments, reports): inputs become outputs by fixed rules; nothing may
  be lost, and reruns must be byte-identical.
- **Control** (live experiments): the harness drives Dokploy through the CLI and must know whether a
  command had its intended effect, which is what the observer and the proxy log are for.
- **Connection** (fault proxy): requests travel over a path the harness deliberately makes unreliable;
  each fault must be precisely targeted and logged.
- **Information display** (claims report): answers must be exact and traceable to a manifest.

## Constraints

- Reproducibility: `uv.lock`, `.python-version`, pinned commit, image digests, recorded binary hash,
  seeds, canonical JSON, sorted outputs.
- Safety: live commands refuse any Dokploy URL that is not a local disposable instance; secrets are
  canaries; raw logs are scanned before they are archived.
- Portability: static levels run on any machine with uv and git; live levels need Docker with Swarm.

## Core and supporting work

Core: the claims registry and verifier, the manifests, and the independent live oracles (observer,
proxy). If these are wrong, nothing else can be trusted. Supporting: census and inventory code,
report rendering, CLI plumbing.

## Bounded contexts and roles

| Context | Role | Responsibilities | Collaborators |
|---|---|---|---|
| Provenance | `Snapshot` | knows the pinned commit and tag; reads files at that commit; refuses a mismatch | git |
| | `BinaryProvider` | supplies a binary whose SHA-256 matches the snapshot, or builds one in the pinned toolchain and records its hash | Docker, `Snapshot` |
| | `RunManifest` | records inputs, tools, host, command, seed, timings and output hashes | every experiment |
| Static analysis | `ApiCensus` | counts operations, routers, methods and roles by name | `Snapshot` |
| | `SpecCatalog` | loads the kind specifications and walks fields, write groups and reads | `Snapshot` |
| | `MismatchClassifier` | applies the mechanical test of each class M1–M12 | `SpecCatalog` |
| | `LedgerReader`, `FixtureInventory` | read the binary's coverage report; count recorded responses | `BinaryProvider`, `Snapshot` |
| Live evaluation | `InstanceProvider` | starts a disposable Dokploy from `compose.yaml` (checked against the system's integration stack), bootstraps an API key, and always tears it down | Docker, `Snapshot` |
| | `CliRunner` | runs the binary in an isolated workspace and captures exit code and output | `BinaryProvider` |
| | `FaultProxy` | forwards requests, logs them, injects one planned fault | Dokploy |
| | `Observer` | reads Dokploy through an allowlist of read operations (`config/observer.yaml`, grounded in recorded responses); never mutates | Dokploy |
| | `Writer` | makes the only harness writes: scenario seeds and drift operators, each pre-registered | Dokploy |
| | `Scenario`, `Step` | pre-registered desired configurations; write a step as a workspace | `config/scenarios/` |
| | `evaluate`, `summary` | decide each hypothesis and outcome class from snapshots, proxy logs and CLI output; aggregate with Wilson intervals | `Observer`, `FaultProxy` |
| | `Run` (`experiment.py`) | executes one repetition of a cell by the procedure of PREREGISTRATION.md §4.1 | all of the above |
| Claims and reporting | `ClaimRegistry` | knows every claim, its location in the paper, its value and its source | results |
| | `ClaimVerifier` | compares claims with results and with the paper text | `ClaimRegistry` |
| | `report` (tables, figures, summary) | renders tables, figures and `results/SUMMARY.md` from results, each citing its manifest | results |
| | `reproduce`, `archive` | the three reproduction levels as fixed command lists; the deterministic results archive | every workflow |

Control style: delegated. Each workflow command coordinates one experiment; experiments ask roles to
do their work and do not inspect their internals. Results are the only channel between contexts.

## Traces

**Normal: a reviewer checks the paper.** `claims verify` loads `claims/claims.yaml`; for each claim it
reads the cited result file through its manifest, checks the manifest's output hashes, extracts the
value at the JSON pointer and applies the comparison rule; `claims check-paper` then finds the value at
the cited location in `paper/sections`. Any mismatch, missing result or broken hash fails the command.

**Consequential alternate: a lost response.** L3 plans a fault `drop_after` at mutation *i*. The
`FaultProxy` forwards the *i*-th mutating request, receives Dokploy's answer and closes the connection
without replying. The `CliRunner` records the CLI's exit code and message. The experiment runs
`recover` and then `apply`, and the `Oracle` classifies the outcome from the proxy log (was any
mutation sent twice?), the `Observer` snapshot (duplicates, lost identities, dangling references) and
the final plan.

## Decisions

- Python 3.13 with uv and `uv_build`, matching the author's other research repositories.
- Results that support the paper are committed under `results/` with their manifests; large raw logs
  are archived separately with checksums.
- Developer evidence (the system's own tests) and independent evidence (this harness) are stored and
  reported separately.
- The fault proxy uses only the standard library, so its behaviour does not depend on a third-party
  HTTP server.

## Open questions

1. Which Docker host runs the live levels (CPU, memory, operating system)? It is recorded in every
   manifest, but the time estimates in `REPRODUCING.md` depend on it; the pilot measures them.
2. Bit-for-bit reproducible Rust builds are not guaranteed across machines; reviewers verify the
   commit and the recorded hash of the binary used, and can rebuild to compare behaviour.
3. The M1–M12 classification has one coder; a second coder would strengthen Section 3.
