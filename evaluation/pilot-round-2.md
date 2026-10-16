# Pilot, round 2

<!-- Written from results/live/pilot/round-2/L1/B1/ (summary.json, result.json, raw/ logs). Not a
confirmatory result. -->

One repetition of each of the 27 L1 scenarios on Dokploy 0.30.6, run on the author's Mac (Docker
Desktop, single-node Swarm) at tag `prereg-v1.1` (`57911f6`), after deviation D1. None of these
runs is counted in Section 9.

## Hypotheses

| Hypothesis | Runs satisfying | Wilson 95% | Verdict |
|---|---:|---|---|
| H1 convergence within two applies | 26/27 | [0.82, 0.99] | refuted (`unit-databases`) |
| H2 no mutation by plans or by an apply at convergence | 27/27 | [0.88, 1.00] | supported |
| H3 observations hold (runs with observations) | 8/8 | [0.68, 1.00] | supported |
| H4 nothing outside the configuration changes | 27/27 | [0.88, 1.00] | supported |
| H7a consecutive plans byte-identical | 27/27 | [0.88, 1.00] | supported |
| Lifecycle expectations | 9/9 | [0.70, 1.00] | supported |
| No secret leak | 27/27 | [0.88, 1.00] | supported |

H7b (first plans equal across repetitions) needs more than one repetition and is not assessed in a
pilot. All 19 observations held. Of the 37 steps that ran the convergence loop, 35 converged after
one apply, one needed none (`lifecycle-ignore-changes` step 2, whose only change is ignored), and
one did not converge (below). The extra apply on every converged workspace made no mutation.

Each run removed the Docker networks Dokploy had created during it (recorded per run as
`docker_cleanup`); no run found a network left by an earlier one. Runs took about 20 s each, 526 s
in total, excluding instance start-up and teardown.

## The libsql database does not converge

In `unit-databases`, every apply failed on the libsql database with "`app_name` does not read back
as written":

1. The first apply created the project, the environment and the libsql database, read it back,
   found `app_name` different from the value sent (`edge`, the key, which the specification
   sends because Dokploy's create requires `appName`), checkpointed and stopped.
2. The next plan recorded drift on `app_name` and, since the field is create-only, planned a
   replacement.
3. Each later apply removed the database, created a new one and stopped at the same mismatch.

The engine behaved safely throughout: no duplicate or orphan was left (remove before create, as
Section 6 states), and every stop named the resource and the property. But the configuration can
never converge. The cause is in the `libsql` specification at `eval-B1`: it sets `app_name` from the
key and treats it as create-only, while Dokploy stores a different value. The other database
specifications declare `app_name` nullable and let Dokploy generate it. The recorded libsql
responses cannot show this, because the capture used a run-specific name that sanitisation
replaced, and libsql is not among the kinds the system's own live tests cover (Section 7.2).

Because apply stops at the first failure, the mariadb, mongo and mysql databases of the same
scenario were never created, so those three kinds were not exercised in this round.

## Other observations

1. **Cross-document selectors.** In five scenarios whose project documents select a tag or network
   that their settings document creates, the first plan was not applyable (exit 1, DOKPLAN019), and
   one apply converged the workspace (plan exits 1 then 0): `realistic-compose`, `realistic-webapp`,
   `topology-networks`, `topology-shared-tag`, `unit-backups`.
2. **Web server reads.** As in round 1, the Traefik settings reads answered 500 ("Resource type not
   found") on this stack, and `unit-web-server`, which manages only `builds_concurrency`,
   converged.

## Consequence

Deviation D2 splits `unit-databases`: `unit-libsql` keeps the libsql database unchanged, so the
confirmatory runs measure the failure in its own cell, and `unit-databases` keeps mariadb, mongo
and mysql. Neither new cell has run yet; a third pilot round runs only these two cells.
