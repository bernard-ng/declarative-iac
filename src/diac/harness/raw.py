"""Read-only Dokploy HTTP client used by the oracles.

Never send a mutating operation from here: the oracle must observe, not act. `GET` operations are
reads in Dokploy's tRPC-over-HTTP surface; the guard below refuses anything else.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import requests


@dataclass
class RawDokploy:
    base_url: str = field(default_factory=lambda: os.environ["DOKPLOY_URL"].rstrip("/"))
    api_key: str = field(default_factory=lambda: os.environ["DOKPLOY_API_KEY"], repr=False)
    timeout: float = 30.0

    def get(self, operation: str, **params) -> object:
        """Call a read operation such as `project.all` or `application.one`."""
        url = f"{self.base_url}/api/{operation}"
        r = requests.get(url, params=params, headers={"x-api-key": self.api_key}, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def post(self, *_a, **_k):  # pragma: no cover - deliberate guard
        raise PermissionError("the oracle is read-only; mutations belong to the system under test")

    def version(self) -> str:
        return str(self.get("settings.getDokployVersion"))
