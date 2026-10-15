from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from declarative_iac.core.paths import config_dir
from declarative_iac.domain.scenarios import load_families, materialise
from declarative_iac.domain.scenarios.model import Change, ScenarioError, Step


def test_every_family_loads_and_ids_are_unique():
    families = load_families(config_dir() / "scenarios")
    assert set(families) == {"unit", "topology", "lifecycle", "realistic"}
    assert all(f.scenarios for f in families.values())


def test_expectations_parse_and_match_address_suffixes():
    change = Change.parse("update tag.probe")
    assert change.matches("update", "tag.probe")
    assert change.matches("update", "project.x/tag.probe")
    assert not change.matches("update", "project.x/tag.probe2")
    assert not change.matches("create", "tag.probe")
    with pytest.raises(ScenarioError):
        Change.parse("rename tag.probe")


def test_steps_refuse_unknown_keys_and_unsafe_paths():
    with pytest.raises(ScenarioError):
        Step.parse({"setings": {}})
    with pytest.raises(ScenarioError):
        Step.parse({"files": {"../escape.txt": "x"}})
    with pytest.raises(ScenarioError):
        Step.parse({"secrets": ["A"], "rotate": ["B"]})
    with pytest.raises(ScenarioError):
        Step.parse({"directives": {"nowhere": {"moves": []}}})


def test_materialise_writes_the_workspace_layout_without_aliases(tmp_path: Path):
    shared = {"environments": {"production": {}}}
    step = Step.parse(
        {
            "settings": {"tags": {"a": {}}},
            "projects": {"one": shared, "two": shared},
            "files": {".dokploy/files/x.txt": "x"},
            "directives": {"settings": {"removed": [{"from": "tag.b"}]}},
        }
    )
    documents = materialise(step, tmp_path)
    assert documents == [
        ".dokploy/settings.yaml",
        ".dokploy/projects/one.yaml",
        ".dokploy/projects/two.yaml",
    ]
    manifest = yaml.safe_load((tmp_path / "dokploy.workspace.yaml").read_text())
    assert manifest == {"version": 1, "documents": documents}
    two = (tmp_path / ".dokploy/projects/two.yaml").read_text()
    assert "&" not in two and "*" not in two
    assert yaml.safe_load(two)["project"]["slug"] == "two"
    settings = yaml.safe_load((tmp_path / ".dokploy/settings.yaml").read_text())
    assert settings["removed"] == [{"from": "tag.b"}]

    smaller = Step.parse({"projects": {"one": shared}})
    assert materialise(smaller, tmp_path) == [".dokploy/projects/one.yaml"]
    assert not (tmp_path / ".dokploy/projects/two.yaml").exists()
    assert not (tmp_path / ".dokploy/settings.yaml").exists()
