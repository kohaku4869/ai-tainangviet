"""Node 5: chốt đáp án (dự phòng bằng đa số các ứng viên nếu agent hết ngân sách) và đóng phiên."""

from __future__ import annotations

from collections import Counter

from langchain_core.runnables import RunnableConfig

from ..graph.state import AgentState
from ..tools.session import SESSIONS


def finalize(state: AgentState, config: RunnableConfig) -> dict:
    answer = state.get("answer") or ""
    trace = []
    if not answer and state.get("candidates"):
        answer = Counter(state["candidates"]).most_common(1)[0][0]
        trace.append(f"finalize: budget exhausted, fallback to candidate {answer!r}")
    SESSIONS.close(state["session_id"])
    return {"answer": answer, "trace": trace}
