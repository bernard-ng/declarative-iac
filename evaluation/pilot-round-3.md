# Pilot, round 3

<!-- Written from results/live/pilot/round-3/L1/B1/ (summary.json, result.json, raw/ logs). Not a
confirmatory result. -->

The two cells created by deviation D2, one repetition each on Dokploy 0.30.6, run on the author's
Mac at tag `prereg-v1.2` (`ba78d5d`). None of these runs is counted in Section 9.

| Cell | Mutations sent | Outcome |
|---|---|---|
| `unit-databases` | `project.create`, `mariadb.create`, `mongo.create`, `mysql.create` | converged after one apply; the apply at convergence made no mutation |
| `unit-libsql` | `project.create`, then `libsql.create`, `libsql.remove`, `libsql.create`, `libsql.remove`, `libsql.create` | did not converge within three applies; every apply stopped with "`app_name` does not read back as written" |

Both runs made no mutation during a plan, changed nothing outside their configuration, left no
duplicate and no secret outside the secret files, and left no Docker network or service behind
(H2, H4, leak check). Each took 20–24 s, including starting, bootstrapping and removing a fresh
instance.

The round reproduces the libsql behaviour reported in [pilot-round-2.md](pilot-round-2.md) and
shows that the mariadb, mongo and mysql databases, which round 2 never created, converge. No
further change to the scenarios is needed; the confirmatory runs use `prereg-v1.2`.
