"""The harness's only way to change Dokploy: allowlisted procedures for seeds and drift."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from declarative_iac.domain.live.instance import require_local


class ForbiddenWrite(RuntimeError):
    """A write outside the pre-registered drift operators and scenario seeds."""


def fill(template: Any, identity: str | None) -> Any:
    """Replace `{id}` in a body template."""

    if isinstance(template, str):
        if "{id}" in template:
            if identity is None:
                raise ValueError("the body needs {id} but the operator has no target")
            return template.replace("{id}", identity)
        return template
    if isinstance(template, Mapping):
        return {k: fill(v, identity) for k, v in template.items()}
    if isinstance(template, list):
        return [fill(v, identity) for v in template]
    return template


class Writer:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        operations: set[str],
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.allowed = frozenset(operations)
        self.client = httpx.Client(
            base_url=require_local(base_url).rstrip("/") + "/api",
            headers={"x-api-key": api_key},
            timeout=60,
            transport=transport,
        )
        self.log: list[dict[str, Any]] = []

    def write(self, operation: str, body: Mapping[str, Any]) -> Any:
        if operation not in self.allowed:
            raise ForbiddenWrite(f"{operation} is not a pre-registered write")
        response = self.client.post(f"/{operation}", json=dict(body))
        self.log.append({"operation": operation, "status": response.status_code})
        response.raise_for_status()
        return response.json() if response.content else None
