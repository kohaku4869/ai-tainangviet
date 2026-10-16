"""Chuẩn hóa đáp án cuối cùng theo yêu cầu định dạng *ghi trong câu hỏi* (phục vụ Exact Match).

Chỉ dựa vào chữ trong câu hỏi (integer / N decimal places / Yes or No / danh sách), không có quy ước riêng của bộ dữ liệu.
"""

from __future__ import annotations

import datetime as dt
import math
import re

WORD_NUM = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def decimals_required(query: str) -> int | None:
    q = query.lower()
    m = re.search(r"(\d+|zero|one|two|three|four|five|six)\s+decimal(?:\s+places?|s)?", q)
    if m:
        w = m.group(1)
        return int(w) if w.isdigit() else WORD_NUM[w]
    if re.search(r"(nearest|whole) (integer|number)|as an integer|\bintegers?\b", q):
        return 0
    return None


def wants_yes_no(query: str) -> bool:
    return bool(re.search(r"\byes\b[^.?]{0,15}\bno\b", query.lower()))


def strip_footnote(s: str) -> str:
    """Bỏ ký hiệu chú thích của bảng thống kê: "Food(1)" -> "Food", "Trade balance 3/" -> "Trade balance"."""
    s = re.sub(r"\s*\(\d+\)(\(\d+\))*", "", s)
    s = re.sub(r"\s+\d+/$", "", s)
    return s.strip()


def _fmt_number(v: float | int, query: str) -> str:
    d = decimals_required(query)
    if d is None:
        if float(v).is_integer():
            return str(int(round(v)))
        return f"{round(v, 6):.6f}".rstrip("0").rstrip(".")
    eps = 1e-9 if v >= 0 else -1e-9  # tránh lỗi làm tròn kiểu 2.675 -> 2.67
    if d == 0:
        return str(int(round(v + eps)))
    return f"{v + eps:.{d}f}"


def _fmt_scalar(v, query: str) -> str:
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            v = v.item()
        except (ValueError, AttributeError):
            pass
    if hasattr(v, "to_pydatetime"):
        v = v.to_pydatetime()
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, dt.datetime):
        return v.strftime("%Y-%m-%d") if v.time() == dt.time(0) else v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, (int, float)):
        return _fmt_number(v, query)
    return format_text(str(v), query)


def format_text(s: str, query: str) -> str:
    s = re.sub(r"\s+", " ", s.strip().strip("`").strip())
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1].strip()
    if s.endswith(".") and not re.search(r"\d\.$", s):
        s = s[:-1].rstrip()
    if wants_yes_no(query):
        low = s.lower()
        if low.startswith("yes"):
            return "Yes"
        if low.startswith("no"):
            return "No"
    plain = s.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", s) else s
    if re.fullmatch(r"-?\d+(\.\d+)?", plain):
        return _fmt_number(float(plain) if "." in plain else int(plain), query)
    if ", " in s and re.fullmatch(r"[-\d.,\s]+", s):  # "40.6, 37.6" -> định dạng từng số
        return ", ".join(format_text(p, query) for p in s.split(", "))
    return strip_footnote(s)


def format_answer(value, query: str) -> str:
    if isinstance(value, dict):
        value = list(value.values())
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        value = value.tolist()
    if isinstance(value, (list, tuple, set)):
        parts = [format_answer(v, query) for v in value]
        return ", ".join(p for p in parts if p != "")
    if isinstance(value, str):
        return format_text(value, query)
    return _fmt_scalar(value, query)
