# Pilot, round 4: harness check of L2, L3 and L4

<!-- Written from results/live/pilot/round-4/ (result.json and raw/ logs). Not a confirmatory
result. -->

The pre-registered pilot (§8) covers L1 only. Before the confirmatory runs, one cell each of the
drift, fault and round-trip experiments ran once on Dokploy 0.30.6, at `49d8d6c`, between
08:57 and 09:00 UTC on 2026-10-16. The confirmatory runs started at 09:06, so the two never shared
an instance. None of these runs is counted in Section 9. The question was whether the harness
code paths for L2, L3 and L4 work; they did, and no harness change was made.

| Cell | Outcome |
|---|---|
| L2 `D1-managed-field` (unit-tag) | drift planned as expected; one apply converged |
| L2 `D7-child-object-deleted` (unit-application-children) | drift planned as expected (`create … domain.main (drift)`); did not converge |
| L3 `drop_before`, first mutation | fault fired; apply exited 1; recovery and convergence (C1) |
| L3 `drop_after`, middle mutation (ordinal 6) | fault fired; apply exited 1; recovery and convergence (C1) |
| L4 seed | seed converged; two imports byte-identical (22 files); plan of the import reported no changes; rebuild on instance B did not converge |

No run made a mutation during a plan, changed an object outside its configuration, or left a
plaintext secret outside the secret files.

## Two observations of the system

**A deleted child is not recreated.** After the harness deleted the application's domain through
`domain.delete`, the plan proposed recreating it. The first apply stopped with "proposed state does
not match the durable expected checkpoint" (`InvalidExpectedCheckpoint`, `dokploy-state`
`journal.rs`). It sent no request, but it left an operation journal in the `Begun` state. Both
later applies then stopped with "state mutation requires recovery" and also sent nothing. L2 runs
no `recover`, as pre-registered (§4.1), so the cell fails H1. The failure is safe: no duplicate and
no partial write.

**Import captures derived Traefik configuration.** `import all` writes `web_server.default`
`traefik.middlewares_config` as a declared file. Dokploy generates the file's middlewares from the
seed's redirect and basic-auth children, and their names contain the application's generated
`appName`. On instance B the plan therefore *adopts* `web_server.default` with that property; the
write restarts Traefik, so it is disruptive, and every apply was refused without
`--allow-disruptive`. The other documents depend on the settings document, so instance B stayed
empty and the second import differs from the first in 19 files. Passing `--allow-disruptive` would
not restore H8: the imported names belong to instance A's `appName`, which instance B does not
reproduce. The file also carries the basic-auth bcrypt hash outside `.dokploy/secrets/`; it is a
hash, not the plaintext, so the leak check (§5) does not count it.

Both are behaviours the pre-registered hypotheses exist to detect (H1 under drift, H8), so the
confirmatory runs record them unchanged.

## Note on the manifest `dirty` flag

`harness.dirty` is `git status --porcelain`, which counts untracked files. In these runs, and in
the confirmatory runs, it is true only because of the untracked `results/` directories the runs
write. `git status --porcelain --untracked-files=no` was empty at `49d8d6c` when the confirmatory
runs started.
