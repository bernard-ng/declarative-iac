"""The recorded live responses of the snapshot (paper Section 7.1)."""

from __future__ import annotations

from collections import Counter


def count_by_version(files: list[str], root: str) -> dict[str, int]:
    """Files below `<root>/<version>/`, counted per version."""

    prefix = root.rstrip("/") + "/"
    versions = Counter(
        path[len(prefix) :].split("/", 1)[0] for path in files if path.startswith(prefix)
    )
    return dict(sorted(versions.items()))
