"""Scenarios as data.

A scenario is an ordered list of steps; a step is a complete desired configuration. This module
turns the files in `config/scenarios/` into typed values and writes one step into a workspace in
the layout the system reads (`dokploy.workspace.yaml` and `.dokploy/`). It knows the document
format only as far as the format's public description (version 2, a `settings` or `project`
root, top-level directives); it never interprets a kind.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from declarative_iac.core.canonical import read_yaml

SETTINGS = "settings"
_CHANGE = re.compile(r"^(create|adopt|update|replace|delete|move|forget|no_op) (\S+)$")
_SLUG = re.compile(r"^[a-z][a-z0-9-]*$")


class ScenarioError(ValueError):
    """A scenario file that does not follow `config/scenarios/README.md`."""


class _Dumper(yaml.SafeDumper):
    """Writes plain YAML: the system rejects anchors and aliases."""

    def ignore_aliases(self, data: Any) -> bool:
        return True


def dump(document: Mapping[str, Any]) -> str:
    return yaml.dump(dict(document), Dumper=_Dumper, sort_keys=False, allow_unicode=True)


@dataclass(frozen=True)
class Change:
    kind: str
    address: str

    @classmethod
    def parse(cls, text: str) -> Change:
        match = _CHANGE.match(text)
        if not match:
            raise ScenarioError(f"an expected change is `kind address`, got {text!r}")
        return cls(match.group(1), match.group(2))

    def matches(self, kind: str, address: str) -> bool:
        return kind == self.kind and (
            address == self.address or address.endswith("/" + self.address)
        )


@dataclass(frozen=True)
class Expectation:
    changes: tuple[Change, ...] | None = None
    refused: bool = False
    apply_exit: int | None = None
    mutations: int | None = None
    remote_present: tuple[str, ...] = ()
    remote_absent: tuple[str, ...] = ()

    @classmethod
    def parse(cls, data: Mapping[str, Any] | None) -> Expectation | None:
        if data is None:
            return None
        unknown = set(data) - {
            "changes",
            "refused",
            "apply_exit",
            "mutations",
            "remote_present",
            "remote_absent",
        }
        if unknown:
            raise ScenarioError(f"unknown expectation keys {sorted(unknown)}")
        changes = data.get("changes")
        return cls(
            changes=None if changes is None else tuple(Change.parse(c) for c in changes),
            refused=bool(data.get("refused", False)),
            apply_exit=data.get("apply_exit"),
            mutations=data.get("mutations"),
            remote_present=tuple(data.get("remote_present", ())),
            remote_absent=tuple(data.get("remote_absent", ())),
        )


@dataclass(frozen=True)
class Observation:
    """A fact about Dokploy, stated in Dokploy's own response names, that must hold after the
    step converges (H3). `collection` names an entry of `config/observer.yaml`."""

    collection: str
    name: str
    field: str | None = None
    equals: Any = None
    contains: str | None = None
    equals_secret: str | None = None
    contains_secret: str | None = None
    absent: bool = False

    @classmethod
    def parse(cls, data: Mapping[str, Any]) -> Observation:
        allowed = {
            "collection",
            "name",
            "field",
            "equals",
            "contains",
            "equals_secret",
            "contains_secret",
            "absent",
        }
        unknown = set(data) - allowed
        if unknown:
            raise ScenarioError(f"unknown observation keys {sorted(unknown)}")
        checks = [
            k for k in ("equals", "contains", "equals_secret", "contains_secret") if k in data
        ]
        if len(checks) > 1 or (checks and "field" not in data):
            raise ScenarioError("an observation checks at most one field, by one comparison")
        return cls(
            collection=data["collection"],
            name=str(data["name"]),
            field=data.get("field"),
            equals=data.get("equals"),
            contains=data.get("contains"),
            equals_secret=data.get("equals_secret"),
            contains_secret=data.get("contains_secret"),
            absent=bool(data.get("absent", False)),
        )

    def holds(self, view: Mapping[str, list[dict[str, Any]]], secrets: Mapping[str, str]) -> bool:
        rows = [r for r in view.get(self.collection, []) if str(r.get("name")) == self.name]
        if self.absent:
            return not rows
        if len(rows) != 1:
            return False
        if self.field is None:
            return True
        value = rows[0].get(self.field)
        if self.equals_secret is not None:
            return value == secrets.get(self.equals_secret)
        if self.contains_secret is not None:
            return isinstance(value, str) and secrets.get(self.contains_secret, "\0") in value
        if self.contains is not None:
            return isinstance(value, str) and self.contains in value
        return value == self.equals


@dataclass(frozen=True)
class Seed:
    """A write made directly against Dokploy before the step, to create pre-existing state."""

    operation: str
    body: Mapping[str, Any]


@dataclass(frozen=True)
class Step:
    settings: Mapping[str, Any] | None
    projects: Mapping[str, Mapping[str, Any]]
    files: Mapping[str, str]
    secrets: tuple[str, ...]
    rotate: tuple[str, ...]
    directives: Mapping[str, Mapping[str, Any]]
    apply_flags: tuple[str, ...]
    seed: tuple[Seed, ...]
    expect: Expectation | None
    observe: tuple[Observation, ...] = ()

    @classmethod
    def parse(cls, data: Mapping[str, Any]) -> Step:
        allowed = {
            "settings",
            "projects",
            "files",
            "secrets",
            "rotate",
            "directives",
            "apply_flags",
            "seed",
            "expect",
            "observe",
        }
        unknown = set(data) - allowed
        if unknown:
            raise ScenarioError(f"unknown step keys {sorted(unknown)}")
        projects = dict(data.get("projects") or {})
        for slug in projects:
            if not _SLUG.match(slug):
                raise ScenarioError(f"project slug {slug!r} is not a valid slug")
        directives = dict(data.get("directives") or {})
        for target in directives:
            if target != SETTINGS and target not in projects:
                raise ScenarioError(f"directives for {target!r}, which the step does not declare")
        for path in data.get("files") or {}:
            if not path.startswith(".dokploy/files/") or ".." in path.split("/"):
                raise ScenarioError(f"file {path!r} must be below .dokploy/files/")
        secrets = tuple(data.get("secrets") or ())
        rotate = tuple(data.get("rotate") or ())
        if set(rotate) - set(secrets):
            raise ScenarioError("a rotated secret must be one of the step's secrets")
        return cls(
            settings=data.get("settings"),
            projects=projects,
            files=dict(data.get("files") or {}),
            secrets=secrets,
            rotate=rotate,
            directives=directives,
            apply_flags=tuple(data.get("apply_flags") or ()),
            seed=tuple(Seed(s["operation"], s.get("body", {})) for s in data.get("seed") or ()),
            expect=Expectation.parse(data.get("expect")),
            observe=tuple(Observation.parse(o) for o in data.get("observe") or ()),
        )

    def documents(self) -> dict[str, dict[str, Any]]:
        """Workspace-relative path -> document, in manifest order (settings first)."""

        out: dict[str, dict[str, Any]] = {}
        if self.settings is not None or SETTINGS in self.directives:
            doc: dict[str, Any] = {"version": 2, "settings": dict(self.settings or {})}
            doc.update(self.directives.get(SETTINGS, {}))
            out[".dokploy/settings.yaml"] = doc
        for slug, body in self.projects.items():
            doc = {"version": 2, "project": {"slug": slug, **dict(body)}}
            doc.update(self.directives.get(slug, {}))
            out[f".dokploy/projects/{slug}.yaml"] = doc
        return out


@dataclass(frozen=True)
class Scenario:
    id: str
    family: str
    covers: tuple[str, ...]
    steps: tuple[Step, ...]

    @property
    def documents(self) -> list[str]:
        """Every document path any step uses, in first-use order."""

        seen: dict[str, None] = {}
        for step in self.steps:
            seen.update(dict.fromkeys(step.documents()))
        return list(seen)


@dataclass(frozen=True)
class Family:
    name: str
    purpose: str
    path: Path
    scenarios: dict[str, Scenario] = field(default_factory=dict)


def load_family(path: Path) -> Family:
    data = read_yaml(path)
    name = data["family"]
    family = Family(name, " ".join(str(data.get("purpose", "")).split()), path)
    for scenario_id, body in (data.get("scenarios") or {}).items():
        if not scenario_id.startswith(f"{name}-"):
            raise ScenarioError(f"scenario {scenario_id!r} must start with {name!r}-")
        try:
            steps = tuple(Step.parse(step) for step in body["steps"])
        except ScenarioError as error:
            raise ScenarioError(f"{path.name}: {scenario_id}: {error}") from error
        if not steps:
            raise ScenarioError(f"{scenario_id} has no steps")
        family.scenarios[scenario_id] = Scenario(
            scenario_id, name, tuple(body.get("covers", ())), steps
        )
    return family


def load_families(directory: Path) -> dict[str, Family]:
    families = {f.name: f for f in (load_family(p) for p in sorted(directory.glob("*.yaml")))}
    ids = [s for f in families.values() for s in f.scenarios]
    if len(ids) != len(set(ids)):
        raise ScenarioError("scenario ids must be unique across families")
    return families


def materialise(step: Step, workspace: Path) -> list[str]:
    """Write `step` as the complete content of `workspace`; return the document paths.

    Documents a previous step wrote but this step does not declare are removed from the manifest
    and the disk, which is how a configuration stops declaring a whole document. State and
    secrets directories are left alone: they belong to the system.
    """

    documents = step.documents()
    dokploy = workspace / ".dokploy"
    for stale in list((dokploy / "projects").glob("*.yaml")) if dokploy.exists() else []:
        if str(stale.relative_to(workspace)) not in documents:
            stale.unlink()
    settings = dokploy / "settings.yaml"
    if settings.exists() and ".dokploy/settings.yaml" not in documents:
        settings.unlink()
    for relative, document in documents.items():
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(dump(document), encoding="utf-8")
    for relative, text in step.files.items():
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    manifest = {"version": 1, "documents": list(documents)}
    (workspace / "dokploy.workspace.yaml").write_text(dump(manifest), encoding="utf-8")
    return list(documents)
