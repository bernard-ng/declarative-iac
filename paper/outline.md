# Technical report outline

**Title.** *Declarative management over procedure-oriented APIs: kind specifications as a semantic bridge*

**Type.** Technical report / software-engineering research paper. A reader should be able to apply
the approach to another API: every decision is stated with its reason, every algorithm is given step
by step, and the reference implementation is pinned (dokploy-iac, tag `eval-B1`, commit `5d73d4b`).

**Sections.**

| # | Section | File | Status |
|---|---------|------|--------|
| 0 | Abstract | `sections/00-abstract.md` | agreed |
| 1 | Introduction | `sections/01-introduction.md` | agreed |
| 2 | Related work | `sections/02-related-work.md` | agreed |
| 3 | What a procedure-oriented API leaves out | `sections/03-what-the-api-leaves-out.md` | agreed |
| 4 | Design principles | `sections/04-design-principles.md` | agreed |
| 5 | The kind specification language | `sections/05-kind-specification-language.md` | agreed |
| 6 | Engine algorithms | `sections/06-engine-algorithms.md` | agreed |
| 7 | Verification method | `sections/07-verification-method.md` | agreed |
| 8 | Applying the approach to another API | `sections/08-applying-the-approach.md` | draft |
| 9 | Evaluation | `sections/09-evaluation.md` | draft (live values pending) |
| 10 | Discussion and limitations | `sections/10-discussion-and-limitations.md` | draft |
| 11 | Conclusion | `sections/11-conclusion.md` | todo |

The sections follow the roadmap at the end of the introduction. Contributions 1–5 map to Sections 3,
5, 6, 7 and 8–9.

Placeholders in drafts are written `[RESULT: ...]` (a number still to be measured) or `[TODO: ...]`
(text still to be written). No placeholder may survive into a submitted version.
