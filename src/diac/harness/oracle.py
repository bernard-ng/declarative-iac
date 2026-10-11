"""Independent expected-state checks (oracle O-raw).

Rules for writing an oracle check:
  * derive field mappings from Dokploy's responses (fixtures or live reads), never from the SUT's
    specs or Rust code; the point is to catch a spec that maps a field wrongly;
  * compare only fields the scenario's document owns (omitted fields are unmanaged, ADR 0004);
  * secrets are checked for presence/absence only, never by value.

Each check returns a list of Mismatch records; an empty list means the remote state matches.
"""
from __future__ import annotations

from dataclasses import dataclass

from .raw import RawDokploy


@dataclass
class Mismatch:
    address: str
    field: str
    expected: object
    observed: object


def check_tags(raw: RawDokploy, declared: dict[str, dict]) -> list[Mismatch]:
    """declared: {key: {name, color}} from the scenario's settings document."""
    observed = {t["name"]: t for t in raw.get("tag.all")}
    out = []
    for key, want in declared.items():
        name = want.get("name", key)
        got = observed.get(name)
        if got is None:
            out.append(Mismatch(f"tag.{key}", "<exists>", True, False))
            continue
        if "color" in want and got.get("color") != want["color"]:
            out.append(Mismatch(f"tag.{key}", "color", want["color"], got.get("color")))
    return out


def project_topology(raw: RawDokploy) -> dict[str, dict[str, set[str]]]:
    """{project name: {environment name: {service names}}} from `project.all` (independent of specs)."""
    topo: dict[str, dict[str, set[str]]] = {}
    for p in raw.get("project.all"):
        envs = {}
        for e in p.get("environments", []):
            names = set()
            for coll in ("applications", "compose", "postgres", "mysql", "mariadb", "mongo", "redis", "libsql"):
                names.update(s.get("name", "") for s in e.get(coll, []))
            envs[e["name"]] = names
        topo[p["name"]] = envs
    return topo


def unmanaged_snapshot(raw: RawDokploy) -> dict:
    """Coarse whole-instance snapshot used by O-unmanaged: compare before/after, minus managed ids."""
    return {
        "projects": raw.get("project.all"),
        "tags": raw.get("tag.all"),
        "registries": raw.get("registry.all"),
        "servers": raw.get("server.all"),
    }
