# Scenarios

Pre-registered inputs of the live experiments (`evaluation/PREREGISTRATION.md`). Each file is one
family; each scenario is an ordered list of **steps**, and each step is a complete desired
configuration: the body of the settings document, the body of each project document keyed by
slug, the content files it references, and the names of the secrets it reads from the
environment. The harness writes a step into a fresh workspace (`dokploy.workspace.yaml` plus
`.dokploy/…`), gives every secret a fresh canary value, and runs the system's CLI against it.

| Key | Meaning |
|---|---|
| `covers` | The kinds the scenario declares; used for the coverage table, never by an oracle |
| `steps[].settings` | Body of the settings document (`version: 2` and `settings:` are added) |
| `steps[].projects` | Slug → body of a project document (`slug:` is added) |
| `steps[].files` | Workspace-relative path → text, for `{ file: … }` sources |
| `steps[].secrets` | Environment variable names read by `{ env: … }` sources |
| `steps[].apply_flags` | Extra flags for `apply` at this step (`--allow-disruptive`) |
| `steps[].expect` | What the first plan of the step must contain (lifecycle family only) |

An expectation lists changes as `kind address`, where `address` is a suffix of the planned
address; the plan must contain exactly these changes, in any order. `refused: true` means the
first plan must be non-applyable and apply must exit 1 without a mutation.

Every document here is checked offline with `dokploy validate` by the static experiment
S6-scenarios, so a scenario that the system would reject on syntax never reaches a live run.
Changing any file in this directory after the `prereg-v1` tag is a deviation and is recorded in
`evaluation/DEVIATIONS.md`.
