# Research log

Dated notes in the style of a lab notebook: decisions, surprises, and dead ends. Newest first.

## 2026-10-11 (evening) — Snapshot B1 pinned

- SUT tagged `eval-B1` → `5d73d4b`; release binary built on a clean tree; SHA-256
  `55ec8a81e17841497bf50e465b6c3d31965849c594c9969d2b483280c235497c` recorded in
  `config/snapshots.yaml`. E1 now refuses a binary whose hash differs from the pin.
- E0, E1 and E5 re-run with the pinned binary. The coverage ledger is identical to the one from
  the earlier debug binary for all 36 kinds; no other number changed.
- `validate` still defaults to `dokploy.yaml` on the release binary (code-review F10).
- Remaining blocker before freezing: F1 (live-suite status in CI).

## 2026-10-11 — Beta review and restructuring

- Reviewed dokploy-iac at B1 (`5d73d4b`); see `docs/code-review.md`. The engine was replaced by a
  spec-driven design after the first methodology was written, so the methodology was rewritten
  (`docs/methodology.md`, version 2).
- Exploratory runs at B1: E0 (API census), E1 (spec inventory), E5 (history). Numbers are quoted in
  the experiment READMEs and will be recomputed after freezing B1.
- Scope decision: the study evaluates the beta only. The first, per-kind engine is no longer a
  baseline; E5 now measures the spec/engine split and onboarding curve inside the beta's history.
- Surprise: only 7 of 36 kinds were spec-only when introduced (E5), against the ADR 0002 target.
  The grammar grew with the API patterns it met, which is now framed as grammar saturation (H9, E7).
- Surprise: the only local `dokploy` binary predates B1 by 30 minutes; E1 records this in its
  manifest. Build a release binary at B1 before confirmatory runs.
- Disclosure noted: 60 of the 90 commits of the spec-driven history are AI-assisted; elapsed time is
  excluded as an effort measure.
