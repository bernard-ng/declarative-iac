from __future__ import annotations

import hashlib
import tarfile
from pathlib import Path

import pytest
import typer

from declarative_iac.workflow import archive, reproduce


def test_levels_are_nested_and_end_with_the_claims_check():
    zero, one, two = (reproduce.commands(n) for n in (0, 1, 2))
    assert zero == [["claims", "verify"], ["claims", "check-paper"]]
    assert ["static", "run", "--all"] in one and ["static", "run", "--all"] in two
    assert all(["live", "run", name] in two for name in reproduce.LIVE)
    assert two[-2] == ["claims", "verify", "--strict"]
    with pytest.raises(typer.BadParameter):
        reproduce.commands(3)


def test_the_archive_is_byte_identical_and_excludes_workspaces(tmp_path: Path):
    root = tmp_path / "repo"
    (root / "results" / "live" / "run" / "workspace" / ".dokploy").mkdir(parents=True)
    (root / "results" / "live" / "run" / "workspace" / ".dokploy" / "x").write_text("canary")
    (root / "results" / "live" / "run" / "result.json").write_text("{}")
    (root / "README.md").write_text("readme")
    first, n = archive.build(root, tmp_path / "a.tar.gz", "pkg")
    second, _ = archive.build(root, tmp_path / "b.tar.gz", "pkg")
    digest = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (first, second)]
    assert digest[0] == digest[1] and n == 2
    with tarfile.open(first) as tar:
        names = tar.getnames()
        sums = tar.extractfile("pkg/SHA256SUMS")
        assert sums is not None
        listed = sums.read().decode()
    assert "pkg/results/live/run/result.json" in names
    assert not any("workspace" in name for name in names)
    assert "README.md" in listed and "workspace" not in listed
