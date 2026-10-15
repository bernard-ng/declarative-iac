"""The kind specifications of the snapshot, loaded as plain data and walked generically."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from statistics import median
from typing import Any

from declarative_iac.core.canonical import load_yaml_text


def walk(node: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    """Every (key path, value) pair below a mapping; list items keep their parent's path."""

    if isinstance(node, dict):
        for key, value in node.items():
            yield (*path, str(key)), value
            yield from walk(value, (*path, str(key)))
    elif isinstance(node, list):
        for item in node:
            yield from walk(item, path)


def walk_fields(fields: dict[str, Any] | None, prefix: str = "") -> list[tuple[str, dict]]:
    """Field declarations, including struct members and the members of each union arm."""

    out: list[tuple[str, dict]] = []
    for name, declaration in (fields or {}).items():
        declaration = declaration or {}
        out.append((prefix + name, declaration))
        for arm, members in (declaration.get("arms") or {}).items():
            out += walk_fields(members, f"{prefix}{name}.{arm}.")
        for key in ("fields", "members"):
            if isinstance(declaration.get(key), dict):
                out += walk_fields(declaration[key], f"{prefix}{name}.")
    return out


@dataclass(frozen=True)
class KindSpec:
    """One specification file, kept as the YAML mapping it is."""

    path: str
    data: dict[str, Any]

    @property
    def kind(self) -> str:
        return str(self.data["kind"])

    @property
    def scope(self) -> str:
        return str(self.data.get("scope"))

    @property
    def api(self) -> dict[str, Any]:
        return self.data.get("api") or {}

    @property
    def reads(self) -> dict[str, Any]:
        return self.api.get("read") or {}

    @property
    def list_read(self) -> dict[str, Any]:
        value = self.reads.get("list")
        return value if isinstance(value, dict) else {}

    @property
    def write_groups(self) -> list[dict[str, Any]]:
        return list(self.data.get("write") or [])

    @property
    def fields(self) -> list[tuple[str, dict]]:
        return walk_fields(self.data.get("fields"))

    def has_key(self, key: str, value: Any = ...) -> bool:
        return any(p[-1] == key and (value is ... or v == value) for p, v in walk(self.data))

    def field_has(self, key: str, value: Any = ...) -> bool:
        return any(
            key in declaration and (value is ... or declaration[key] == value)
            for _, declaration in self.fields
        )

    def field_type_starts(self, prefix: str) -> bool:
        return any(str(d.get("type", "")).startswith(prefix) for _, d in self.fields)

    def read_form(self) -> str:
        """`singleton`, `embedded`, `scoped`, `flat`, or `none` (Section 5.2)."""

        if "singleton" in self.reads:
            return "singleton"
        if not self.list_read:
            return "none"
        if "embedded_in" in self.list_read:
            return "embedded"
        if "scope" in self.list_read:
            return "scoped"
        return "flat"

    def create_identity(self) -> str | None:
        identity = self.api.get("create_identity")
        if isinstance(identity, dict) and identity:
            return str(next(iter(identity)))
        return str(identity) if identity else None

    def write_operations(self) -> set[str]:
        ops: set[str] = set()
        for group in self.write_groups:
            if "op" in group:
                ops.add(str(group["op"]))
            ops.update(str(op) for op in (group.get("ops") or {}).values())
        return ops

    def operations_named(self, known: set[str]) -> set[str]:
        """Every string in the specification that names an operation of the contract."""

        return {v for _, v in walk(self.data) if isinstance(v, str) and v in known}


class SpecCatalog:
    """All kind specifications of the snapshot, sorted by kind."""

    def __init__(self, specs: list[KindSpec]) -> None:
        self.specs = sorted(specs, key=lambda spec: spec.kind)

    @classmethod
    def from_files(cls, files: dict[str, bytes]) -> SpecCatalog:
        return cls([KindSpec(path, load_yaml_text(text)) for path, text in sorted(files.items())])

    def __iter__(self) -> Iterator[KindSpec]:
        return iter(self.specs)

    def __len__(self) -> int:
        return len(self.specs)

    def get(self, kind: str) -> KindSpec:
        return next(spec for spec in self.specs if spec.kind == kind)

    def kinds(self, predicate: Any) -> list[str]:
        return [spec.kind for spec in self.specs if predicate(spec)]


def distribution(values: list[int]) -> dict[str, float | int]:
    return {
        "median": median(values),
        "min": min(values),
        "max": max(values),
        "count": len(values),
    }
