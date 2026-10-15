# 9 Evaluation

The evaluation asks whether the engine, driven only by the kind specifications, manages real Dokploy
instances as Sections 4–6 state. It addresses four questions, one per property named in contribution 5:

- **Q1 Convergence and idempotency.** Does an apply bring Dokploy to the declared state, and does a
  converged configuration stay converged without further mutations?
- **Q2 Drift.** When Dokploy is changed outside the engine, does the next plan contain exactly the
  changes the configuration owns?
- **Q3 Recovery.** When an apply is interrupted by a lost request or response, can it be resumed
  without an unsafe outcome?
- **Q4 Round trip.** Is an imported instance a fixed point, and does rebuilding from the import
  reproduce it?

Section 7 described the evidence that the system's own verification produces. That evidence is
written and run by the system's author against a simulator and a fixed set of live tests, and it
covers the four questions only partly (Section 7.4). This section therefore reports a second,
independent evaluation, run by a separate harness against disposable Dokploy instances. The
experiments, hypotheses and decision rules were fixed in a pre-registration before any live run.
Section 9.1 describes the setup, Section 9.2 the scenarios, and Section 9.3 the results for each
question. At the time of writing, the static part of the evaluation is complete and the live
part has not yet been run; the live values are marked [RESULT].

## 9.1 Setup

**System and instances.** The system under test is the release build of dokploy-iac at `eval-B1`. Each
run starts a fresh Dokploy of one supported version (0.30.6 or 0.30.7) from its digest-pinned image,
with a Compose stack that mirrors the system's own integration stack, and tears it down afterwards. Every instance is bound to
`127.0.0.1`.

**Independence.** The harness does not import or modify the system. It runs the binary as a black box,
in a private workspace and environment, and reads the system's repository only at the pinned commit.
Its oracles do not use the kind specifications:

- expected plans are written from the design of Sections 4–6;
- Dokploy is read through a separate read-only client, whose field names are Dokploy's response names
  taken from the recorded responses. The client may call only an allowlist of read operations, so
  observing cannot change the instance;
- every request between the system and Dokploy passes through a recording proxy, which counts
  mutations and, in Q3, injects faults.

**Pre-registration.** The pre-registration fixes the scenarios, the drift operators, the fault plan,
eight hypotheses, the number of repetitions, the settling rule and the exclusion rules. Any later
change is recorded as a deviation. Table 14 lists the experiments.

**Table 14.** Live experiments. A cell is one combination of factors; each repetition runs on a fresh
instance.

| Experiment | Question | Factors | Cells per version | Repetitions | Runs |
|---|---|---|---:|---:|---:|
| L1 | Q1 | scenario | 27 | 5 | 270 |
| L2 | Q2 | drift operator | 7 | 5 | 70 |
| L3 | Q3 | scenario × fault kind × position | 36 | 3 | 216 |
| L4 | Q4 | seed workspace | 1 | 5 | 10 |

L3 uses fewer repetitions because the fault is placed deterministically, by the position of the
mutation it affects; repetitions vary only timing.

**Hypotheses.** Each hypothesis is a property that should hold in every run. It is reported as
supported if no run violates it, with the proportion of satisfying runs and a Wilson 95% interval per
version and for both versions together.

| | Hypothesis | Measure |
|---|---|---|
| H1 | Every step converges within two applies. | number of applies until the plan is empty, at most 3 attempted |
| H2 | No plan mutates Dokploy, and an apply on a converged workspace makes no mutation. | mutations in the proxy log |
| H3 | After convergence, Dokploy holds the declared values. | the scenario's observations, in Dokploy's names |
| H4 | Nothing outside the configuration changes. | objects that existed before the run, or that the harness added, compared before and after |
| H5 | A plan after drift contains exactly the expected changes. | planned changes against the operator's expectation |
| H6 | No interrupted apply ends in an unsafe outcome. | outcome class (Table 16) |
| H7 | Plans depend only on configuration and state. | two consecutive plans are byte-identical; first plans agree across repetitions |
| H8 | An import is a fixed point, and a rebuild reproduces it. | empty plan on the import; byte-identical imports |

**Settling.** Dokploy completes some work asynchronously. After every apply and every harness write, the
read-only client reads Dokploy every 2 s until two consecutive reads agree, for at most 60 s. A run that
does not settle is reported and excluded from H3 only.

**Pilot.** As pre-registered, one repetition of every L1 scenario on Dokploy 0.30.6 preceded the
confirmatory runs. It led to one recorded deviation: scenario corrections where a scenario broke a
rule the system checks only against an instance, the removal of the registry scenario, and
corrections to the harness where its procedure or isolation differed from the pre-registration. The
pilot is reported in an appendix and none of its runs is counted below.

## 9.2 Scenarios

The scenarios are complete desired configurations, written as data in four families: 13 *unit*
scenarios that declare one kind with only the parents it needs; 3 *topology* scenarios with references
across documents, sets of selectors and several parents; 9 *lifecycle* scenarios that change a
converged configuration, each with the plan it must produce; and 2 *realistic* workspaces, a web
application with its database, cache, domain and scheduled job, and a Compose stack with shared
networks. Together they have 38 steps and 44 documents.

Two checks were made before any live run. First, every document was validated offline by the pinned
binary, and all 44 passed; two deliberately invalid documents, one with an unknown field and one with
a literal secret, were rejected with the expected diagnostics, so the check is not vacuous. Second,
every name the read-only client uses was found in a recorded response of Dokploy 0.30.6.

**Table 15.** Mismatch classes exercised by the scenarios: kinds affected (Table 3) and kinds that
appear in at least one scenario.

| Class | M1 | M2 | M3 | M4 | M5 | M6 | M7 | M8 | M9 | M10 | M11 | M12 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Kinds affected | 8 | 1 | 2 | 18 | 6 | 14 | 4 | 2 | 15 | 2 | 2 | 26 |
| Kinds exercised | 3 | 1 | 2 | 18 | 6 | 10 | 3 | 2 | 10 | 2 | 2 | 18 |

The scenarios exercise 26 of the 36 kinds and every mismatch class (Table 15). The ten kinds left
out are the four git providers, `server`, `vault_provider`, `dns_provider`, `ssh_key`, `certificate`
and `registry`. They need external accounts, a second host, key material or, for `registry`, a
reachable registry, because Dokploy logs in to a registry when it is created; a disposable instance
provides none of these. The read-only client observes 15 of the 26 exercised kinds. Kinds for which no
response was recorded, such as `notification`, are applied but not observed, so H3 does not cover
them.

L2 uses seven drift operators: a changed managed field, a deleted managed object, an added object that
no configuration declares, a changed field that the configuration does not own, a changed field
listed in `ignore_changes`, a changed project field, and a deleted child object. L3 interrupts the
first apply of three scenarios (`unit-application-children`, `topology-networks` and
`realistic-webapp`) at the first, middle or last of its mutations, with one of four faults: the
connection is dropped before the request reaches Dokploy, the request is applied but its response is
lost, or the proxy answers with a server error or an unavailable status. The operator procedure after
a fault is fixed: run `recover` for every document, then apply until the plan is empty. L4 seeds one
instance with three scenarios that together declare 15 kinds, compared with the five kinds of the
system's own round-trip gate (Section 7.3).

## 9.3 Results

### Convergence and idempotency (Q1)

[RESULT: H1, H2, H3, H4 and H7 for L1 on both versions: runs satisfying each hypothesis, Wilson 95%
intervals, the distribution of applies to convergence, and every violating run.]

[RESULT: lifecycle expectations: for each of the nine lifecycle scenarios, whether the first plan of
each step contained exactly the expected changes, and the outcome of the refused step (deletion of a
protected resource).]

### Drift (Q2)

[RESULT: H5 per drift operator and version, with the planned changes of any violating run; H4 for the
unmanaged object added by the third operator.]

### Interrupted applies (Q3)

Each faulted run is assigned the first class of Table 16 that it meets. C1 and C2 are safe; the
others are not.

**Table 16.** Outcome classes of an interrupted apply, in order of precedence.

| Class | Meaning |
|---|---|
| U5 leak | a secret value appears outside the secret files |
| U1 duplicate | two Dokploy objects exist for one declared resource |
| U2 orphan | an object the system created is neither tracked nor reported |
| U3 collateral | an object outside the configuration changed |
| U4 wrong value | the system reports convergence while an observation fails |
| U6 crash | an undocumented exit code, a panic, or a failure without a diagnostic |
| C2 blocked | the system stops with a diagnostic that names the affected resource |
| C1 converged | after recovery the workspace converges, and H3 and H4 hold |

[RESULT: outcome counts per fault kind, position and version; H6; the mutation counts of the
fault-free reference applies that fixed the positions.]

### Round trip (Q4)

[RESULT: H8 on both versions: whether the plan of each first import was empty, whether two imports of
one instance and the import of the rebuilt instance were byte-identical, and the files that differed
in any violating run.]

### Summary

[RESULT: one table with the verdict of H1–H8 and the leak check, generated from the results.]

The static checks give a lower bound on what the live part can show. The scenario set reaches every
mismatch class, but not every kind, and the read-only client grounds its observations in recorded
responses for 15 kinds. A supported hypothesis therefore holds for the exercised kinds and the
observed fields, not for all 36 kinds. Section 10 discusses these limits.
