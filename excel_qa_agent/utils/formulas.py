"""Tính các công thức Excel đơn giản khi file không lưu sẵn giá trị (cached value)."""

from __future__ import annotations

import re

from openpyxl.utils import column_index_from_string, get_column_letter

from .values import is_num, to_value

_SHEET = r"(?:'([^']+)'!|([A-Za-z0-9_.]+)!)?"
RANGE_RE = re.compile(_SHEET + r"\$?([A-Z]{1,3})\$?(\d+):\$?([A-Z]{1,3})\$?(\d+)")
REF_RE = re.compile(_SHEET + r"\$?([A-Z]{1,3})\$?(\d+)(?![\d(])")
CALL_RE = re.compile(r"([A-Za-z_]\w*)\(")


def _flat(args) -> list:
    out: list = []
    for a in args:
        out.extend(_flat(a) if isinstance(a, (list, tuple)) else [a])
    return [x for x in out if is_num(x)]


FUNCS = {
    "SUM": lambda *a: sum(_flat(a)),
    "AVERAGE": lambda *a: sum(_flat(a)) / max(1, len(_flat(a))),
    "MIN": lambda *a: min(_flat(a)),
    "MAX": lambda *a: max(_flat(a)),
    "COUNT": lambda *a: len(_flat(a)),
    "ABS": abs,
    "ROUND": lambda x, n=0: round(x, int(n)),
}


def _cell(wb_values, wb_formulas, sheet: str, coord: str, depth: int):
    v = wb_values[sheet][coord].value
    if v is None:
        f = wb_formulas[sheet][coord].value
        if isinstance(f, str) and f.startswith("="):
            v = eval_formula(f, wb_values, wb_formulas, sheet, depth + 1)
    return to_value(v)


def eval_formula(formula: str, wb_values, wb_formulas, sheet: str, depth: int = 0):
    """Hỗ trợ: tham chiếu ô/vùng (kể cả sheet khác), + - * / ^, SUM/AVERAGE/MIN/MAX/COUNT/ABS/ROUND.

    Trả về None với công thức không hỗ trợ (để không đưa giá trị sai vào bảng).
    """
    if depth > 30:
        return None
    env: dict = {"__builtins__": {}, **FUNCS}

    def put(val) -> str:
        name = f"_v{len(env)}"
        env[name] = val
        return name

    def rng(m: re.Match) -> str:
        sh = m.group(1) or m.group(2) or sheet
        c1, r1, c2, r2 = m.group(3), int(m.group(4)), m.group(5), int(m.group(6))
        vals = [
            _cell(wb_values, wb_formulas, sh, f"{get_column_letter(c)}{r}", depth)
            for r in range(r1, r2 + 1)
            for c in range(column_index_from_string(c1), column_index_from_string(c2) + 1)
        ]
        return put(vals)

    def ref(m: re.Match) -> str:
        v = _cell(wb_values, wb_formulas, m.group(1) or m.group(2) or sheet, f"{m.group(3)}{m.group(4)}", depth)
        return put(0 if v is None else v)

    try:
        expr = RANGE_RE.sub(rng, formula.lstrip("="))
        expr = REF_RE.sub(ref, expr).replace("^", "**")
        if any(name not in FUNCS for name in CALL_RE.findall(expr)):
            return None
        val = eval(expr, env)  # noqa: S307 - biểu thức chỉ gồm số, toán tử và hàm trong FUNCS
        return to_value(val) if is_num(val) else None
    except Exception:  # noqa: BLE001
        return None
