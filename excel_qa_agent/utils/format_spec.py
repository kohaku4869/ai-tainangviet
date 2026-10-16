"""Spec định dạng đáp án: do node parse_format (LLM) trích từ câu hỏi, hoặc regex tiếng Anh khi LLM lỗi."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

WORD_NUM = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


@dataclass
class FormatSpec:
    answer_type: str = "auto"  # number | text | list | yes_no | date | auto
    decimals: int | None = None  # 0 = số nguyên; None = không yêu cầu
    thousands_separator: bool = False
    percent_sign: bool = False
    list_separator: str = ", "
    yes_word: str | None = None
    no_word: str | None = None
    magnitude_only: bool = False  # hỏi độ lớn của thay đổi/chênh lệch -> số không âm
    source: str = "default"  # llm | regex | default

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "FormatSpec":
        if not d:
            return cls()
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def describe(self) -> str:
        """Mô tả ngắn để đưa vào prompt của bước giải."""
        parts = [f"type={self.answer_type}"]
        if self.decimals is not None:
            parts.append("integer" if self.decimals == 0 else f"{self.decimals} decimal places")
        if self.percent_sign:
            parts.append("with % sign")
        if self.yes_word:
            parts.append(f"yes/no words: {self.yes_word!r}/{self.no_word!r}")
        if self.magnitude_only:
            parts.append("non-negative magnitude")
        if self.answer_type == "list":
            parts.append(f"items separated by {self.list_separator!r}")
        return ", ".join(parts)


def _as_int(v) -> int | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if 0 <= n <= 10 else None


def spec_from_llm_text(text: str) -> FormatSpec | None:
    """Đọc JSON do LLM trả về; None nếu không hợp lệ."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(d, dict):
        return None
    answer_type = str(d.get("answer_type") or "auto").lower()
    if answer_type not in {"number", "text", "list", "yes_no", "date", "auto"}:
        answer_type = "auto"
    sep = d.get("list_separator")
    return FormatSpec(
        answer_type=answer_type,
        decimals=_as_int(d.get("decimals")),
        thousands_separator=bool(d.get("thousands_separator")),
        percent_sign=bool(d.get("percent_sign")),
        list_separator=sep if isinstance(sep, str) and 0 < len(sep) <= 5 else ", ",
        yes_word=d.get("yes_word") or None,
        no_word=d.get("no_word") or None,
        magnitude_only=bool(d.get("magnitude_only")),
        source="llm",
    )


def spec_from_regex(query: str) -> FormatSpec:
    """Dự phòng khi LLM lỗi: chỉ hiểu chỉ dẫn tiếng Anh."""
    q = query.lower()
    spec = FormatSpec(source="regex")
    m = re.search(r"(\d+|zero|one|two|three|four|five|six)\s+decimal(?:\s+places?|s)?", q)
    if m:
        w = m.group(1)
        spec.decimals = int(w) if w.isdigit() else WORD_NUM[w]
    elif re.search(r"(nearest|whole) (integer|number)|as an integer|\bintegers?\b", q):
        spec.decimals = 0
    if re.search(r"\byes\b[^.?]{0,15}\bno\b", q):
        spec.answer_type, spec.yes_word, spec.no_word = "yes_no", "Yes", "No"
    return spec
