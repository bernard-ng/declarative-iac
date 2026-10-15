"""A read-only view of Dokploy, written from Dokploy's recorded responses, not from the system's
specifications (independent oracle, paper Section 9)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from declarative_iac.core.canonical import read_yaml
from declarative_iac.domain.live.instance import require_local


class ForbiddenOperation(RuntimeError):
    """The observer was asked to call an operation outside its read-only allowlist."""


@dataclass(frozen=True)
class Collection:
    """How the observer lists one kind of Dokploy object.

    `operation` lists the objects (or, with `within`, the name of a collection whose detail
    responses embed them); `path` descends through nested lists of the response; `detail` reads
    each object individually when the list carries too little. Field names are Dokploy's response
    names, taken from recorded responses, never from the system's specifications.
    """

    kind: str
    operation: str | None
    id_field: str
    name_field: str | None
    fields: tuple[str, ...]
    path: tuple[str, ...] = ()
    detail: tuple[str, str] | None = None
    within: str | None = None
    parent: str | None = None


def load_collections(path: Path) -> list[Collection]:
    data = read_yaml(path)
    out: list[Collection] = []
    for kind, body in data["collections"].items():
        detail = body.get("detail")
        out.append(
            Collection(
                kind=kind,
                operation=body.get("list"),
                id_field=body["id"],
                name_field=body.get("name"),
                fields=tuple(body.get("fields", ())),
                path=tuple(body.get("path", ())),
                detail=(detail["operation"], detail["param"]) if detail else None,
                within=body.get("within"),
                parent=body.get("parent"),
            )
        )
    known = {c.kind for c in out}
    for collection in out:
        if collection.within and collection.within not in known:
            raise ValueError(f"{collection.kind} is read within unknown {collection.within}")
        if not collection.within and not collection.operation:
            raise ValueError(f"{collection.kind} needs `list` or `within`")
    return out


def read_operations(collections: list[Collection]) -> set[str]:
    names = {c.operation for c in collections if c.operation and not c.within}
    return names | {c.detail[0] for c in collections if c.detail}


def _descend(
    node: Any, path: tuple[str, ...], enclosing: dict[str, Any] | None = None
) -> Iterator[tuple[dict[str, Any] | None, dict[str, Any]]]:
    """(enclosing object, item) for every object at the end of `path`."""

    if not path:
        if isinstance(node, list):
            yield from ((enclosing, item) for item in node if isinstance(item, dict))
        elif isinstance(node, dict):
            yield enclosing, node
        return
    items = node if isinstance(node, list) else [node]
    for item in items:
        if isinstance(item, dict):
            yield from _descend(item.get(path[0]) or [], path[1:], item)


class Observer:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        read_operations: set[str],
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.allowed = frozenset(read_operations)
        self.client = httpx.Client(
            base_url=require_local(base_url).rstrip("/") + "/api",
            headers={"x-api-key": api_key},
            timeout=60,
            transport=transport,
        )

    def read(self, operation: str, **query: str) -> Any:
        if operation not in self.allowed:
            raise ForbiddenOperation(f"{operation} is not a read operation of the contract")
        response = self.client.get(f"/{operation}", params=query)
        response.raise_for_status()
        return response.json()

    def snapshot(self, collections: list[Collection]) -> dict[str, list[dict[str, Any]]]:
        """Every object of every collection, reduced to the compared fields, sorted by id.

        Parents are read before the collections `within` them; each row records its parent id.
        """

        view: dict[str, list[dict[str, Any]]] = {}
        details: dict[str, dict[str, Any]] = {}
        pending = list(collections)
        while pending:
            collection = next(
                c for c in pending if not c.within or c.within in details or c.within in view
            )
            pending.remove(collection)
            sources: list[tuple[str | None, Any]]
            if collection.within:
                sources = list(details.get(collection.within, {}).items())
            else:
                if collection.operation is None:
                    raise RuntimeError("collection.operation is required here")
                listed = self.read(collection.operation)
                if isinstance(listed, dict) and ("items" in listed or "data" in listed):
                    listed = listed.get("items") or listed.get("data") or []
                sources = [(None, listed)]
            rows: list[dict[str, Any]] = []
            own: dict[str, Any] = {}
            for owner, node in sources:
                for enclosing, item in _descend(node, collection.path):
                    parent = owner
                    if collection.parent and enclosing is not None:
                        parent = str(enclosing.get(collection.parent))
                    identity = item.get(collection.id_field)
                    record = item
                    if collection.detail and identity is not None:
                        operation, param = collection.detail
                        record = self.read(operation, **{param: str(identity)})
                        own[str(identity)] = record
                    rows.append(
                        {
                            "id": identity,
                            "parent": parent,
                            "name": record.get(collection.name_field)
                            if collection.name_field
                            else None,
                            **{f: record.get(f) for f in collection.fields},
                        }
                    )
            details[collection.kind] = own
            view[collection.kind] = sorted(rows, key=lambda row: str(row["id"]))
        return view


def diff_snapshots(
    before: dict[str, list[dict]], after: dict[str, list[dict]], managed_ids: set[str]
) -> list[dict[str, Any]]:
    """Changes between two snapshots outside the managed identities (H4)."""

    changes: list[dict[str, Any]] = []
    for kind in sorted(set(before) | set(after)):
        old = {str(r["id"]): r for r in before.get(kind, [])}
        new = {str(r["id"]): r for r in after.get(kind, [])}
        for identity in sorted(set(old) | set(new)):
            if identity in managed_ids:
                continue
            if old.get(identity) != new.get(identity):
                changes.append(
                    {
                        "kind": kind,
                        "id": identity,
                        "before": old.get(identity),
                        "after": new.get(identity),
                    }
                )
    return changes
