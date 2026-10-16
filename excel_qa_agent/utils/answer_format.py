"""Chuẩn hóa đáp án cuối cùng theo FormatSpec (phục vụ Exact Match).

Việc *hiểu* yêu cầu định dạng (mọi ngôn ngữ) do node parse_format làm; module này chỉ *áp dụng* spec một cách
cố định. Khi không có spec, dùng regex tiếng Anh (spec_from_regex).
"""

from __future__ import annotations

import datetime as dt
import math
import re

from .format_spec import FormatSpec, spec_from_regex

YES_WORDS = {"yes", "true", "có", "oui", "sí", "si", "ja", "예", "네", "是", "はい", "да"}
NO_WORDS = {"no", "false", "không", "non", "nein", "아니요", "아니오", "否", "不是", "いいえ", "нет"}


def strip_footnote(s: str) -> str:
    """Bỏ ký hiệu chú thích của bảng thống kê: "Food(1)" -> "Food", "Trade balance 3/" -> "Trade balance"."""
    s = re.sub(r"\s*\(\d+\)(\(\d+\))*", "", s)
    s = re.sub(r"\s+\d+/$", "", s)
    return s.strip()


def _fmt_number(v: float | int, spec: FormatSpec) -> str:
    if spec.magnitude_only:
        v = abs(v)
    d = spec.decimals
    eps = 1e-9 if v >= 0 else -1e-9  # tránh lỗi làm tròn kiểu 2.675 -> 2.67
    sep = "," if spec.thousands_separator else ""
    if d is None:
        if float(v).is_integer():
            s = f"{int(round(v)):{sep}d}"
        else:
            s = f"{round(v, 6):{sep}.6f}".rstrip("0").rstrip(".")
    elif d == 0:
        s = f"{int(round(v + eps)):{sep}d}"
    else:
        s = f"{v + eps:{sep}.{d}f}"
    return s + ("%" if spec.percent_sign else "")


def _yes_no(word: str, spec: FormatSpec) -> str | None:
    low = word.strip().lower()
    yes, no = spec.yes_word or "Yes", spec.no_word or "No"
    if low in YES_WORDS or low == yes.lower() or low.startswith("yes"):
        return yes
    if low in NO_WORDS or low == no.lower() or re.match(r"no\b", low):
        return no
    return None


def _fmt_scalar(v, spec: FormatSpec) -> str:
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
        return (spec.yes_word or "Yes") if v else (spec.no_word or "No")
    if isinstance(v, dt.datetime):
        return v.strftime("%Y-%m-%d") if v.time() == dt.time(0) else v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, (int, float)):
        return _fmt_number(v, spec)
    return _fmt_text(str(v), spec)


def _fmt_text(s: str, spec: FormatSpec) -> str:
    s = re.sub(r"\s+", " ", s.strip().strip("`").strip())
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1].strip()
    if s.endswith(".") and not re.search(r"\d\.$", s):
        s = s[:-1].rstrip()
    if spec.answer_type == "yes_no" or spec.yes_word:
        yn = _yes_no(s, spec)
        if yn:
            return yn
    plain = s.rstrip("%").strip()
    plain = plain.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", plain) else plain
    if re.fullmatch(r"-?\d+(\.\d+)?", plain):
        return _fmt_number(float(plain) if "." in plain else int(plain), spec)
    if ", " in s and re.fullmatch(r"[-\d.,%\s]+", s):  # "40.6, 37.6" -> định dạng từng số
        return spec.list_separator.join(_fmt_text(p, spec) for p in s.split(", "))
    return strip_footnote(s)


def format_answer(value, query: str, spec: FormatSpec | dict | None = None) -> str:
    if isinstance(spec, dict) or spec is None:
        spec = FormatSpec.from_dict(spec) if spec else spec_from_regex(query)
    if isinstance(value, dict):
        value = list(value.values())
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        value = value.tolist()
    if isinstance(value, (list, tuple, set)):
        parts = [format_answer(v, query, spec) for v in value]
        return spec.list_separator.join(p for p in parts if p != "")
    if isinstance(value, str):
        return _fmt_text(value, spec)
    return _fmt_scalar(value, spec)
