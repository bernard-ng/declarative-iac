"""`declarative-iac archive`: the deposit for Zenodo, as one reproducible tarball.

The archive holds what a reviewer needs to check every claim without this repository's history:
the harness source and lock file (so `uv sync` works), the manuscript, results (with raw logs
when present), manifests, claims, configuration, the pre-registration, and SHA256SUMS.
Entries are sorted, owned by 0:0 and dated SOURCE_DATE_EPOCH (default 0), and gzip carries no
timestamp, so the same tree gives the same bytes.
"""

from __future__ import annotations

import gzip
import io
import os
import tarfile
from pathlib import Path

import typer

from declarative_iac.core.hashing import sha256_bytes
from declarative_iac.core.paths import relative, repository_root

app = typer.Typer(help="Build the results archive.", invoke_without_command=True)

INCLUDE = (
    "src",
    "paper",
    "results",
    "claims",
    "config",
    "evaluation",
    "docs/harness",
    "REPRODUCING.md",
    "CITATION.cff",
    "README.md",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
)
# Never archived: they hold canary secrets and system state of disposable instances.
EXCLUDE_PARTS = {"workspace", "home", "__pycache__", ".DS_Store"}


def members(root: Path) -> list[Path]:
    out: list[Path] = []
    for name in INCLUDE:
        path = root / name
        if path.is_file():
            out.append(path)
        elif path.is_dir():
            out += [
                p
                for p in path.rglob("*")
                if p.is_file()
                and not (EXCLUDE_PARTS & set(p.relative_to(root).parts))
                and not any(part.startswith("import-") for part in p.relative_to(root).parts)
            ]
    return sorted(out, key=lambda p: p.relative_to(root).as_posix())


def build(root: Path, target: Path, prefix: str) -> tuple[Path, int]:
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))
    files = members(root)
    sums = "".join(
        f"{sha256_bytes(p.read_bytes())}  {p.relative_to(root).as_posix()}\n" for p in files
    ).encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        entries = [(p.relative_to(root).as_posix(), p.read_bytes()) for p in files]
        entries.append(("SHA256SUMS", sums))
        for name, data in sorted(entries):
            info = tarfile.TarInfo(f"{prefix}/{name}")
            info.size = len(data)
            info.mtime = epoch
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    target.parent.mkdir(parents=True, exist_ok=True)
    with (
        target.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
    ):
        compressed.write(buffer.getvalue())
    return target, len(files)


@app.callback()
def archive(
    snapshot: str = typer.Option("B1", help="Snapshot label used in the archive name."),
) -> None:
    root = repository_root()
    name = f"declarative-iac-results-{snapshot}"
    target, count = build(root, root / "dist" / f"{name}.tar.gz", name)
    digest = sha256_bytes(target.read_bytes())
    (target.parent / f"{name}.tar.gz.sha256").write_text(f"{digest}  {target.name}\n")
    typer.echo(f"wrote    {relative(target)} ({count} files, sha256 {digest[:12]})")
