# E7: API characteristics that obstruct declarative management

**Question.** Which properties of the API forced extensions of the spec grammar or kind-specific
engine code, and how often does each occur? (RQ3)

**Sources.**
1. **Grammar-evolution log:** every grammar feature (E1 `grammar_usage`) linked to the commit and ADR
   that introduced it (ADRs 0018, 0019, 0020 and `feat(spec,engine)` commits) and to the API behaviour
   that motivated it.
2. **Residual kind-specific code:** engine branches that test a kind name (B1 has 13 production sites, e.g. the
   `server` local selector, `vault_provider` discovery, deployment-type mapping for
   application/compose). Each is either a candidate hook or a missing grammar feature.
3. **Scorecard** (`scorecard.yaml`): AIP-121/128-derived properties scored per router.

**Output.** A table: API property → grammar feature or hook → kinds affected → evidence (ADR,
commit, fixture) → failure observed in E3/E4/E6, if any.
