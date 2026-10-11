import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

"""E5 - Where the per-kind effort goes in the spec-driven beta (RQ4).

From git only, within the history of the spec-driven engine (from the commit that introduced the
first kind spec up to the snapshot):
  1. code size per crate at the snapshot (non-generated Rust, src/ vs tests/) and spec size per kind;
  2. for every kind, the commit that introduced its spec and whether that commit also had to change
     kernel/engine Rust (a grammar or engine extension) or was spec-only;
  3. the cumulative onboarding curve (does the engine-change cost per new kind fall over time?);
  4. commit activity and co-author trailers, disclosed because assisted development makes elapsed
     time a poor proxy for human effort.
"""
import argparse
import json
import re
from collections import Counter

import pandas as pd

from diac.results import output_dir, write_manifest
from diac.specs import load_specs, walk_fields
from diac.sut import Snapshot

GENERATED = re.compile(r"(/generated/|imperative_generated\.rs$)")
ENGINE_PATHS = ("crates/dokploy-engine/src", "crates/dokploy-spec/src", "crates/dokploy-core/src",
                "crates/dokploy-model/src", "crates/dokploy-sim/src", "crates/dokploy-state/src",
                "crates/dokploy-conformance/src")


def loc_by_crate(snap: Snapshot) -> pd.DataFrame:
    rows = []
    for f in snap.files():
        if not f.endswith(".rs") or GENERATED.search(f):
            continue
        parts = f.split("/")
        crate = "/".join(parts[:2]) if parts[0] == "crates" else parts[0]
        rows.append(dict(crate=crate, area="tests" if "/tests/" in f else "src", lines=snap.read(f).count("\n")))
    df = pd.DataFrame(rows)
    return df.pivot_table(index="crate", columns="area", values="lines", aggfunc="sum", fill_value=0).reset_index()


def numstat(snap: Snapshot, commit: str) -> list[tuple[int, int, str]]:
    out = []
    for line in snap.git("show", "--numstat", "--format=", commit).splitlines():
        a, d, path = line.split("\t", 2)
        if a != "-":
            out.append((int(a), int(d), path))
    return out


def first_spec_commit(snap: Snapshot) -> str:
    log = snap.git("log", snap.commit, "--diff-filter=A", "--format=%H", "--reverse", "--", "specs/")
    return log.split()[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot")
    args = ap.parse_args()
    snap = Snapshot.load(args.snapshot)
    out = output_dir("e5_effort_history", snap)
    start = first_spec_commit(snap)
    window = f"{start}^..{snap.commit}"

    loc = loc_by_crate(snap)
    loc.to_csv(out / "loc_by_crate.csv", index=False)

    specs = load_specs(snap)
    spec_size = pd.DataFrame([dict(kind=k, spec_file=s["_file"], spec_lines=snap.read(s["_file"]).count("\n"),
                                   properties=len(list(walk_fields(s.get("fields")))))
                              for k, s in specs.items()]).sort_values("spec_lines", ascending=False)
    spec_size.to_csv(out / "spec_size_by_kind.csv", index=False)

    added = snap.git("log", window, "--diff-filter=A", "--format=@@%H|%ad|%s", "--date=short", "--name-only", "--", "specs/")
    onboard, cur = [], None
    for line in added.splitlines():
        if line.startswith("@@"):
            h, d, s = line[2:].split("|", 2)
            cur = dict(full=h, commit=h[:7], date=d, subject=s)
        elif line.endswith(".yaml") and cur and not line.endswith(("versions.yaml", "types.yaml")):
            onboard.append({**cur, "spec_file": line})
    per_commit = Counter(o["full"] for o in onboard)
    rows = []
    for o in onboard:
        ns = numstat(snap, o["full"])
        engine = sum(a for a, _, p in ns if p.startswith(ENGINE_PATHS) and p.endswith(".rs") and "/tests/" not in p)
        rows.append(dict(kind=o["spec_file"].split("/")[-1][:-5], spec_file=o["spec_file"], commit=o["commit"],
                         date=o["date"], subject=o["subject"], kinds_in_commit=per_commit[o["full"]],
                         spec_lines_added=sum(a for a, _, p in ns if p.startswith("specs/")),
                         engine_src_lines_added=engine,
                         test_lines_added=sum(a for a, _, p in ns if p.endswith(".rs") and "/tests/" in p),
                         fixture_files_touched=sum(1 for _, _, p in ns if p.startswith("fixtures/")),
                         onboarding="spec_only" if engine == 0 else "spec_plus_engine"))
    onboarding = pd.DataFrame(rows)
    order = snap.git("log", window, "--format=%H", "--reverse").split()
    onboarding["order"] = onboarding.commit.map({h[:7]: i for i, h in enumerate(order)})
    onboarding = onboarding.sort_values(["order", "kind"]).drop(columns="order")
    onboarding.to_csv(out / "kind_onboarding.csv", index=False)
    events = onboarding.drop_duplicates("commit")
    thirds = [events.iloc[i * len(events) // 3:(i + 1) * len(events) // 3] for i in range(3)]

    log = snap.git("log", window, "--format=%H|%ad|%s%n%b@@END", "--date=short")
    commits, trailers, per_day = 0, Counter(), Counter()
    for block in log.split("@@END"):
        block = block.strip()
        if not block:
            continue
        commits += 1
        per_day[block.splitlines()[0].split("|", 2)[1]] += 1
        for m in re.finditer(r"^Co-authored-by:\s*([^<\n]+)", block, re.M | re.I):
            trailers[m.group(1).strip()] += 1

    totals = loc[[c for c in ("src", "tests") if c in loc.columns]].sum().to_dict()
    engine_src = int(loc[loc.crate.isin([p.rsplit("/", 1)[0] for p in ENGINE_PATHS])]["src"].sum())
    summary = {
        "window": {"from_first_spec_commit": start, "to": snap.commit},
        "rust_lines_non_generated": totals,
        "kernel_engine_src_lines": engine_src,
        "spec_yaml_lines": int(spec_size.spec_lines.sum()),
        "spec_lines_per_kind": {"median": float(spec_size.spec_lines.median()), "max": int(spec_size.spec_lines.max()),
                                "min": int(spec_size.spec_lines.min())},
        "kinds_onboarded": int(len(onboarding)),
        "onboarding_events": int(len(events)),
        "onboarding_mode_counts": onboarding.onboarding.value_counts().to_dict(),
        "spec_only_kinds": onboarding[onboarding.onboarding == "spec_only"].kind.tolist(),
        "engine_lines_added_in_onboarding_events": int(events.engine_src_lines_added.sum()),
        "engine_lines_by_onboarding_third": [int(t.engine_src_lines_added.sum()) for t in thirds],
        "spec_only_events_by_third": [int((t.onboarding == "spec_only").sum()) for t in thirds],
        "commits_in_window": commits,
        "commits_per_day": dict(sorted(per_day.items())),
        "co_author_trailers": dict(trailers),
        "caveats": [
            "src/ lines include inline #[cfg(test)] modules; tests/ counts only integration-test files",
            "an onboarding commit that adds grammar for several kinds is attributed to every kind it introduces",
            "engine lines added in an onboarding commit may include refactoring unrelated to the new kind",
        ],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    write_manifest(out, "e5_effort_history", snap, window_start=start)
    print(json.dumps({k: v for k, v in summary.items() if k != "commits_per_day"}, indent=2))


if __name__ == "__main__":
    main()
