"""Drift and partial-state operators (E3). These mutate Dokploy *behind the engine's back*.

Kept separate from the read-only oracle on purpose. Each operator returns a description of the
expected plan (metamorphic relation, H5): the actions that revert exactly this perturbation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import requests


@dataclass
class Perturber:
    base_url: str = field(default_factory=lambda: os.environ["DOKPLOY_URL"].rstrip("/"))
    api_key: str = field(default_factory=lambda: os.environ["DOKPLOY_API_KEY"], repr=False)

    def call(self, operation: str, body: dict) -> object:
        r = requests.post(f"{self.base_url}/api/{operation}", json=body,
                          headers={"x-api-key": self.api_key}, timeout=60)
        r.raise_for_status()
        return r.json() if r.content else None


# operator name -> (description, expected plan shape). Implementations are scenario-specific and
# registered by experiments/e3_convergence/operators.py; the list here is the pre-registered set.
DRIFT_OPERATORS = {
    "owned_field":       ("change a field the document owns",               "one update naming that path"),
    "unowned_field":     ("change a field the document omits",              "empty plan"),
    "delete_managed":    ("delete a managed resource",                       "one create at its address"),
    "colliding_sibling": ("create an unmanaged sibling with the same name",  "blocked plan (unmanaged collision)"),
    "secret_rotation":   ("rotate a secret value out of band",               "empty plan (write-only, not observable)"),
    "env_var_added":     ("add an environment variable the document never named", "empty plan"),
    "env_var_changed":   ("change a variable the document owns",             "one update naming that variable"),
    "reparent":          ("move a service to another environment",           "blocked or move, per spec"),
    "ignored_path":      ("change a path listed in lifecycle.ignore_changes", "empty plan"),
}
