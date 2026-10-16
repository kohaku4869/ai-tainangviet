"""Kiểm tra tính hợp lệ của đáp án (các lỗi chung của LLM, không phụ thuộc bộ dữ liệu)."""

from __future__ import annotations

import math
import re


def check_answer(value, formatted: str, query: str, row_numbers: set[int], column_letters: set[str]) -> str | None:
    """Trả về mô tả vấn đề (để LLM tự sửa) hoặc None nếu đáp án trông hợp lệ."""
    if value is None or formatted == "":
        return "The answer is empty."
    if isinstance(value, float) and math.isnan(value):
        return "The answer is NaN: the selection probably matched no cells."
    if len(formatted) > 300:
        return "The answer is too long: return only the final value, not a table or explanation."
    q = query.lower()
    asks_name = bool(re.match(r"\s*(which|who)\b", q)) and not re.search(r"\b(year|number|how many|age)\b", q)
    if asks_name and formatted.strip() in column_letters:
        return f"'{formatted}' is a column letter; return the column's header name instead."
    if asks_name and re.fullmatch(r"\d+", formatted) and int(formatted) in row_numbers:
        return f"{formatted} looks like an Excel row number; return that row's label instead."
    return None
