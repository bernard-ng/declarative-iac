from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from declarative_iac.core.manifest import RunManifest, verify_manifest
from declarative_iac.domain.provenance import Snapshot, SnapshotConfig
from declarative_iac.domain.provenance.snapshot import SnapshotError


def config_for(commit: str) -> SnapshotConfig:
    return replace(SnapshotConfig.load(), commit=commit)


def test_files_are_read_at_the_commit_not_from_the_working_tree(sut_repo):
    repo, commit = sut_repo
    snapshot = Snapshot(config_for(commit), checkout=repo)
    snapshot.ensure()
    assert 'channel = "1.97.1"' in snapshot.show_text("rust-toolchain.toml")
    assert snapshot.verify() == []
    assert [v.version for v in snapshot.dokploy_versions()] == ["0.30.6"]
    assert snapshot.list_files("specs") == ["specs/versions.yaml"]


def test_a_missing_commit_is_refused(sut_repo):
    repo, _ = sut_repo
    snapshot = Snapshot(config_for("0" * 40), checkout=repo)
    with pytest.raises(SnapshotError):
        snapshot.ensure()


def test_a_tag_on_another_commit_is_reported(sut_repo):
    repo, commit = sut_repo
    other = replace(config_for(commit), tag="missing-tag")
    assert any("missing-tag" in problem for problem in Snapshot(other, checkout=repo).verify())


def test_a_manifest_detects_a_changed_output(tmp_path: Path):
    out = tmp_path / "result"
    out.mkdir()
    data = out / "summary.json"
    data.write_text("{}\n")
    manifest = RunManifest(experiment="t", output_dir=out, snapshot="B1", command=["t"])
    path = manifest.finish([data])
    record = json.loads(path.read_text())
    assert set(record["outputs"]) == {"summary.json"}
    assert verify_manifest(path) == []
    data.write_text('{"changed": true}\n')
    assert verify_manifest(path) == [f"{data.as_posix()}: content differs from its manifest"]
