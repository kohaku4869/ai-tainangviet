"""Đoán các bảng trong một sheet: tiêu đề -> header (nhiều tầng) -> dữ liệu -> chú thích.

Đây chỉ là *gợi ý* cấu trúc. Mỗi bảng mang danh sách `warnings` khi cấu trúc bất thường để router
quyết định chuyển sang agent (agent tự khám phá lưới thô thay vì tin vào phần đoán này).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .excel_reader import SheetData
from .values import fmt_value, is_date, is_num


@dataclass
class Table:
    sheet: str
    index: int
    title: list[str]
    columns: dict[str, str]  # chữ cái cột -> header đã làm phẳng ("2023 > Total")
    label_col: str
    df: pd.DataFrame  # index = số dòng Excel, columns = chữ cái cột
    rows: dict[int, list]  # giá trị gốc theo dòng (để hiển thị)
    header_rows: list[int] = field(default_factory=list)
    indents: dict[int, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return f"{self.sheet}#{self.index}"


def _year_only(vals) -> bool:
    nums = [v for v in vals if v is not None]
    return bool(nums) and all(isinstance(v, int) and 1900 <= v <= 2100 for v in nums)


def detect_tables(sd: SheetData) -> list[Table]:
    grid, r0 = sd.grid, sd.min_row
    n, ncols = sd.n_rows, sd.n_cols
    letters = [sd.letter(j) for j in range(ncols)]

    def nonempty(k: int) -> list[int]:
        return [j for j, v in enumerate(grid[k]) if v is not None]

    def is_data(k: int) -> bool:
        row = grid[k]
        rest = row[1:]
        has_values = any(is_num(v) or is_date(v) for v in rest)
        header_years = k < 10 and _year_only(rest) and not is_num(row[0])
        return row[0] is not None and has_values and not header_years

    def header_like(k: int) -> bool:
        ne = nonempty(k)
        return len(ne) >= 2 and all(isinstance(grid[k][j], str) for j in ne)

    def next_nonempty(k: int) -> int | None:
        k += 1
        while k < n and not nonempty(k):
            k += 1
        return k if k < n else None

    def starts_new_table(k: int) -> bool:
        """Bảng xếp chồng: sau dòng trống là (tiêu đề một ô ->) dòng header toàn chữ, rồi tới dữ liệu."""
        if k == 0 or nonempty(k - 1):
            return False
        if nonempty(k) == [0]:
            nk = next_nonempty(k)
            return nk is not None and header_like(nk)
        if header_like(k):
            nk = next_nonempty(k)
            return nk is not None and is_data(nk)
        return False

    tables: list[Table] = []
    pending_title: list[str] = []
    i = 0
    while i < n:
        header_rows: list[int] = []
        while i < n and not is_data(i):
            ne = nonempty(i)
            if ne == [0] and not header_rows:
                pending_title.append(str(grid[i][0]))
            elif ne:
                header_rows.append(i)
            i += 1
        if i >= n:
            break

        data_rows: list[int] = []
        # Dòng nhóm (chỉ có nhãn, vd "TOTAL") nằm ngay trước dữ liệu thuộc về dữ liệu, không phải header.
        while len(header_rows) > 1 and nonempty(header_rows[-1]) == [0]:
            data_rows.insert(0, header_rows.pop())
        while i < n:
            ne = nonempty(i)
            if ne and grid[i][0] is None:  # header mới bắt đầu ở giữa vùng dữ liệu
                break
            if data_rows and starts_new_table(i):
                break
            data_rows.append(i)
            i += 1

        last_data = max((k for k in data_rows if is_data(k)), default=None)
        notes: list[str] = []
        if last_data is not None:
            tail = [k for k in data_rows if k > last_data]
            data_rows = [k for k in data_rows if k <= last_data]
            notes = [str(grid[k][0]) for k in tail if grid[k][0] is not None]
        if not data_rows:
            continue

        used = [j for j in range(ncols) if any(grid[k][j] is not None for k in data_rows)]
        columns: dict[str, str] = {}
        for j in used:
            parts: list[str] = []
            for h in header_rows:
                v = grid[h][j]
                if v is not None and (not parts or parts[-1] != fmt_value(v)):
                    parts.append(fmt_value(v))
            columns[letters[j]] = " > ".join(parts)

        label_col = letters[used[0]]
        for j in used:
            if sum(isinstance(grid[k][j], str) for k in data_rows) > len(data_rows) / 2:
                label_col = letters[j]
                break

        rows = {r0 + k: [grid[k][j] for j in used] for k in data_rows if any(grid[k][j] is not None for j in used)}
        df = pd.DataFrame(list(rows.values()), index=list(rows), columns=[letters[j] for j in used], dtype=object)
        for c in df.columns:
            vals = df[c].dropna()
            if len(vals) and all(is_num(v) for v in vals):
                df[c] = pd.to_numeric(df[c])
            elif len(vals) and all(is_date(v) for v in vals):
                df[c] = pd.to_datetime(df[c])
        df.index.name = "excel_row"

        label_j = letters.index(label_col)
        indents = {r0 + k: sd.indents[(r0 + k, sd.min_col + label_j)]
                   for k in data_rows if (r0 + k, sd.min_col + label_j) in sd.indents}

        warnings: list[str] = []
        if not header_rows:
            warnings.append("no header rows detected")
        unnamed = [c for c, d in columns.items() if not d and c != label_col]
        if unnamed and len(unnamed) / max(1, len(columns)) > 0.25:
            warnings.append(f"columns without header: {', '.join(unnamed)}")
        gaps = [letters[j] for j in range(used[0], used[-1] + 1) if j not in used]
        if gaps:
            warnings.append(f"empty column(s) {', '.join(gaps)} inside the table: may be side-by-side tables")
        if any(sd.min_row + k in sd.hidden_rows for k in data_rows):
            warnings.append("contains hidden rows")

        tables.append(Table(
            sheet=sd.name, index=len(tables) + 1, title=pending_title, columns=columns, label_col=label_col,
            df=df, rows=rows, header_rows=[r0 + h for h in header_rows], indents=indents, notes=notes,
            warnings=warnings,
        ))
        pending_title = []
    return tables
