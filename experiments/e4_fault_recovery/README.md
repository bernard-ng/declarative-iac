# E4: Fault injection and recovery

**Question.** After a fault at any mutation of a plan, does the engine either converge on the next
apply or refuse with recovery evidence, without ever duplicating a resource or re-sending an
uncertain non-idempotent mutation? (RQ2; H6)

**Design.** For each scenario plan with n mutations, inject one fault at mutation i = 1..n through the
recording proxy (`drop_before`, `drop_after` = committed but response lost, `status_503`, `delay`),
then run `recover --auto-approve` and `apply`. Classify each run as **converged**, **refused with
evidence**, or **unsafe** (duplicate remote object, lost identity, dangling reference, repeated
mutation visible in the call log). Only *unsafe* falsifies H6.

**Relation to SUT tests.** The SUT's conformance suite already injects the same fault classes into its
simulator (`unknown_{create,update,delete}_{before,after}`); E4 repeats them against a real Dokploy
through an independent proxy, which tests whether the simulator's fault model holds.
