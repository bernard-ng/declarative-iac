# Paper outline (working)

**Working title.** *From procedures to resources: a specification layer for declarative management
of RPC-style platform APIs* (alternatives to be settled with `write-title` once results exist).

**Article type.** Software-engineering research paper with an artefact and an empirical evaluation.
Candidate venues: ICSE (technical or SEIP track), ESEC/FSE, ICSME, ICSA, TSE/TOSEM; MODELS if the
specification-language framing leads. Run `target-article-analysis` on 3–4 recent papers of the
chosen venue before drafting.

**Claim (to be bounded by results).** A declarative control plane can be built over an API that
exposes procedures rather than resources. The engine stays generic if the missing semantics —
identity, operation roles, write groups, identity discovery, read authority, mutability and value
classes, and structural shapes — are supplied as per-kind specifications that are checked for
completeness against the API contract and recorded responses.

## Contributions (map each to an experiment)

| # | Contribution | Evidence |
|---|--------------|----------|
| C1 | A specification language that captures the declarative semantics a procedure-oriented API lacks | E1, E2, E7 |
| C2 | A kind-agnostic reconciliation engine with explicit safety invariants and evidence-based recovery | E3, E4, E6 |
| C3 | A completeness and conformance method: field-classification ledger, spec-derived conformance, simulator/live differential, round-trip contract | E1, E3–E6 |
| C4 | An empirical case: Dokploy (604 operations), obstacles and effort | E0, E5, E7, E8 |

## Section move maps

1. **Introduction** — IaC assumes resource-oriented provider APIs (cite AIP-128, Kubernetes,
   Cloud Control). Many platforms expose procedures instead. Gap: bridging work assumes
   resource-oriented targets or hand-written connectors and does not evaluate convergence
   (models@run.time, TOSCA/OCCI; see `docs/literature-review.md`). Aim, RQs, contributions.
2. **Background and running example** — Dokploy's API (E0 numbers), one kind (application) shown
   as procedures and then as a spec.
3. **The specification language** — constructs grouped by the semantic gap each closes, with the
   presence semantics.
4. **Engine and safety model** — the pipeline (discover → project → plan → apply → verify → recover),
   invariants, and outcome-unknown handling.
5. **Completeness and conformance method** — ledger, generated scenarios, simulator, live, round trip.
6. **Evaluation method** — `docs/methodology.md` §2–§7, condensed.
7. **Results** — RQ1 (E1, E2), RQ2 (E3, E4, E6), RQ3 (E7), RQ4 (E5, E8).
8. **Discussion** — what generalises beyond Dokploy, guidance for API designers, threats.
9. **Related work** — positioned per research line (from the literature review).
10. **Conclusion**.
