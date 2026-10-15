"""The `declarative-iac` command line."""

from __future__ import annotations

import logging

import typer

from declarative_iac.workflow import (
    archive,
    claims,
    developer,
    live,
    provenance,
    report,
    reproduce,
    static,
)

app = typer.Typer(
    help="Reproduce and check every result of the dokploy-iac technical report.",
    no_args_is_help=True,
)
app.add_typer(provenance.app, name="provenance")
app.add_typer(static.app, name="static")
app.add_typer(claims.app, name="claims")
app.add_typer(developer.app, name="developer")
app.add_typer(live.app, name="live")
app.add_typer(report.app, name="report")
app.add_typer(reproduce.app, name="reproduce")
app.add_typer(archive.app, name="archive")


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
