"""Hàm dùng chung cho các node."""

from __future__ import annotations

import time

from langchain_core.messages import BaseMessage

from ..config import Configuration
from ..graph.state import AgentState


def message_text(msg: BaseMessage) -> str:
    content = msg.content
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)


def agent_budget_left(state: AgentState, cfg: Configuration) -> bool:
    steps_ok = state.get("steps", 0) < cfg.agent_max_steps
    time_ok = time.time() - state.get("started_at", time.time()) < cfg.agent_max_seconds
    return steps_ok and time_ok


def dispatch(state: AgentState) -> dict:
    """Điểm hội tụ sau load_workbook và parse_format (chạy song song); việc chọn đường do route_after_load làm."""
    return {}
