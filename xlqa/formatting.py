"""Chuẩn hóa đáp án cuối cùng theo yêu cầu định dạng nêu trong câu hỏi (Exact Match)."""

from __future__ import annotations

import datetime as dt
import math
import re

import numpy as np

WORD_NUM = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def decimals_required(query: str) -> int | None:
    q = query.lower()
    m = re.search(r"(\d+|zero|one|two|three|four|five|six)\s+decimal(?:\s+places?|s)?", q)
    if m:
        w = m.group(1)
        return int(w) if w.isdigit() else WORD_NUM[w]
    if re.search(r"(nearest|whole) (integer|number)|as an integer|only the integer|integer score|\bintegers?\b", q):
        return 0
    if "percentage point" in q and "decimal" not in q:
        return None
    return None


def _strip_footnote(s: str) -> str:
    s = re.sub(r"\s*\(\d+\)(\(\d+\))*", "", s)  # "Food away from home(1)" -> "Food away from home"
    s = re.sub(r"\s+\d+/$", "", s)  # "Trade balance 3/" -> "Trade balance"
    return s.strip()


def _fmt_scalar(v, query: str) -> str:
    if isinstance(v, np.generic):
        v = v.item()
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, (dt.datetime, dt.date)):
        if isinstance(v, dt.datetime) and v.time() == dt.time(0):
            return v.strftime("%Y-%m-%d")
        return v.isoformat() if not isinstance(v, dt.datetime) else v.strftime("%Y-%m-%d %H:%M:%S")
    if hasattr(v, "to_pydatetime"):
        return _fmt_scalar(v.to_pydatetime(), query)
    if isinstance(v, (int, float)):
        d = decimals_required(query)
        if d is None:
            if float(v).is_integer():
                return str(int(round(v)))
            return f"{round(v, 6):.6f}".rstrip("0").rstrip(".")
        if d == 0:
            return str(int(round(v + (1e-9 if v >= 0 else -1e-9))))
        return f"{v + (1e-12 if v >= 0 else -1e-12):.{d}f}"
    return format_text(str(v), query)


def format_text(s: str, query: str) -> str:
    s = s.strip().strip("`").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1].strip()
    s = re.sub(r"\s+", " ", s)
    if s.endswith(".") and not re.search(r"\d\.$", s):
        s = s[:-1].rstrip()
    q = query.lower()
    low = s.lower()
    if "yes or no" in q or "'yes' or 'no'" in q or re.search(r"\byes\b.*\bno\b", q):
        if low.startswith("yes"):
            return "Yes"
        if low.startswith("no"):
            return "No"
    # Số dạng chuỗi -> áp dụng định dạng số.
    t = s.replace(",", "") if re.fullmatch(r"-?[\d,]+(\.\d+)?", s) else s
    if re.fullmatch(r"-?\d+(\.\d+)?", t):
        return _fmt_scalar(float(t) if "." in t else int(t), query)
    if ", " in s and re.fullmatch(r"[-\d.,\s]+", s):  # "40.6, 37.6" -> định dạng từng số
        return ", ".join(format_text(p, query) for p in s.split(", "))
    return _strip_footnote(s)


def query_named_items(query: str) -> list[str]:
    """Các mục được liệt kê trong câu hỏi, vd "...: Agriculture, Manufacturing, and Construction."."""
    m = re.search(r":\s*([^:]+?)\.(?:\s|$)", query)
    if not m:
        return []
    parts = re.split(r",\s*(?:and\s+|or\s+)?|\s+and\s+|\s+or\s+", m.group(1))
    items = [p.strip().strip("'\"") for p in parts if p.strip()]
    return items if 2 <= len(items) <= 12 and all(len(i.split()) <= 6 for i in items) else []


def align_to_query_names(answer: str, query: str) -> str:
    """Nếu đáp án là danh sách nhãn trong bảng tương ứng các tên câu hỏi đã nêu, dùng đúng tên trong câu hỏi."""
    items = query_named_items(query)
    if not items or not answer:
        return answer
    out = []
    for part in answer.split(", "):
        p = part.lower()
        hits = [it for it in items if p == it.lower() or p.startswith(it.lower() + " ") or it.lower().startswith(p + " ")]
        out.append(hits[0] if len(hits) == 1 else part)
    return ", ".join(out)


def format_answer(value, query: str) -> str:
    return align_to_query_names(_format_answer(value, query), query)


def _format_answer(value, query: str) -> str:
    if isinstance(value, dict):
        value = list(value.values())
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        value = value.tolist()
    if isinstance(value, (list, tuple, set)):
        items = [format_answer(v, query) for v in value]
        return ", ".join(i for i in items if i != "")
    if isinstance(value, str):
        return format_text(value, query)
    return _fmt_scalar(value, query)
