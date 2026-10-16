"""Chuẩn hóa giá trị ô Excel."""

from __future__ import annotations

import datetime as dt
import re

MISSING_TOKENS = {"", "-", "–", "—", "…", "...", "�", "na", "n/a", "(na)", "(x)", "x", "(z)", "z", "nan", "none"}
NUM_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")

# Tiền tố giữ dấu gạch nối khi header bị ngắt dòng ("Self-\nemployed"), còn lại nối liền ("Con-\nstruction").
HYPHEN_PREFIXES = {"self", "non", "part", "full", "year", "co", "ex", "multi", "semi", "well", "high", "low",
                   "long", "short", "post", "pre", "anti", "mid", "one", "two", "three", "four", "five"}


def _join_hyphen(m: re.Match) -> str:
    word = m.group(1)
    return f"{word}-" if word.lower() in HYPHEN_PREFIXES else word


def clean_text(s: str) -> str:
    s = s.replace("\r", "")
    s = re.sub(r"(\w+)-\n(?=[a-z])", _join_hyphen, s)
    s = re.sub(r"\s*\n\s*", " ", s)
    return re.sub(r"[ \t]+", " ", s).strip()


def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def is_date(v) -> bool:
    return isinstance(v, (dt.date, dt.datetime))


def to_value(v):
    """Số dạng chuỗi -> số, ký hiệu thiếu dữ liệu -> None, chuỗi -> chuỗi đã làm sạch."""
    if v is None or isinstance(v, bool):
        return v
    if isinstance(v, float):
        v = float(f"{v:.12g}")  # bỏ nhiễu dấu phẩy động
        return int(v) if v.is_integer() and abs(v) < 1e15 else v
    if isinstance(v, int) or isinstance(v, (dt.date, dt.datetime, dt.time)):
        return v
    s = clean_text(str(v))
    if s.lower() in MISSING_TOKENS:
        return None
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s).replace(" ", "")
    if NUM_RE.match(t):
        f = float(t)
        return int(f) if f.is_integer() and "." not in t and "e" not in t.lower() else f
    return s


def fmt_value(v) -> str:
    """Hiển thị giá trị ô cho LLM."""
    if v is None:
        return ""
    if isinstance(v, dt.datetime):
        return v.strftime("%Y-%m-%d") if v.time() == dt.time(0) else v.isoformat(sep=" ")
    if isinstance(v, dt.date):
        return v.isoformat()
    return str(v)
