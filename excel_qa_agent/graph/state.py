"""State của graph."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class InputState(TypedDict):
    question_id: str
    question: str
    file_path: str


class OutputState(TypedDict, total=False):
    answer: str
    route: Literal["fast", "agent"]
    trace: list[str]


class AgentState(InputState, total=False):
    # --- load_workbook
    session_id: str
    overview: str  # tóm tắt workbook cho agent
    tables_text: str  # toàn bộ bảng đã hiển thị (chỉ có khi đủ nhỏ)
    route: Literal["fast", "agent"]
    started_at: float

    # --- fast_solver
    candidates: Annotated[list[str], operator.add]  # đáp án đã định dạng từ các lời giải

    # --- agent / execute_code
    messages: Annotated[list[AnyMessage], add_messages]
    steps: int
    llm_failed: bool  # agent gặp lỗi API không phục hồi được

    # --- kết quả
    final_value: Any
    answer: str
    trace: Annotated[list[str], operator.add]  # nhật ký ngắn để debug
