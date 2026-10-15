# Reproducing the results

Every number in the paper is a registered claim (`claims/claims.yaml`) that points at a result
file produced by this harness, and every result directory has a `manifest.json` recording its
inputs, tools, host and output hashes. Reproduction has three levels; each is one command and
is nothing more than the commands it prints (`--dry-run`).

| Level | What it checks | Needs | Time (estimate) |
|---|---|---|---|
| 0 | Committed or archived results against the paper | uv | 1–2 min |
| 1 | Recomputes every static result and the system's own test evidence | uv, git; Docker *or* Rust 1.97.1 for the developer run | 30–60 min |
| 2 | Reruns the pre-registered live experiments | Level 1 + Docker with Swarm | 1–2 days |

Times are estimates on a 4-core laptop; level 2 is dominated by starting a fresh Dokploy for each
of 566 runs, and the pilot (PREREGISTRATION.md §8) measures it.

## Setup

```bash
git clone https://github.com/bernard-ng/declarative-iac.git
cd declarative-iac
uv sync --locked
```

The harness clones the system under study itself (into `.cache/`) and reads it only through
`git show` at the pinned commit. To use an existing checkout or binary instead:

```bash
export DIAC_SUT_PATH=/path/to/dokploy-iac            # a clone containing the pinned commit
export DIAC_SUT_BINARY=/path/to/target/release/dokploy
```

## Level 0: verify

```bash
uv run declarative-iac reproduce --level 0
```

Runs `claims verify` (each claim's value against its result file, after checking the file's hash
against its manifest) and `claims check-paper` (each claimed value appears, literally, at its
location in `paper/sections`). The report is written to `results/CLAIMS_REPORT.md`. Pending
claims are those of Section 9, which need level 2.

The same works from the archive deposited on Zenodo: unpack it, `uv sync --locked`, and run the
same command; `sha256sum -c SHA256SUMS` checks the archive first.

## Level 1: recompute

```bash
uv run declarative-iac reproduce --level 1
```

1. `provenance verify` checks the pinned commit, tag `eval-B1`, the Rust toolchain file and the
   release binary (§"The release binary").
2. `static run --all` recomputes S1–S7 into `results/static/*/B1/`. Outputs other than
   `manifest.json` must be byte-identical to the committed ones (`git diff` shows nothing); CI
   checks this on every push for S1, S2, S4, S5 and S7.
3. `developer run --no-live` runs the system's own tests and spec checks at the pinned commit and
   records them as *developer evidence*, apart from the independent results.
4. `report` regenerates `paper/tables/`, `paper/figures/` and `results/SUMMARY.md`.
5. `claims verify` and `claims check-paper` as in level 0.

## Level 2: live experiments

Requirements: Docker Engine (or Docker Desktop) with Compose v2, port 33000 free on `127.0.0.1`. The
harness makes the host a single-node Swarm manager if it is not one already (`docker swarm init`),
because Dokploy deploys through Swarm, and creates the `dokploy-network` overlay. Allow about 4
CPUs, 8 GB RAM and 20 GB disk for images and volumes (estimates). Every instance is local; the
harness refuses any non-local Dokploy URL.

```bash
uv run declarative-iac live plan                     # the 566 runs, without starting anything
uv run declarative-iac live up --version 0.30.6      # one instance from compose.yaml, left running
uv run declarative-iac live smoke                    # one L1 run of unit-tag on a fresh instance
uv run declarative-iac live down                     # remove the stack and its volumes
uv run declarative-iac live clean                    # list networks left on the host by earlier runs
uv run declarative-iac live run L1 --pilot --repetitions 1 --version 0.30.6   # pilot (§8)
uv run declarative-iac reproduce --level 2
```

Runs follow `evaluation/PREREGISTRATION.md`, frozen by the tag `prereg-v1`; any change after that
tag is listed in `evaluation/DEVIATIONS.md`. `live run` is resumable: a run whose
`manifest.json` exists is skipped. Each run writes `results/live/<exp>/B1/<version>/<cell>/r<n>/`:

| File | Content | Committed |
|---|---|---|
| `result.json` | the run's measures | yes |
| `raw-index.json` | sha256 of every raw file | yes |
| `manifest.json` | inputs (binary, frozen inputs, instance), host, output hashes | yes |
| `raw/` | CLI output per command, proxy log, observer snapshots, harness writes | archive only |
| `workspace/`, `home/`, `import-*/` | the system's workspace and state; hold canary secrets | never |

`live summarise <exp>` writes the hypothesis table (`summary.json`) with Wilson 95% intervals.

## The release binary

The paper's results come from the release build of commit
`5d73d4b932251c9540c0a8dd6358edd5bc076d16` (dokploy-iac `0.1.0-beta.1`). Rust release builds are
not bit-for-bit reproducible across machines, so the expected sha256 is recorded per platform
in `config/snapshot.yaml`. A binary built elsewhere (`provenance build-binary`, in the pinned
`rust:1.97.1` container on Linux) is accepted as `rebuilt`, and its own hash is recorded in every
manifest that used it. Results are compared by value, never by binary hash.

## Sources of variation and how each is controlled

| Source | Control |
|---|---|
| Binary bytes differ across platforms | per-platform hash; `origin: pinned` or `rebuilt` in every manifest |
| Dokploy finishes some work asynchronously | settling rule: two equal observer snapshots 2 s apart, at most 60 s |
| Dokploy generates names and ids | oracles compare by name, never by id; ids are mapped per run |
| Secrets differ per run (canaries) | by design; plans are compared after removing `lineage`, `stateSerial`, `configDigest` |
| Timing of a fault | faults are placed by mutation ordinal fixed from a fault-free reference run |
| Host load and network | recorded in the manifest; durations are descriptive only, never tested |
| Figure rasterisation | PNGs are byte-identical on one platform and Matplotlib version; tables everywhere |
| Manifest timestamps and host fields | excluded from comparisons (`git diff ':(exclude)…/manifest.json'`) |

## Archive

```bash
uv run declarative-iac archive
```

Writes `dist/declarative-iac-results-B1.tar.gz` and its `.sha256`: the harness source, lock
file, manuscript, results with raw logs, claims, configuration, pre-registration and a
`SHA256SUMS` file. Entries are sorted, owned by 0:0 and dated `SOURCE_DATE_EPOCH` (default 0), so
the same tree always produces the same archive. Workspaces and private HOME directories are never
included.
