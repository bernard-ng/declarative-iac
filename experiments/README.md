# Experiments

Each experiment answers part of one research question, writes its outputs to
`results/<experiment>/<snapshot>/` together with a `manifest.json` (SUT commit, research-repo
commit, command, time), and never reads the SUT working tree: files come from
`git show <snapshot commit>:<path>` (see `config/snapshots.yaml`).

| ID | Question | Needs | Status at B1 |
|----|----------|-------|--------------|
| [E0](e0_api_census/) | How procedure-oriented is the API, and which operations do the specs use? (RQ1, RQ3) | git only | **run** (preliminary) |
| [E1](e1_spec_expressiveness/) | What semantics do the kind specs encode, and which grammar features does each kind need? (RQ1, RQ3) | git; SUT binary for the ledger | **run** (preliminary; rebuild binary at B1) |
| [E2](e2_semantic_inference/) | How much of each spec can be inferred automatically from the OpenAPI document and live fixtures? (RQ1) | git | designed |
| [E3](e3_convergence/) | Does apply converge, stay idempotent, and stay safe from every initial condition? (RQ2) | Docker, Dokploy, SUT binary | harness ready; `empty` only |
| [E4](e4_fault_recovery/) | Is recovery after injected faults safe and convergent? (RQ2) | as E3 + recording proxy | designed |
| [E5](e5_effort_history/) | Where does the per-kind effort go: specs or engine code? (RQ4) | git only | **run** (preliminary) |
| [E6](e6_round_trip_versions/) | Does import → rebuild → import round-trip, on both supported Dokploy versions? (RQ2, RQ3) | Docker, two Dokploy versions | designed (reuses SUT gate + independent diff) |
| [E7](e7_api_friendliness/) | Which API properties forced grammar extensions or residual kind-specific code? (RQ3) | ADRs, git, E1 | designed (scorecard draft) |
| [E8](e8_generator_baseline/) | What does a general OpenAPI→Terraform generator recover from the same contract? (RQ4) | Go toolchain | designed |

Run the git-only experiments:

```bash
python experiments/e0_api_census/run.py
python experiments/e1_spec_expressiveness/run.py --binary <dokploy built at B1>
python experiments/e5_effort_history/run.py
```

Conventions: pre-registered hypotheses live in `evaluation/PREREGISTRATION.md`; any change after
the first confirmatory run is logged in `evaluation/DEVIATIONS.md`. Exploratory runs are labelled
as such in the experiment README and in the paper.
