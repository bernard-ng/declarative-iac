# Paper

The manuscript is LaTeX. `main.tex` builds a draft with the standard `article` class:

```
main.tex            draft build: front matter and one \input per section
macros.tex          packages and macros the sections need (\result, \draftnote, the L column type)
sections/NN-*.tex   one file per section; these are the source from now on
references.bib      54 references, built by tools/build_bib.py from Crossref and DataCite records
figures/            PNG figures written by `declarative-iac report`
tables/             tables written by `declarative-iac report` (Markdown, not yet in the sections)
tools/              the one-off Markdown-to-LaTeX migration (md2tex.py, latex.lua, build_bib.py)
```

**Overleaf.** Import the repository and set `paper/main.tex` as the main document (pdfLaTeX,
BibTeX). To move to a journal template, take the template's class and front matter, add
`\input{macros}` to its preamble (dropping packages the class already loads), keep the
`\input{sections/...}` lines and `\bibliography{references}`, and swap `plainnat` for the
journal's bibliography style. Tables use `table` with `\linewidth`; in a two-column class, change
the wide ones to `table*`.

**Placeholders.** `\result{...}` (red) marks values the confirmatory live runs will supply;
`\draftnote{...}` (blue) marks open items, such as the two vendor-documentation citations.

**Sections in Markdown.** `sections/*.md` are the versions before the move to LaTeX; they are no
longer edited. The claims check (`declarative-iac claims check-paper`) still reads them until it is
switched to the `.tex` files; all 219 claim fragments are present in the LaTeX as converted.

Use the local skill `science-research-writing` for drafting, and run `paper-consistency-audit` on the
full draft before submission.
