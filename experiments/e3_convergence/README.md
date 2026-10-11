# E3: Convergence, idempotency, and safety matrix

**Question.** Starting from each initial condition, does `apply` reach a state whose next plan is
empty, and is a further apply free of mutations? (RQ2; H1–H5, H7)

**Design.** scenario (S-unit per kind, S-topology, S-lifecycle, S-realistic) × condition
(`empty`, `engine_partial`, `brownfield` via `import`, `drifted:<operator>`) × 5 repetitions,
against a digest-pinned Dokploy (0.30.6 and 0.30.7).

**Oracles (independent of the SUT).**
- O-plan: `plan --detailed-exitcode` (the SUT's own view; necessary, not sufficient)
- O-raw: `diac.harness.oracle`, handwritten from Dokploy responses, read-only client
- O-traffic: `diac.harness.proxy.CallRecorder` counts mutations on the extra apply (H2)
- O-unmanaged: whole-instance snapshot before/after, minus managed ids (H4)
- determinism: three consecutive plans must be byte-identical (H7)
- canary scan of workspace and all output (invariant 18)

**Status.** Runner, proxy, CLI wrapper, and one scenario (`S-unit-tag`) exist; only `empty` is
implemented. Next: condition constructors, operator implementations in `operators.py`, scenarios
for each kind family, then the confirmatory run after pre-registration is frozen.
