# E5: Where the per-kind effort goes

**Question.** In the spec-driven beta, how much of what it takes to support a kind is carried by its
spec, and how much still needs kernel or engine code? Does the engine cost of a new kind fall as the
grammar matures? (RQ4; H9)

**Design.** Git-only analysis of the beta's own history, from the commit that introduced the first
kind spec (`c1606aa`) to the snapshot: code size per crate at the snapshot, spec size per kind, and an
onboarding log recording, for each kind, the commit that introduced its spec and the kernel/engine
Rust lines added in that commit (spec-only versus spec-plus-engine).

**Preliminary result (B1, exploratory).**
- Non-generated Rust at B1: 40,836 lines in `src/` (32,163 in kernel, engine, spec, model, simulator,
  state and conformance crates) and 21,221 in `tests/`; specs: 3,272 lines for 36 kinds (median 70
  lines per kind, from 25 to 299 for `application`).
- 36 kinds arrived in 18 onboarding commits. **7 kinds were spec-only** (port, security, and the five
  databases); **29 arrived with engine changes**, 6,873 engine lines in total.
- No saturation yet: engine lines added per third of the onboarding events were 3,549, 1,093 and
  2,231, and both spec-only events fall in the first third. The settings kinds added last brought
  new API patterns (singletons split across endpoints, adopt-only kinds, per-provider create
  operations, asymmetric nullability).
- 90 commits in the window; 60 carry an AI-assistant co-author trailer, so elapsed time is not used
  as an effort measure.

**Caveats.** See `summary.json` → `caveats`. Lines measure size, not effort. Onboarding commits can
mix grammar work for several kinds with refactoring.
