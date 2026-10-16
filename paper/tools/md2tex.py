"""One-off migration of paper/sections/*.md to LaTeX (paper/sections/*.tex).

Usage: python tools/md2tex.py            (from paper/; needs pandoc >= 3)

A pre-pass on the Markdown turns DOI links into natbib citations (\\citet outside parentheses,
\\citealp inside, merged into \\citep when a parenthesis holds only citations), "Section N" and
"Table N" into \\ref, numbered headings into labelled sections, "**Table N.**" captions into
pandoc table captions and "[RESULT: ...]" and "[TODO: ...]" into
\\result{...} and \\draftnote{...}. tools/latex.lua then writes the
tables (booktabs, tabularx), code (lstlisting) and placeholders, and a post-pass replaces the
remaining non-ASCII symbols. Code spans and blocks are never rewritten.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAPER = HERE.parent
SECTIONS = PAPER / "sections"
NUM = r"\d+(?:\.\d+)*"

records = json.loads((HERE / "bib-records.json").read_text())
text_keys = json.loads((HERE / "cite-keys.json").read_text())
url_keys: dict[str, str] = {}
for doi, rec in records.items():
    for t in rec["texts"]:
        url_keys["https://doi.org/" + doi.lower()] = text_keys[t]
url_keys["https://www.usenix.org/conference/osdi22/presentation/sun"] = text_keys["Sun et al. 2022"]

SYMBOLS = {"→": r"\ensuremath{\rightarrow}", "←": r"\ensuremath{\leftarrow}",
           "∪": r"\ensuremath{\cup}", "≠": r"\ensuremath{\neq}", "∈": r"\ensuremath{\in}",
           "∉": r"\ensuremath{\notin}", "×": r"\ensuremath{\times}", "≤": r"\ensuremath{\leq}",
           "≥": r"\ensuremath{\geq}", "–": "--", "—": "---", "ü": r"\"u", "í": r"\'i",
           "⌈": r"\ensuremath{\lceil}", "⌉": r"\ensuremath{\rceil}", "…": r"\ldots{}"}

warnings: list[str] = []


def labels() -> set[str]:
    found = set()
    for path in SECTIONS.glob("*.md"):
        text = path.read_text()
        found |= {"sec:" + m for m in re.findall(rf"^#+ ({NUM}) ", text, re.M)}
        found |= {"tab:" + m for m in re.findall(r"^\*\*Table (\d+)\.\*\*", text, re.M)}
    return found


LABELS = labels()

CODE = re.compile(r"```.*?```|``[^`]+?``|`[^`\n]+?`", re.S)


def protect(text: str) -> tuple[str, list[str]]:
    saved: list[str] = []

    def keep(m: re.Match[str]) -> str:
        saved.append(m.group(0))
        return f"\x00{len(saved) - 1}\x00"

    return CODE.sub(keep, text), saved


def restore(text: str, saved: list[str]) -> str:
    return re.sub(r"\x00(\d+)\x00", lambda m: saved[int(m.group(1))], text)


def headings(text: str, name: str) -> str:
    if name.startswith("00-"):
        return re.sub(r"^# Abstract\n+", "", text)
    text = re.sub(rf"^(#+) ({NUM}) (.+)$", r"\1 \3 {#sec:\2}", text, flags=re.M)
    return re.sub(r"^(#+) ([^\d\n{][^\n{]*)$", r"\1 \2 {.unnumbered}", text, flags=re.M)


def captions(text: str) -> str:
    return re.sub(r"^\*\*Table (\d+)\.\*\* (.+?)(?=\n\n)", r"Table: \2 TABLABEL\1TABLABEL",
                  text, flags=re.M | re.S)


def results(text: str) -> str:
    text = re.sub(r"\[TODO:\s*(.*?)\]", lambda m: f"[{m.group(1)}]{{.todo}}", text, flags=re.S)
    return re.sub(r"\[RESULT(?::\s*(.*?))?\]", lambda m: f"[{m.group(1) or ''}]{{.result}}",
                  text, flags=re.S)


LINK = re.compile(r"\[([^\]]+)\]\((\S+?)\)")


def citations(text: str) -> str:
    out = []
    for para in re.split(r"(\n\s*\n)", text):
        pieces, pos = [], 0
        for m in LINK.finditer(para):
            key = url_keys.get(m.group(2).lower() if "doi.org" in m.group(2) else m.group(2))
            if key is None:
                continue
            before = LINK.sub("", para[:m.start()])
            depth = before.count("(") - before.count(")")
            pieces += [para[pos:m.start()], (r"\citealp{%s}" if depth > 0 else r"\citet{%s}") % key]
            pos = m.end()
        para = "".join(pieces) + para[pos:]
        if para.lstrip().startswith("|"):  # Table 1 names works in plain text
            para = re.sub(r"Song et al\. 2010a, 2010b", r"\\citealp{song2010a,song2010b}", para)
            for t, key in sorted(text_keys.items(), key=lambda kv: -len(kv[0])):
                para = para.replace(t, r"\citealp{%s}" % key)
        group = r"\\citealp\{[^}]+\}(?:;\s*\\citealp\{[^}]+\})*"
        para = re.sub(rf"\((e\.g\.,?\s+)?({group})\)", lambda m: (
            (r"\citep[%s][]{%s}" % (m.group(1).strip(), ",".join(re.findall(r"\{([^}]+)\}", m.group(2)))))
            if m.group(1) else r"\citep{%s}" % ",".join(re.findall(r"\{([^}]+)\}", m.group(2)))), para)
        out.append(para)
    return "".join(out)


def references(text: str) -> str:
    sep = r"(?:,\s+and\s+|,\s*|\s+and\s+|\s*–\s*|\s+to\s+)"

    def ref(m: re.Match[str]) -> str:
        word, rest = m.group(1), m.group(0)[len(m.group(1)):]
        prefix = "sec:" if word.startswith("Section") else "tab:"
        parts = re.split(rf"({sep})", rest.strip())
        nums = parts[0::2]
        if any(prefix + n not in LABELS for n in nums):
            warnings.append(f"unresolved {m.group(0)!r}")
            return m.group(0)
        built = word + "\u00a0\\ref{" + prefix + nums[0] + "}"
        for s, n in zip(parts[1::2], nums[1:]):
            built += ("--" if "–" in s else s.rstrip() + "\u00a0") + "\\ref{" + prefix + n + "}"
        return built

    return re.sub(rf"\b(Sections?|Tables?)\s+{NUM}(?:{sep}{NUM}(?![\w-]))*(?![\w-])", ref, text)


def convert(path: Path) -> str:
    text, saved = protect(path.read_text())
    text = headings(text, path.name)
    text = captions(text)
    text = results(text)
    text = citations(text)
    text = references(text)
    text = restore(text, saved)
    run = subprocess.run(
        ["pandoc", "-f", "markdown+raw_tex-auto_identifiers-implicit_figures", "-t", "latex",
         "--wrap=preserve", "--lua-filter", str(HERE / "latex.lua")],
        input=text, capture_output=True, text=True)
    if run.returncode:
        sys.exit(f"pandoc failed on {path.name}:\n{run.stderr}")
    tex = run.stdout
    tex = re.sub(r"TABLABEL(\d+)TABLABEL", "", tex)  # stray markers, if any
    tex = re.sub(r"^\\tightlist\n", "", tex, flags=re.M)
    chunks = re.split(r"(\\begin\{lstlisting\}.*?\\end\{lstlisting\})", tex, flags=re.S)
    for i in range(0, len(chunks), 2):
        for symbol, replacement in SYMBOLS.items():
            chunks[i] = chunks[i].replace(symbol, replacement)
    tex = "".join(chunks)
    left = sorted({c for c in re.sub(r"\\begin\{lstlisting\}.*?\\end\{lstlisting\}", "", tex, flags=re.S) if ord(c) > 127})
    if left:
        warnings.append(f"{path.name}: non-ASCII left {left}")
    for m in re.finditer(r"\b[A-Z][a-z]+(?: et al\.| & [A-Z][a-z]+) \d{4}", re.sub(r"\\cite\w*(\[[^]]*\])*\{[^}]*\}", "", tex)):
        warnings.append(f"{path.name}: uncited {m.group(0)!r}")
    header = f"% Converted from sections/{path.name} by tools/md2tex.py; edit this file from now on.\n"
    return header + tex


if __name__ == "__main__":
    for path in sorted(SECTIONS.glob("*.md")):
        (SECTIONS / (path.stem + ".tex")).write_text(convert(path))
    print("\n".join(warnings) or "no warnings", file=sys.stderr)
