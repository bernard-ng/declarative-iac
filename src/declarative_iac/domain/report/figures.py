"""Figures generated from results, in the drc-names-corpus style (scienceplots, PNG + PGF).

PNG output is byte-identical across reruns on one platform and Matplotlib version (no software
or date metadata). PGF output needs XeLaTeX for text metrics; without it only PNG is written and
the report says so.
"""

from __future__ import annotations

import shutil
import statistics
from collections.abc import Callable
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import scienceplots  # noqa: E402, F401
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from declarative_iac.domain.report.sources import Source, header  # noqa: E402
from declarative_iac.domain.static.classes import CLASSES  # noqa: E402

SIZES = (8, 7, 6)  # base (labels), annotation/legend, ticks
FOCAL = "#1f4e79"  # one hue for presence marks
MUTED = "#d9d9d9"
# Okabe-Ito, colour-blind safe, one colour per mutability, used identically everywhere.
MUTABILITY = {
    "in_place": "#0072B2",
    "write_only": "#E69F00",
    "create_only": "#009E73",
    "computed": "#999999",
}
DOUBLE_COLUMN = 7.0  # inches


def style() -> None:
    plt.style.use(["science", "no-latex", "grid"])
    base, small, tick = SIZES
    matplotlib.rcParams.update(
        {
            "font.size": base,
            "axes.labelsize": base,
            "axes.titlesize": base,
            "legend.fontsize": small,
            "xtick.labelsize": tick,
            "ytick.labelsize": tick,
            "savefig.facecolor": "white",
            "pgf.texsystem": "xelatex",
            "pgf.rcfonts": False,
            "svg.hashsalt": "declarative-iac",
            "path.simplify": False,
        }
    )


def tex_available() -> bool:
    return shutil.which("xelatex") is not None


def save(fig: Figure, directory: Path, name: str, sources: list[Source]) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    png = directory / f"{name}.png"
    fig.savefig(png, dpi=300, bbox_inches="tight", metadata={"Software": None})
    written = [png]
    if tex_available():
        pgf = directory / f"{name}.pgf"
        fig.savefig(pgf, backend="pgf", bbox_inches="tight")
        text = pgf.read_text()
        pgf.write_text(header(sources, "%% {}") + "\n" + text)
        written.append(pgf)
    (directory / f"{name}.source.txt").write_text(header(sources, "{}") + "\n")
    written.append(directory / f"{name}.source.txt")
    plt.close(fig)
    return written


def obstacles_by_kind(directory: Path) -> list[Path]:
    """Which mismatch classes each kind meets (Section 3): kinds x classes, by scope."""

    source = Source.static("S2-specifications")
    kinds = source.csv("kinds.csv")
    ids = [c.id for c in CLASSES]
    by_scope = {
        scope: sorted(
            (k for k in kinds if k["scope"] == scope),
            key=lambda k: (-len([c for c in k["classes"].split(";") if c]), k["kind"]),
        )
        for scope in ("project", "settings")
    }
    ordered = by_scope["project"] + by_scope["settings"]
    gap = 1.0
    positions = [i + (gap if i >= len(by_scope["project"]) else 0) for i in range(len(ordered))]
    fig, ax = plt.subplots(figsize=(DOUBLE_COLUMN, 2.9))
    for x, kind in zip(positions, ordered, strict=True):
        present = set(filter(None, kind["classes"].split(";")))
        for y, cid in enumerate(ids):
            ax.scatter(
                x,
                y,
                s=22,
                marker="s",
                linewidths=0,
                color=FOCAL if cid in present else MUTED,
                zorder=3,
            )
    totals = {cid: sum(cid in k["classes"].split(";") for k in ordered) for cid in ids}
    ax.set_yticks(range(len(ids)), [f"{cid} ({totals[cid]})" for cid in ids])
    ax.set_xticks(positions, [k["kind"].replace("_", " ") for k in ordered], rotation=90)
    ax.invert_yaxis()
    ax.grid(False)
    ax.minorticks_off()
    ax.tick_params(which="both", length=0, top=False, right=False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xlim(min(positions) - 0.8, max(positions) + 0.8)
    ax.set_ylim(len(ids) - 0.4, -1.9)
    split = len(by_scope["project"])
    for label, xs in (("project kinds", positions[:split]), ("settings kinds", positions[split:])):
        ax.annotate(
            label, xy=((xs[0] + xs[-1]) / 2, -1.25), ha="center", va="center", fontsize=SIZES[1]
        )
        ax.plot([xs[0] - 0.3, xs[-1] + 0.3], [-0.85, -0.85], color="black", linewidth=0.6)
    top = max(ids, key=lambda cid: totals[cid])
    titles = source.json("classes.json")
    clear = [k["kind"] for k in ordered if not any(k["classes"].split(";"))]
    ax.set_title(
        f"{titles[top]['title']} ({top}) affect {totals[top]} of {len(ordered)} kinds; "
        f"{len(ordered) - len(clear)} kinds meet at least one class",
        loc="left",
    )
    ax.set_ylabel("Mismatch class (kinds)")
    return save(fig, directory, "obstacles-by-kind", [source])


def fields_per_kind(directory: Path) -> list[Path]:
    """Field declarations per kind, by mutability (Section 5)."""

    source = Source.static("S2-specifications")
    fields = source.csv("fields.csv")
    kinds = {k["kind"]: k for k in source.csv("kinds.csv")}
    counts: dict[str, dict[str, int]] = {}
    for row in fields:
        counts.setdefault(row["kind"], dict.fromkeys(MUTABILITY, 0))[row["mutability"]] += 1
    order = sorted(counts, key=lambda k: (sum(counts[k].values()), k))
    scopes = ("project", "settings")
    fig, axes = plt.subplots(
        1,
        2,
        figsize=(DOUBLE_COLUMN, 3.6),
        sharex=True,
        gridspec_kw={"wspace": 0.55},
    )
    for ax, scope in zip(axes, scopes, strict=True):
        names = [k for k in order if kinds[k]["scope"] == scope]
        left = [0] * len(names)
        for mutability, colour in MUTABILITY.items():
            values = [counts[k][mutability] for k in names]
            ax.barh(
                range(len(names)),
                values,
                left=left,
                color=colour,
                height=0.72,
                linewidth=0,
                zorder=3,
            )
            left = [a + b for a, b in zip(left, values, strict=True)]
        ax.set_yticks(range(len(names)), [n.replace("_", " ") for n in names])
        ax.set_title(f"{scope.capitalize()} kinds ({len(names)})", loc="left")
        ax.set_xlabel("Field declarations")
        ax.grid(axis="y", visible=False)
        ax.tick_params(axis="y", which="both", length=0)
        ax.set_ylim(-0.6, len(names) - 0.4)
        widest = max(range(len(names)), key=lambda i: left[i])
        ax.annotate(
            str(left[widest]),
            xy=(left[widest], widest),
            xytext=(3, 0),
            textcoords="offset points",
            va="center",
            fontsize=SIZES[1],
        )
    axes[0].set_xlim(0, max(sum(c.values()) for c in counts.values()) * 1.12)
    handles = [Patch(color=c, label=m.replace("_", "-")) for m, c in MUTABILITY.items()]
    axes[1].legend(
        handles=handles,
        loc="lower right",
        frameon=False,
        title="Mutability",
        title_fontsize=SIZES[1],
    )
    totals = {k: sum(c.values()) for k, c in counts.items()}
    largest = max(totals, key=lambda k: totals[k])
    median = statistics.median(totals.values())
    fig.suptitle(
        f"{largest.replace('_', ' ').capitalize()} declares {totals[largest]} of "
        f"{sum(totals.values())} fields; the median kind declares {median:g}",
        x=0.0,
        ha="left",
        fontsize=SIZES[0],
        y=0.99,
    )
    return save(fig, directory, "fields-per-kind", [source])


FIGURES: dict[str, Callable[[Path], list[Path]]] = {
    "obstacles-by-kind": obstacles_by_kind,
    "fields-per-kind": fields_per_kind,
}


def write_figures(directory: Path) -> list[Path]:
    style()
    written: list[Path] = []
    for build in FIGURES.values():
        written += build(directory)
    return written
