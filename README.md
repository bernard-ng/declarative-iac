# declarative-iac

Research workspace for a study of **declarative infrastructure management over procedure-oriented
APIs**, with [dokploy-iac](https://github.com/bernard-ng/dokploy-iac) and the Dokploy tRPC API as the
case. It holds the methodology, the evaluation harness, the experiments, their results, and the paper.

The system under study lives in its own repository and is read **only** at pinned commits
(`config/snapshots.yaml`). Nothing here imports its code.

## Layout

```text
config/snapshots.yaml        pinned SUT commits (B1 = beta 0.1.0-beta.1)
docs/
  methodology.md             research design, experiments E0-E8, hypotheses, threats (v2)
  code-review.md             architecture and code review of the SUT at B1, with findings F1-F10
  literature-review.md       related work and positioning
  research-log.md            dated decisions and surprises
evaluation/
  PREREGISTRATION.md         hypotheses H1-H9 and fixed parameters (freeze before confirmatory runs)
  DEVIATIONS.md              every change after freezing
experiments/                 one folder per experiment: README (question, design, status) + run.py
src/diac/                    shared Python code
  sut.py                     read SUT files at a snapshot via git
  specs.py                   kind-spec loader and inventories
  results.py                 output folders and provenance manifests
  harness/                   black-box harness: raw read-only client, recording/fault proxy,
                             CLI runner, scenarios, oracles, drift operators
tests/                       smoke tests (pytest)
results/<exp>/<snapshot>/    derived outputs + manifest.json (raw logs under raw/, git-ignored)
paper/                       manuscript outline and sections
.agents/skills/              research-writing skills used for the manuscript
```

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate && pip install -e .
# git-only experiments (no Docker needed)
python experiments/e0_api_census/run.py
python experiments/e1_spec_expressiveness/run.py --binary /path/to/dokploy   # built at B1
python experiments/e5_effort_history/run.py
```

Point at another checkout with `DOKPLOY_IAC_PATH=/path/to/dokploy-iac`, and at another snapshot (once one is
added to `config/snapshots.yaml`) with `--snapshot <id>` or `DIAC_SNAPSHOT=<id>`.

Live experiments (E3, E4, E6) need Docker, the SUT's `compose.integration.yaml`, and
`DOKPLOY_URL` / `DOKPLOY_API_KEY` for a **disposable** instance. Never point them at a real one.
