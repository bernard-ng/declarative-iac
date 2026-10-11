"""Write experiment outputs with provenance so every number traces to a snapshot."""
from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .sut import RESEARCH_ROOT, Snapshot


def _research_commit() -> str:
    try:
        out = subprocess.run(["git", "-C", str(RESEARCH_ROOT), "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=True).stdout.strip()
        # results/ is the output of the run itself, so it does not make the code dirty
        dirty = subprocess.run(["git", "-C", str(RESEARCH_ROOT), "status", "--porcelain", "--", ".", ":!results"],
                               capture_output=True, text=True).stdout.strip()
        return out + ("+dirty" if dirty else "")
    except subprocess.CalledProcessError:
        return "uncommitted"


def output_dir(experiment: str, snap: Snapshot) -> Path:
    d = RESEARCH_ROOT / "results" / experiment / snap.id
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_manifest(directory: Path, experiment: str, snap: Snapshot, **extra) -> Path:
    manifest = {
        "experiment": experiment,
        "snapshot": snap.id,
        "sut_commit": snap.commit,
        "research_commit": _research_commit(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "command": " ".join(sys.argv),
        **extra,
    }
    p = directory / "manifest.json"
    p.write_text(json.dumps(manifest, indent=2) + "\n")
    return p
