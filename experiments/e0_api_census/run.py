import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

"""E0 - API census (RQ1, RQ3).

Enumerates every operation in each pinned Dokploy OpenAPI document, classifies it lexically
(procedure-name heuristics), records request-side size and whether the 200 response schema is
the closed empty object, and joins it with the role the kind specs give it (the specs act as
an expert annotation of the API). Outputs: operations.csv, routers.csv, summary.json.
"""
import argparse
import json
from collections import Counter

import pandas as pd

from diac.results import output_dir, write_manifest
from diac.specs import load_specs, spec_operation_roles
from diac.sut import Snapshot

LEXICON = {
    "create": "create", "one": "read_one", "get": "read_one", "all": "list", "search": "list",
    "list": "list", "getAll": "list", "update": "update", "remove": "delete", "delete": "delete",
}


def request_fields(op: dict) -> int:
    n = len([p for p in op.get("parameters", []) if p.get("in") == "query"])
    body = (op.get("requestBody") or {}).get("content", {}).get("application/json", {}).get("schema", {})
    return n + len(body.get("properties", {}) or {})


def empty_response(op: dict) -> bool:
    s = op.get("responses", {}).get("200", {}).get("content", {}).get("application/json", {}).get("schema", {})
    return s.get("type") == "object" and not s.get("properties") and s.get("additionalProperties") is False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot")
    args = ap.parse_args()
    snap = Snapshot.load(args.snapshot)
    versions = snap.read_yaml("specs/versions.yaml")["versions"]
    specs = load_specs(snap)
    roles = spec_operation_roles(specs)  # operation id -> set of roles

    rows = []
    for v in versions:
        doc = json.loads(snap.read(v["openapi"]))
        for path, item in doc["paths"].items():
            for method, op in item.items():
                if method not in {"get", "post", "put", "patch", "delete"}:
                    continue
                name = path.strip("/")
                router, proc = name.split(".", 1)[0], name.split(".")[-1]
                spec_roles = sorted(roles.get(name, set()))
                rows.append(dict(
                    dokploy_version=v["version"], operation=name, router=router, procedure=proc,
                    http_method=method.upper(), lexical_role=LEXICON.get(proc, "other"),
                    request_fields=request_fields(op), response_schema_empty=empty_response(op),
                    used_by_spec=bool(spec_roles), spec_roles=";".join(spec_roles),
                ))
    ops = pd.DataFrame(rows)
    out = output_dir("e0_api_census", snap)
    ops.to_csv(out / "operations.csv", index=False)

    base = ops[ops.dokploy_version == versions[0]["version"]]
    routers = base.groupby("router").agg(
        operations=("operation", "count"),
        lexical_crud=("lexical_role", lambda s: int((s != "other").sum())),
        used_by_spec=("used_by_spec", "sum"),
    ).reset_index().sort_values("operations", ascending=False)
    routers.to_csv(out / "routers.csv", index=False)

    used = base[base.used_by_spec]
    summary = {
        "per_version_operation_counts": ops.groupby("dokploy_version").size().to_dict(),
        "base_version": versions[0]["version"],
        "operations": int(len(base)),
        "routers": int(base.router.nunique()),
        "lexical_crud_operations": int((base.lexical_role != "other").sum()),
        "response_schema_empty": int(base.response_schema_empty.sum()),
        "operations_used_by_specs": int(len(used)),
        "routers_used_by_specs": int(used.router.nunique()),
        "used_ops_by_lexical_role": used.lexical_role.value_counts().to_dict(),
        "used_ops_non_crud_names": sorted(used[used.lexical_role == "other"].operation.tolist()),
        "added_in_later_versions": sorted(set(ops.operation) - set(base.operation)),
        "removed_in_later_versions": sorted(set(base.operation) - set(ops[ops.dokploy_version == versions[-1]["version"]].operation)),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    write_manifest(out, "e0_api_census", snap, dokploy_versions=[v["version"] for v in versions])
    print(json.dumps({k: v for k, v in summary.items() if not isinstance(v, list)}, indent=2))


if __name__ == "__main__":
    main()
