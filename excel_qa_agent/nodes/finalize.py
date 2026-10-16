"""Node cuối: chốt đáp án và đóng phiên.

Khi agent hết ngân sách (bước/thời gian/lỗi API) mà chưa gọi final(), dùng lần lượt các nguồn dự phòng:
  1. đa số các đáp án ứng viên của đường nhanh;
  2. biến kết quả mà code của agent đã gán trong sandbox (answer / result / final_answer ...);
  3. dòng in ra ngắn cuối cùng của agent (vd "Total: 4084" -> "4084").
Đáp án rỗng chắc chắn sai, nên một dự đoán hợp lý không làm giảm điểm.
"""

from __future__ import annotations

import re
from collections import Counter

from langchain_core.runnables import RunnableConfig

from ..graph.state import AgentState
from ..tools.session import SESSIONS
from ..utils.answer_format import format_answer
from ..utils.validation import check_answer, unflatten_headers

RESULT_VARS = ("final_answer", "answer", "result", "res", "output")


def _from_namespace(state: AgentState) -> tuple[str, str] | None:
    try:
        session = SESSIONS.get(state["session_id"])
    except KeyError:
        return None
    ns = session.sandbox.namespace
    for name in RESULT_VARS:
        if name not in ns or callable(ns[name]):
            continue
        value = unflatten_headers(ns[name], session.header_paths())
        if isinstance(value, (str, int, float, bool, list, tuple)) or hasattr(value, "item"):
            answer = format_answer(value, state["question"], state.get("format_spec"))
            if not check_answer(value, answer, state["question"], session.row_numbers(), session.column_letters()):
                return answer, f"variable `{name}`"
    return None


def _from_last_output(state: AgentState) -> tuple[str, str] | None:
    line = state.get("last_output")
    if not line:
        return None
    # "Total revenue: 4084" / "Answer = 4084" -> phần sau dấu ':' hoặc '=' cuối cùng
    m = re.search(r"[:=]\s*([^:=]+)$", line)
    value = (m.group(1) if m else line).strip()
    answer = format_answer(value, state["question"], state.get("format_spec"))
    return (answer, "last printed line") if answer else None


def finalize(state: AgentState, config: RunnableConfig) -> dict:
    answer = state.get("answer") or ""
    trace = []
    if not answer:
        if state.get("candidates"):
            answer = Counter(state["candidates"]).most_common(1)[0][0]
            trace.append(f"finalize: fallback to fast-path candidate {answer!r}")
        else:
            found = _from_namespace(state) or _from_last_output(state)
            if found:
                answer = found[0]
                trace.append(f"finalize: no final() call, fallback to {found[1]} -> {answer!r}")
    SESSIONS.close(state["session_id"])
    return {"answer": answer, "trace": trace}
