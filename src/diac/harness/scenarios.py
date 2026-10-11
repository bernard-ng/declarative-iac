"""Scenario files for E3/E4: a workspace template plus the initial condition to construct.

Format (experiments/e3_convergence/scenarios/*.yaml):

  id: S-unit-registry
  family: unit | topology | lifecycle | realistic
  kinds: [registry]
  workspace: templates/registry/          # copied into a fresh temp directory
  secrets_env: { GHCR_TOKEN: canary-... }  # canary values, scanned for leaks afterwards
  conditions: [empty, engine_partial, brownfield, drifted]
  drift_operators: [owned_field, unowned_field, delete_managed, colliding_sibling, ...]
  expected:
    k_max: 2          # pre-registered bound (H1)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Scenario:
    id: str
    family: str
    kinds: list[str]
    workspace: Path
    conditions: list[str]
    drift_operators: list[str] = field(default_factory=list)
    secrets_env: dict[str, str] = field(default_factory=dict)
    k_max: int = 2

    @classmethod
    def load(cls, path: Path) -> "Scenario":
        d = yaml.safe_load(path.read_text())
        return cls(id=d["id"], family=d["family"], kinds=d["kinds"],
                   workspace=(path.parent / d["workspace"]).resolve(), conditions=d["conditions"],
                   drift_operators=d.get("drift_operators", []), secrets_env=d.get("secrets_env", {}),
                   k_max=d.get("expected", {}).get("k_max", 2))


def load_all(directory: Path) -> list[Scenario]:
    return [Scenario.load(p) for p in sorted(directory.glob("*.yaml"))]
