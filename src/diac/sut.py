"""Read the system under study at a pinned snapshot commit (read-only, via git)."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import yaml

RESEARCH_ROOT = Path(__file__).resolve().parents[2]


def _config() -> dict:
    return yaml.safe_load((RESEARCH_ROOT / "config" / "snapshots.yaml").read_text())


@dataclass(frozen=True)
class Snapshot:
    id: str
    commit: str
    path: Path
    meta: dict

    @classmethod
    def load(cls, snapshot_id: str | None = None) -> "Snapshot":
        cfg = _config()
        sid = snapshot_id or os.environ.get("DIAC_SNAPSHOT") or cfg["default"]
        meta = cfg["snapshots"][sid]
        path = Path(os.environ.get("DOKPLOY_IAC_PATH") or (RESEARCH_ROOT / cfg["sut"]["path"])).resolve()
        if not (path / ".git").exists():
            raise FileNotFoundError(f"SUT repository not found at {path}; set DOKPLOY_IAC_PATH")
        return cls(sid, meta["commit"], path, meta)

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.path), *args], check=True,
                              capture_output=True, text=True).stdout

    def files(self, prefix: str = "") -> list[str]:
        out = self.git("ls-tree", "-r", "--name-only", self.commit, "--", prefix) if prefix else \
            self.git("ls-tree", "-r", "--name-only", self.commit)
        return [line for line in out.splitlines() if line]

    def read(self, rel: str) -> str:
        return self.git("show", f"{self.commit}:{rel}")

    def read_yaml(self, rel: str):
        return yaml.safe_load(self.read(rel))

    @cached_property
    def head_matches(self) -> bool:
        """True when the SUT working tree is at this snapshot (needed only for black-box CLI runs)."""
        return self.git("rev-parse", "HEAD").strip() == self.commit
