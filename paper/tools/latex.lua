-- Pandoc filter for md2tex.py: booktabs/tabularx tables, lstlisting code, \result placeholders.

local function latex(blocks)
  return (pandoc.write(pandoc.Pandoc(blocks), "latex"):gsub("%s+$", ""))
end

local function cell_text(cell)
  local s = latex(cell.contents)
  return (s:gsub("\n", " "))
end

function Table(tbl)
  local caption, label = "", nil
  local cap = tbl.caption.long
  if #cap > 0 then
    local text = latex(cap)
    local n = text:match("TABLABEL(%d+)TABLABEL")
    if n then label = "tab:" .. n end
    caption = (text:gsub("%s*TABLABEL%d+TABLABEL%s*", "", 1))
  end
  local widths, aligns = {}, {}
  local rows = {}
  local function collect(r) table.insert(rows, r) end
  for _, r in ipairs(tbl.head.rows) do collect(r) end
  for _, body in ipairs(tbl.bodies) do for _, r in ipairs(body.body) do collect(r) end end
  for i, spec in ipairs(tbl.colspecs) do
    aligns[i] = spec[1]
    local longest = 0
    for _, r in ipairs(rows) do
      local c = r.cells[i]
      if c then longest = math.max(longest, #pandoc.utils.stringify(c.contents)) end
    end
    widths[i] = longest
  end
  local cols, any_x = {}, false
  for i, w in ipairs(widths) do
    if w > 28 then cols[i] = "L"; any_x = true
    elseif aligns[i] == "AlignRight" then cols[i] = "r"
    elseif aligns[i] == "AlignCenter" then cols[i] = "c"
    else cols[i] = "l" end
  end
  local spec = table.concat(cols)
  local floating = caption ~= ""
  local out = floating and {"\\begin{table}[tbp]", "\\centering", "\\small"}
    or {"\\begin{center}", "\\small"}
  if floating then table.insert(out, "\\caption{" .. caption .. "}") end
  if label then table.insert(out, "\\label{" .. label .. "}") end
  if any_x then
    table.insert(out, "\\begin{tabularx}{\\linewidth}{" .. spec .. "}")
  else
    table.insert(out, "\\begin{tabular}{" .. spec .. "}")
  end
  table.insert(out, "\\toprule")
  local function emit(r)
    local cells = {}
    for _, c in ipairs(r.cells) do table.insert(cells, cell_text(c)) end
    table.insert(out, table.concat(cells, " & ") .. " \\\\")
  end
  for _, r in ipairs(tbl.head.rows) do emit(r) end
  table.insert(out, "\\midrule")
  for _, body in ipairs(tbl.bodies) do for _, r in ipairs(body.body) do emit(r) end end
  table.insert(out, "\\bottomrule")
  table.insert(out, any_x and "\\end{tabularx}" or "\\end{tabular}")
  table.insert(out, floating and "\\end{table}" or "\\end{center}")
  return pandoc.RawBlock("latex", table.concat(out, "\n"))
end

function CodeBlock(block)
  return pandoc.RawBlock("latex", "\\begin{lstlisting}\n" .. block.text .. "\n\\end{lstlisting}")
end

function Span(span)
  for class, macro in pairs({result = "result", todo = "draftnote"}) do
    if span.classes:includes(class) then
      local inner = pandoc.write(pandoc.Pandoc({pandoc.Plain(span.content)}), "latex"):gsub("%s+$", "")
      return pandoc.RawInline("latex", "\\" .. macro .. "{" .. inner .. "}")
    end
  end
end
