"""`declarative-iac report`: regenerate tables, figures and results/SUMMARY.md from results/.

Generated files are never edited by hand; rerunning on the same results gives the same bytes
(figures: on the same platform and Matplotlib version).
"""

from __future__ import annotations

import typer

from declarative_iac.core.paths import paper_dir, relative, repository_root, results_dir
from declarative_iac.domain.report import figures, summary, tables

app = typer.Typer(
    help="Generate tables, figures and the results summary.", invoke_without_command=True
)


@app.callback()
def report(
    figures_too: bool = typer.Option(True, "--figures/--no-figures", help="Also draw figures."),
) -> None:
    written, missing = tables.write_tables(paper_dir() / "tables")
    for path in written:
        typer.echo(f"wrote    {relative(path)}")
    for item in missing:
        typer.echo(f"missing  {item}")
    if figures_too:
        for path in figures.write_figures(paper_dir() / "figures"):
            typer.echo(f"wrote    {relative(path)}")
        if not figures.tex_available():
            typer.echo("note     xelatex not found: PGF figures skipped, PNG written")
    target = results_dir() / "SUMMARY.md"
    target.write_text(summary.build(repository_root() / "claims" / "claims.yaml"))
    typer.echo(f"wrote    {relative(target)}")
