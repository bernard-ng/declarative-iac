"""Load kind specs from the SUT snapshot and derive feature inventories (no SUT code is imported)."""
from __future__ import annotations

from collections import Counter, defaultdict

from .sut import Snapshot


def load_specs(snap: Snapshot) -> dict[str, dict]:
    out = {}
    for rel in snap.files("specs"):
        if not rel.endswith(".yaml") or rel.endswith(("versions.yaml", "types.yaml")):
            continue
        spec = snap.read_yaml(rel)
        out[spec["kind"]] = {**spec, "_file": rel}
    return out


def walk_fields(fields: dict | None, prefix: str = ""):
    """Yield (path, field) for every field, union-arm member, and struct member."""
    for name, f in (fields or {}).items():
        f = f or {}
        yield prefix + name, f
        for arm, members in (f.get("arms") or {}).items():
            yield from walk_fields(members, f"{prefix}{name}.{arm}.")
        for key in ("fields", "members"):
            if isinstance(f.get(key), dict):
                yield from walk_fields(f[key], f"{prefix}{name}.")


def _ops(node, found: set[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "op" and isinstance(v, str):
                found.add(v)
            elif k == "ops" and isinstance(v, dict):
                found.update(x for x in v.values() if isinstance(x, str))
            else:
                _ops(v, found)
    elif isinstance(node, list):
        for x in node:
            _ops(x, found)


def spec_operation_roles(specs: dict[str, dict]) -> dict[str, set[str]]:
    """Map each OpenAPI operation id to the roles the specs assign it (create, write_group, ...)."""
    roles: dict[str, set[str]] = defaultdict(set)

    def tag(node, role: str) -> None:
        found: set[str] = set()
        _ops(node, found)
        for op in found:
            roles[op].add(role)

    for s in specs.values():
        api = s.get("api") or {}
        for key in ("create", "update", "remove", "deploy"):
            if api.get(key):
                tag(api[key], key)
        read = api.get("read") or {}
        for key in ("list", "one", "singleton"):
            if read.get(key):
                tag(read[key], f"read_{key}")
        tag(s.get("write") or [], "write_group")
        for _, f in walk_fields(s.get("fields")):
            if f.get("membership"):
                tag(f["membership"], "membership")
            if f.get("entry"):
                tag(f["entry"], "entry")
    return roles


GRAMMAR_FIELD_ATTRS = ["nullable", "read_nullable", "default", "needs_deploy", "disruptive", "fallback",
                       "granularity", "entry", "trim", "read_normalization", "file_key", "request",
                       "list_api", "json", "key_selector", "since", "until", "membership", "nest",
                       "resend_on_update"]
GRAMMAR_KIND_ATTRS = ["singleton", "made_with_parent", "hook", "since"]
GRAMMAR_API_ATTRS = ["attach", "attach_by_parent", "parent_field", "send", "from_read", "query_by_parent",
                     "embedded_in", "scope", "agree", "id_from", "merge", "fallback", "update_id", "by_variant"]


def _count_keys(node, keys: set[str], counter: Counter) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k in keys:
                counter[k] += 1
            _count_keys(v, keys, counter)
    elif isinstance(node, list):
        for x in node:
            _count_keys(x, keys, counter)


def grammar_usage(spec: dict) -> Counter:
    c: Counter = Counter()
    for k in GRAMMAR_KIND_ATTRS:
        if spec.get(k):
            c[f"kind.{k}"] += 1
    for _, f in walk_fields(spec.get("fields")):
        for k in GRAMMAR_FIELD_ATTRS:
            if k in f and f[k] not in (False, None):
                c[f"field.{k}"] += 1
        t = str(f.get("type", ""))
        for tname in ("union(", "struct", "map<", "set<", "list<", "env", "file", "blob(", "ref(", "selector(", "enum["):
            if t.startswith(tname) or (tname in ("set<", "map<") and tname in t):
                c[f"type.{tname.rstrip('(<[')}"] += 1
    api_counter: Counter = Counter()
    _count_keys(spec.get("api") or {}, set(GRAMMAR_API_ATTRS), api_counter)
    _count_keys(spec.get("write") or [], {"by_variant"}, api_counter)
    for k, v in api_counter.items():
        c[f"api.{k}"] += v
    return c
