"""Hiển thị bảng / workbook thành text gọn cho LLM."""

from __future__ import annotations

from .excel_reader import WorkbookData
from .table_detector import Table
from .values import fmt_value


def render_table(t: Table, max_rows: int | None = None) -> str:
    lines = [f"### Table {t.name} (sheet '{t.sheet}')"]
    if t.title:
        lines.append("Title: " + " / ".join(t.title))
    lines.append("Columns:")
    for c, desc in t.columns.items():
        tag = " (row label)" if c == t.label_col else ""
        lines.append(f"  {c}: {desc or '(no header)'}{tag}")
    cols = list(t.columns)
    label_i = cols.index(t.label_col)
    lines.append("Rows (excel_row | " + " | ".join(cols) + "):")
    items = list(t.rows.items())
    if max_rows is not None and len(items) > max_rows:
        head = max_rows - 5
        items = items[:head] + [None] + items[-5:]
    for item in items:
        if item is None:
            lines.append(f"... ({len(t.rows) - max_rows} rows omitted) ...")
            continue
        r, vals = item
        cells = [fmt_value(v) for v in vals]
        if t.indents.get(r):
            cells[label_i] = "  " * t.indents[r] + cells[label_i]
        while cells and cells[-1] == "":
            cells.pop()
        lines.append(f"{r} | " + " | ".join(cells))
    if t.notes:
        lines.append("Notes: " + " ".join(t.notes))
    return "\n".join(lines)


def render_tables(tables: list[Table], max_rows: int | None = None) -> str:
    return "\n\n".join(render_table(t, max_rows) for t in tables)


def render_overview(wb: WorkbookData, tables: list[Table], preview_rows: int = 5) -> str:
    """Tóm tắt workbook cho agent: sheet, kích thước, các bảng đoán được, vài dòng đầu, cảnh báo."""
    lines = []
    for name, sd in wb.sheets.items():
        lines.append(f"Sheet '{name}': range {sd.dimensions}, {len(sd.merges)} merged ranges"
                     + (f", hidden rows {sorted(sd.hidden_rows)[:10]}" if sd.hidden_rows else ""))
        for t in [t for t in tables if t.sheet == name]:
            first, last = (min(t.rows), max(t.rows)) if t.rows else (None, None)
            lines.append(f"  Guessed table table('{t.name}'): data rows {first}-{last} ({len(t.rows)} rows), "
                         f"header rows {t.header_rows or 'none'}"
                         + (f", title: {' / '.join(t.title)[:150]}" if t.title else ""))
            for c, d in t.columns.items():
                lines.append(f"    {c}: {(d or '(no header)')[:120]}{' (row label)' if c == t.label_col else ''}")
            labels = [fmt_value(v[list(t.columns).index(t.label_col)]) for v in list(t.rows.values())[:preview_rows]]
            lines.append(f"    first row labels: {labels}")
            for w in t.warnings:
                lines.append(f"    WARNING: {w}")
    return "\n".join(lines)
