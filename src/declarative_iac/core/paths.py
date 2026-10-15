"""Locations inside the research repository."""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path


@cache
def repository_root() -> Path:
    """The research repository root: `DIAC_ROOT`, or the nearest parent holding `pyproject.toml`
    with this project's name."""

    override = os.environ.get("DIAC_ROOT")
    if override:
        return Path(override).resolve()
    here = Path(__file__).resolve()
    for candidate in [Path.cwd(), *Path.cwd().parents, *here.parents]:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and 'name = "declarative-iac"' in pyproject.read_text():
            return candidate
    raise RuntimeError("cannot find the declarative-iac repository root; set DIAC_ROOT")


def config_dir() -> Path:
    return repository_root() / "config"


def results_dir() -> Path:
    return repository_root() / "results"


def cache_dir() -> Path:
    path = repository_root() / ".cache"
    path.mkdir(exist_ok=True)
    return path


def paper_dir() -> Path:
    return repository_root() / "paper"


def relative(path: Path) -> str:
    """A path relative to the repository root, with forward slashes, for manifests."""

    try:
        return path.resolve().relative_to(repository_root()).as_posix()
    except ValueError:
        return path.as_posix()
