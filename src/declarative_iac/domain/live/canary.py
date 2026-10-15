"""Canary secrets: distinctive values whose appearance anywhere is a leak."""

from __future__ import annotations

import secrets
from pathlib import Path


def make_canary(label: str) -> str:
    return f"diac-canary-{label}-{secrets.token_hex(8)}"


def scan(paths: list[Path], texts: list[str], canaries: list[str]) -> list[str]:
    """Where any canary appears: files below `paths` (excluding secret source files the
    workspace legitimately holds) and captured texts."""

    found: list[str] = []
    for root in paths:
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            if "secrets" in path.relative_to(root).parts:
                continue
            data = path.read_bytes()
            found += [f"{path}: {c[:24]}..." for c in canaries if c.encode() in data]
    for index, text in enumerate(texts):
        found += [f"captured output #{index}: {c[:24]}..." for c in canaries if c in text]
    return found
