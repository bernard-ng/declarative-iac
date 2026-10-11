# Instructions for agents working in this repository

This repository holds the manuscript of a technical report on dokploy-iac. It contains no code.

## Rules

1. **Describe the final design only.** No development history, and no earlier engine. Every
   decision is stated with its reason, every algorithm step by step, so a reader can apply the
   approach to another API.
2. **Describe what the code does.** The reference implementation is dokploy-iac at tag `eval-B1`
   (commit `5d73d4b`). Where its design documents and its code disagree, the paper follows the code.
3. **Do not invent values.** Mark gaps as `[RESULT: ...]` (a number still to be measured) or
   `[TODO: ...]` (text still to be written). No placeholder may survive into a submitted version.
4. **Citations** are inline Markdown links, `[Author Year](https://doi.org/...)`, with every DOI
   verified and added to `paper/references.bib`. The abstract has no citations.
5. **One section at a time.** Every section in the introduction's roadmap has a file in
   `paper/sections/`; draft them one at a time and update the status in `paper/outline.md`.

## Writing the paper

Use the skills in `.agents/skills/`. Start with `science-research-writing`, which routes to the section
skills (`write-methodology`, `write-results`, `write-introduction`, `write-discussion-conclusion`,
`write-abstract`, `write-title`). For framing, use `formulate-research-gap`,
`literature-review-positioning`, `contribution-mapping` and `claim-strength`. Finish each section with
`scientific-style-editing` and, for a full draft, `paper-consistency-audit`.
