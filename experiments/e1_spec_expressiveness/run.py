import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

"""E1 - Spec expressiveness and semantic inventory (RQ1, RQ4).

From the kind specs at the snapshot commit: per-kind semantic profile (identity strategy, read
authority, write-group shapes, mutability and value classes, hooks), per-property table, and
grammar-feature usage (which spec constructs each kind needs). Optionally runs the SUT CLI's
`dokploy coverage` to capture the field-classification ledger; the binary's provenance is recorded
and a mismatch with the snapshot is flagged instead of silently trusted.
"""
import argparse
import json
import os
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from diac.results import output_dir, write_manifest
from diac.specs import grammar_usage, load_specs, walk_fields
from diac.sut import Snapshot


def kind_profile(s: dict) -> dict:
    api = s.get("api") or {}
    read = api.get("read") or {}
    lst = read.get("list") or {}
    ci = api.get("create_identity")
    ci = next(iter(ci)) if isinstance(ci, dict) else ci
    shapes = Counter("by_variant" if "by_variant" in g else g.get("shape", "?") for g in (s.get("write") or []))
    hook = s.get("hook")
    props = list(walk_fields(s.get("fields")))
    parent = s.get("parent")
    return dict(
        kind=s["kind"], scope=s.get("scope"), spec_file=s["_file"],
        parents=len(parent) if isinstance(parent, list) else (1 if parent else 0),
        kind_class=s.get("class", "managed"), coverage=s.get("coverage", "full"),
        singleton=bool(s.get("singleton")), made_with_parent=bool(s.get("made_with_parent")),
        top_level_fields=len(s.get("fields") or {}), properties=len(props),
        write_groups=len(s.get("write") or []),
        wg_partial=shapes.get("partial", 0), wg_full=shapes.get("full", 0), wg_by_variant=shapes.get("by_variant", 0),
        create_identity=ci or ("adopt_only" if s.get("class") == "adopt_only" else None),
        read_mode=("singleton" if "singleton" in read else "embedded" if "embedded_in" in lst
                   else "scoped" if "scope" in lst else "collection" if lst else "id_only"),
        list_authority=lst.get("authority"), direct_read_agree=bool((read.get("one") or {}).get("agree")),
        hook=(hook or {}).get("name") if isinstance(hook, dict) else hook,
        ledger_readonly=len((s.get("ledger") or {}).get("readonly") or []),
        ledger_ignored=len((s.get("ledger") or {}).get("ignored") or []),
        ledger_derived=len((s.get("ledger") or {}).get("derived") or []),
    )


def sha256(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_coverage(snap: Snapshot, binary: str | None) -> tuple[pd.DataFrame | None, dict]:
    pinned = snap.meta.get("binary") or {}
    candidates = [binary] if binary else ([str(snap.path / pinned["path"])] if pinned.get("path") else []) + \
        [str(snap.path / "target/release/dokploy"), str(snap.path / "target/debug/dokploy")]
    for b in candidates:
        if b and Path(b).is_file() and os.access(b, os.X_OK):
            digest = sha256(b)
            if pinned.get("sha256") and digest != pinned["sha256"]:
                raise SystemExit(f"binary {b} has sha256 {digest}, snapshot pins {pinned['sha256']}")
            version = subprocess.run([b, "--version"], capture_output=True, text=True).stdout.strip()
            text = subprocess.run([b, "coverage"], capture_output=True, text=True, check=True).stdout
            rows = [line.split("\t") for line in text.strip().splitlines()]
            df = pd.DataFrame(rows[1:], columns=rows[0])
            for c in df.columns[2:]:
                df[c] = df[c].astype(int)
            built = datetime.fromtimestamp(Path(b).stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
            commit_time = snap.git("log", "-1", "--format=%cI", snap.commit).strip()
            prov = {"binary": b, "sha256": digest, "sha256_matches_pin": digest == pinned.get("sha256"),
                    "version": version, "binary_mtime_utc": built, "snapshot_commit_time": commit_time,
                    "binary_may_predate_snapshot": built < datetime.fromisoformat(commit_time).astimezone(timezone.utc).isoformat(timespec="seconds"),
                    "working_tree_at_snapshot": snap.head_matches}
            return df, prov
    return None, {"binary": None, "note": "no dokploy binary found; build the SUT at the snapshot commit"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot")
    ap.add_argument("--binary", help="path to a dokploy binary built at the snapshot commit")
    args = ap.parse_args()
    snap = Snapshot.load(args.snapshot)
    specs = load_specs(snap)
    out = output_dir("e1_spec_expressiveness", snap)

    kinds = pd.DataFrame([kind_profile(s) for s in specs.values()]).sort_values(["scope", "kind"])
    kinds.to_csv(out / "kinds.csv", index=False)

    props = []
    for s in specs.values():
        for path, f in walk_fields(s.get("fields")):
            props.append(dict(kind=s["kind"], path=path, depth=path.count("."), type=str(f.get("type", "")),
                              mutability=f.get("mutability", "in_place"), value_class=f.get("class", "public"),
                              nullable=bool(f.get("nullable")), read_nullable=bool(f.get("read_nullable")),
                              needs_deploy=bool(f.get("needs_deploy")), disruptive=bool(f.get("disruptive")),
                              has_fallback="fallback" in f))
    props = pd.DataFrame(props)
    props.to_csv(out / "properties.csv", index=False)

    usage = pd.DataFrame([{"kind": k, **grammar_usage(s)} for k, s in specs.items()]).fillna(0)
    usage = usage.set_index("kind").astype(int)
    usage.to_csv(out / "grammar_usage.csv")
    feature_kinds = (usage > 0).sum().sort_values(ascending=False)

    cov, prov = run_coverage(snap, args.binary)
    if cov is not None:
        cov.to_csv(out / "coverage_ledger.csv", index=False)

    summary = {
        "kinds": int(len(kinds)), "kinds_by_scope": kinds.scope.value_counts().to_dict(),
        "kinds_with_hook": int(kinds.hook.notna().sum()),
        "kinds_coverage_partial": kinds[kinds.coverage != "full"].kind.tolist(),
        "properties": int(len(props)),
        "mutability": props.mutability.value_counts().to_dict(),
        "value_class": props.value_class.value_counts().to_dict(),
        "create_identity": kinds.create_identity.fillna("none").value_counts().to_dict(),
        "read_mode": kinds.read_mode.value_counts().to_dict(),
        "write_groups_total": int(kinds.write_groups.sum()),
        "kinds_with_multiple_write_groups": int((kinds.write_groups > 1).sum()),
        "kinds_with_by_variant": int((kinds.wg_by_variant > 0).sum()),
        "multi_parent_kinds": kinds[kinds.parents > 1].kind.tolist(),
        "grammar_feature_kind_counts": feature_kinds.to_dict(),
        "coverage_ledger_totals": (cov.iloc[:, 2:].sum().to_dict() if cov is not None else None),
        "coverage_provenance": prov,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    write_manifest(out, "e1_spec_expressiveness", snap, coverage_provenance=prov)
    print(json.dumps({k: v for k, v in summary.items() if k != "grammar_feature_kind_counts"}, indent=2, default=str))


if __name__ == "__main__":
    main()
