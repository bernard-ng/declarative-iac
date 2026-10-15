"""Deterministic serialisation: the same data always yields the same bytes."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml


def canonical_json(value: Any) -> bytes:
    """Sorted keys, fixed separators, UTF-8, one trailing newline."""

    text = json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
    return (text + "\n").encode("utf-8")


def write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(value))
    return path


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: Iterable[Mapping[str, Any]], columns: Sequence[str]) -> Path:
    """Write rows in the given column order, LF line endings, no index."""

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: _cell(row.get(column)) for column in columns})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(buffer.getvalue(), encoding="utf-8")
    return path


def _cell(value: Any) -> Any:
    if isinstance(value, (list, tuple, set, frozenset)):
        return ";".join(str(item) for item in sorted(value, key=str))
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return value


def read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_yaml_text(text: str | bytes) -> Any:
    return yaml.safe_load(text)
