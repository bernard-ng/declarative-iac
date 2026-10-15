# Deviations from the pre-registration

Every change made after the tag `prereg-v1` to `evaluation/PREREGISTRATION.md` or to a frozen
input (`config/scenarios/`, `config/observer.yaml`, `config/drift.yaml`, `config/faults.yaml`)
is recorded here before the runs it affects, with a new tag.

| # | Date | Tag | What changed | Why | Effect on results |
|---|---|---|---|---|---|
| D1 | 2026-10-15 | `prereg-v1.1` | Scenarios, observer read model and harness procedure, after pilot round 1 (details below) | The pilot found scenarios that break plan-time rules or cannot run on a bare instance, one wrong expectation, and three places where the harness differed from §4.1 or did not isolate runs ([pilot-round-1.md](pilot-round-1.md)) | L1 has 27 cells (270 runs) instead of 28 (280); 566 runs in total instead of 576. 26 kinds are exercised instead of 27 (`registry` removed); the read-only client observes 15 of them. All 12 mismatch classes remain exercised. No confirmatory run had taken place. |

### D1 in detail

Frozen inputs changed (`git diff prereg-v1 -- config/` shows every line):

1. `config/scenarios/*.yaml`: every docker source declares `password: null` (10 scenarios); every
   port declares `protocol` and `publish_mode`; the libsql database declares `image` and
   `enable_namespaces`. Cause: rules the system checks only against an instance (DOKPLAN018, and
   apply's refusal to write a full write group without its write-only member). No resource, value
   or expectation was otherwise changed.
2. `config/scenarios/unit.yaml`: `unit-registry` removed. Cause: Dokploy logs in to a registry on
   create and rejects it when the login fails; a disposable instance has no reachable registry.
3. `config/scenarios/lifecycle.yaml`: `lifecycle-replace` expected an unattended replacement to be
   refused without `--allow-disruptive`. In the system, `disruptive` marks writes that restart
   Traefik or the server (ADR 0013), not replacements, so the expectation was wrong. Step 2 now
   expects `replace network.backend` and observes the new value; step 3 was removed.
4. `config/observer.yaml`: nested collections record the id of their enclosing object (`parent`),
   so that two projects' `production` environments are not taken for one duplicated object.

Harness corrections (code, not frozen inputs, recorded because they change measured values):

5. The convergence loop applied only while the plan exited 2; §4.1 step 5 applies until the plan
   exits 0 or `k_max` applies have run. The loop now follows §4.1.
6. A0 (the apply on the converged workspace, H2) was also run on workspaces that had not
   converged; §4.1 runs it on the converged workspace only. It now does.
7. Dokploy creates networks on the host's Docker, which removing the Compose stack does not remove,
   so a network from one run made the next run's create of the same name fail. Each run now
   records the host's networks and Swarm services before it starts and removes, after teardown,
   only those that appeared during the run (listed in its manifest as `docker_cleanup`); a run
   refuses to start if a network named by a scenario already exists (`declarative-iac live clean`).
8. The proxy log keeps the first 2,000 bytes of every error response, with the run's secret values
   removed, so that a rejection can be diagnosed from the log.
9. S6-scenarios checks the two plan-time rules of item 1 offline (`domain/scenarios/lint.py`).

Round 1 is kept under `results/live/pilot/` and reported in [pilot-round-1.md](pilot-round-1.md).
A second pilot round (`--round 2`, under `results/live/pilot/round-2/`) runs under `prereg-v1.1`
before any confirmatory run.

## Harness checks before the tag

These runs checked that the harness works end to end. They are not part of the pilot or of any
reported result, and they changed no frozen input.

| Date | Run | Outcome |
|---|---|---|
| 2026-10-15 | `live smoke`: one L1 run of `unit-tag` on Dokploy 0.30.6 (`results/live/pilot/smoke/`) | completed; two harness defects found by the first attempt were fixed in the harness before it (Docker configuration redirect, fingerprint key format) |

