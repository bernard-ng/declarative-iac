# Instructions for agents working in this repository

This is a research repository. Its outputs are evidence for a paper, so provenance matters more
than speed.

## Rules

1. **Never modify the system under study.** dokploy-iac is read through `diac.sut.Snapshot`
   (`git show <commit>:<path>`). Do not read its working tree for results, and do not import its code.
2. **Every number traces to a snapshot.** Experiments write to `results/<experiment>/<snapshot>/`
   with `diac.results.write_manifest`. Do not hand-edit result files.
3. **Pre-registration first.** Do not change hypotheses, metrics, scenarios, or operators in
   `evaluation/PREREGISTRATION.md` once it is frozen; log changes in `evaluation/DEVIATIONS.md`.
4. **Oracles are independent.** Oracle mappings in `src/diac/harness/oracle.py` are written from Dokploy
   responses, not from the SUT's specs or Rust code. The raw client is read-only.
5. **Label evidence.** Distinguish *developer evidence* (the SUT's own ledger, conformance, simulator,
   live suite, round-trip gate) from *independent evidence* (this harness), and exploratory runs from
   confirmatory ones.
6. **Live experiments use disposable instances only**, from the SUT's `compose.integration.yaml`.
   Never commit `DOKPLOY_URL` or `DOKPLOY_API_KEY` values.
7. Record decisions and surprises in `docs/research-log.md`, newest first.

## Writing the paper

Use the skills in `.agents/skills/`. Start with `science-research-writing`, which routes to the section
skills. Draft in the order Methods → Results → Introduction → Discussion → Abstract → Title
(`write-methodology`, `write-results`, `write-introduction`, `write-discussion-conclusion`,
`write-abstract`, `write-title`). For framing, use `formulate-research-gap`,
`literature-review-positioning`, `contribution-mapping` and `claim-strength`. Finish with
`scientific-style-editing` and, for a full draft, `paper-consistency-audit`. Use only supplied
results, and mark gaps instead of inventing values.
