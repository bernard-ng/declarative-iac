# Pilot, round 1

<!-- Written from results/live/pilot/L1/B1/ (result.json, raw/ logs). Not a confirmatory result. -->

One repetition of every L1 scenario on Dokploy 0.30.6, run on 2026-10-15 on the author's Mac
(Docker Desktop, single-node Swarm) at tag `prereg-v1` (`ea0f979`), as PREREGISTRATION.md §8
requires before the confirmatory runs. None of these runs is counted in Section 9.

## Outcome per scenario

13 of 28 scenarios met every check that applies to them. A failure is attributed to the
first cause found in its logs (plan diagnostics, CLI errors, proxy log).

| Scenario | Outcome | Cause | Rejected requests |
|---|---|---|---|
| `lifecycle-adopt` | pass | — | — |
| `lifecycle-destroy` | pass | — | tag.one 404 |
| `lifecycle-forget` | pass | — | — |
| `lifecycle-ignore-changes` | fail | A docker password undeclared | — |
| `lifecycle-move` | fail | A docker password undeclared | — |
| `lifecycle-protect` | pass | — | — |
| `lifecycle-replace` | fail | G replacement expected to be refused | network.one 404 |
| `lifecycle-secret-rotation` | fail | A docker password undeclared | — |
| `lifecycle-update-in-place` | pass | — | — |
| `realistic-compose` | fail | E harness stopped at plan exit 1 (cross-document selector) | — |
| `realistic-webapp` | fail | B create-required field undeclared<br>E harness stopped at plan exit 1 (cross-document selector) | — |
| `topology-networks` | fail | C network create rejected<br>E harness stopped at plan exit 1 (cross-document selector) | network.create 400 |
| `topology-shared-tag` | fail | E harness stopped at plan exit 1 (cross-document selector)<br>F harness false duplicate (no parent id) | — |
| `topology-wide` | fail | B create-required field undeclared | — |
| `unit-ai-provider` | pass | — | — |
| `unit-application` | fail | A docker password undeclared | — |
| `unit-application-children` | fail | B create-required field undeclared | — |
| `unit-backups` | fail | A docker password undeclared<br>E harness stopped at plan exit 1 (cross-document selector) | — |
| `unit-compose` | pass | — | — |
| `unit-databases` | fail | B create-required field undeclared | — |
| `unit-network` | fail | C network create rejected | network.create 400 |
| `unit-notification` | pass | — | — |
| `unit-organization` | pass | — | — |
| `unit-postgres` | pass | — | — |
| `unit-project` | pass | — | — |
| `unit-registry` | fail | D registry login on create | registry.create 400 |
| `unit-tag` | pass | — | — |
| `unit-web-server` | pass | — | settings.getTraefikPorts 500, settings.haveTraefikDashboardPortEnabled 500, settings.readTraefikEnv 500 |

## Causes and corrections

| Cause | Kind | What happened | Correction (deviation D1) |
|---|---|---|---|
| A docker password undeclared (5 scenarios) | scenario | the docker source omitted the write-only `password`, which a full write group must declare (`null` when unused) | declared `password: null` on every docker source (10 scenarios) |
| B create-required field undeclared (4 scenarios) | scenario | a field required by the create request was not declared (DOKPLAN018): port `protocol`/`publish_mode`, libsql `enable_namespaces` | declared the fields (ports: `protocol: tcp`, `publish_mode: ingress`; libsql: `image`, `enable_namespaces: false`) |
| C network create rejected (2 scenarios) | harness | a Docker network of the same name, created by Dokploy in an earlier run, still existed on the host; Dokploy answers a duplicate name with 400 | runs record the host's networks and services before starting and remove those that appeared during the run; a run refuses to start if a scenario-declared network already exists (`live clean`) |
| D registry login on create (1 scenario) | infeasible | Dokploy logs in to a registry on create and rejects (but saves) it when the login fails; a bare instance has no reachable registry | scenario `unit-registry` removed |
| E harness stopped at plan exit 1 (cross-document selector) (5 scenarios) | harness | the harness stopped applying when a plan exited 1, although PREREGISTRATION.md §4.1 step 5 applies until the plan exits 0 or k_max is reached | the convergence loop now follows §4.1 step 5 |
| F harness false duplicate (no parent id) (1 scenario) | harness | the read-only client did not record the parent of nested objects, so two projects' `production` environments looked like one duplicated object | `config/observer.yaml` records the enclosing id (`parent`) of nested collections |
| G replacement expected to be refused (1 scenario) | expectation | `lifecycle-replace` expected an unattended replacement to be refused without `--allow-disruptive`; in the system `disruptive` marks writes that restart Traefik or the server (ADR 0013), not replacements, and the apply replaced the network as documented | step 2 now expects the replacement and its observation; the third step was removed |

Two of the scenario causes (A, B) are rules the system checks only when it plans or applies
against an instance; `dokploy validate` accepts the documents. Both are now checked offline by
S6-scenarios (`domain/scenarios/lint.py`), which reports exactly the cases above for the round-1
scenarios and none for the corrected ones.

## Observations about the system

These are single observations from an exploratory run, not tests of a hypothesis.

1. **A plan that apply refuses.** For an application whose docker source omitted `password`, the
   plan was complete and applyable (exit 2), but apply created the project and its environment and
   then refused the application before sending its request ("updating this replaces
   `source.docker.password`, so its source must be declared"). Every later apply was refused until
   `recover` ("state mutation requires recovery"). The rule is checked at apply, not at plan.
2. **Cross-document selectors.** When a project document selects a tag or network that the settings
   document of the same workspace creates, the first plan is not applyable (DOKPLAN019, unmatched
   selector), yet one apply, which handles the documents in order, converged the workspace
   (`topology-shared-tag`: tag, two projects and both assignments in one apply; the next plan was
   empty).
3. **Web server reads.** On this stack, which runs no Traefik, three Traefik settings reads
   answered 500 (`settings.getTraefikPorts`, `settings.haveTraefikDashboardPortEnabled`,
   `settings.readTraefikEnv`); the `unit-web-server` scenario, which manages only
   `builds_concurrency`, still converged.

## Timing

The 28 runs took 922 s in total (median 20 s per run, longest
248 s for `unit-application`), including starting, bootstrapping and removing a fresh instance;
the CLI commands themselves take about 1 s per run.
