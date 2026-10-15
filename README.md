# Declarative management over procedure-oriented APIs: kind specifications as a semantic bridge

> work in progress

[![audit](https://github.com/bernard-ng/declarative-iac/actions/workflows/audit.yml/badge.svg)](https://github.com/bernard-ng/declarative-iac/actions/workflows/audit.yml)
[![quality](https://github.com/bernard-ng/declarative-iac/actions/workflows/quality.yml/badge.svg)](https://github.com/bernard-ng/declarative-iac/actions/workflows/quality.yml)
[![tests](https://github.com/bernard-ng/declarative-iac/actions/workflows/tests.yml/badge.svg)](https://github.com/bernard-ng/declarative-iac/actions/workflows/tests.yml)

---

## Abstract

Declarative infrastructure-as-code (IaC) tools reconcile a desired state with the observed one,
which presumes APIs that expose resources with stable identities, standard methods and typed
representations. Many self-hosted platforms expose procedures instead. Dokploy, an open-source
deployment platform, offers 604 procedures through a tRPC API whose OpenAPI export declares every
response as an empty object; it writes one object through several procedures and often does not
return the identity of what it creates. This report describes a method for building a declarative
control plane over such an API without changing it. What the API leaves implicit is written once per
resource kind, as data, in a kind specification: identity, the role of each procedure, the fields
each update procedure carries, how a new identity is learned, which reads prove absence, the
mutability and secrecy of each field, and shapes such as unions, relations and kinds with several
parents. A kind-agnostic engine derives parsing, discovery, three-way planning, journaled execution
with read-back verification, recovery and import from these specifications. A coverage ledger checks
completeness by classifying every request field of every procedure used against the API contract,
and response shapes are taken from recorded live responses. For Dokploy, 36 specifications with 625
fields use 223 of the 604 procedures, and no request field is left unclassified. [RESULT:
convergence, idempotency, recovery and round-trip outcomes.] The report also identifies twelve
classes of mismatch between procedure-oriented APIs and declarative management and gives a procedure
for applying the method to other APIs.

The reference implementation is [dokploy-iac](https://github.com/bernard-ng/dokploy-iac), cited at a
pinned commit (tag `eval-B1`, commit `5d73d4b`). This repository holds the manuscript and the
evaluation harness that produces every number in it.

## How to cite this work

```bib
to be provided after publication
```

Software metadata is in [CITATION.cff](CITATION.cff).

## Workflows

Clone the repository and sync dependencies:

```bash
git clone https://github.com/bernard-ng/declarative-iac.git
cd declarative-iac
uv sync
```

Check every claim of the paper against the committed results (no Docker, a minute or two):

```bash
uv run declarative-iac reproduce --level 0
```

Recompute the results from the pinned system, or rerun the live experiments on a Docker host:

```bash
uv run declarative-iac reproduce --level 1
uv run declarative-iac reproduce --level 2
```

[REPRODUCING.md](REPRODUCING.md) describes each level, its requirements, and how variation is
controlled. The live experiments follow the [pre-registration](evaluation/PREREGISTRATION.md).

| Command | Purpose |
|---|---|
| `declarative-iac provenance show\|verify\|build-binary` | the pinned system, its toolchain and release binary |
| `declarative-iac static run --all` | S1–S7: API census, specifications, coverage ledger, recorded responses, invariants, scenarios, kind names in engine code |
| `declarative-iac developer run` | the system's own tests at the pinned commit (developer evidence) |
| `declarative-iac live up\|down\|smoke` | a local Dokploy from `compose.yaml`; one end-to-end run |
| `declarative-iac live plan\|run\|summarise` | L1–L4: convergence, drift, faults and recovery, round trip |
| `declarative-iac report` | tables, figures and `results/SUMMARY.md`, generated from results only |
| `declarative-iac claims verify\|check-paper` | each number in the paper against its result and its location |
| `declarative-iac archive` | the results archive for deposit, with `SHA256SUMS` |

## Layout

```text
paper/                 manuscript: sections/, generated tables/ and figures/, references.bib
claims/claims.yaml     every quantitative statement of the paper and the result that produces it
config/                pinned snapshot, scenarios, observer read model, drift operators, fault plan
evaluation/            pre-registration and deviations
results/               static/, developer/, live/ results with manifests; SUMMARY.md; CLAIMS_REPORT.md
src/declarative_iac/   the harness (core/, domain/, workflow/)
docs/harness/          design brief of the harness
docs/literature-review.md
```

## Contributing

Read [AGENTS.md](AGENTS.md) first. The harness never imports or modifies the system under study,
generated files are never edited by hand, and a change to the paper's numbers starts with a
change to the results.
