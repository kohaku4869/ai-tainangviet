"""Các hàm điều hướng (conditional edges) của graph."""

from __future__ import annotations

from typing import Literal

from langchain_core.runnables import RunnableConfig

from ..config import Configuration
from ..graph.state import AgentState
from .common import agent_budget_left


def route_after_load(state: AgentState) -> Literal["fast_solver", "agent"]:
    return "fast_solver" if state.get("route") == "fast" else "agent"


def route_after_fast(state: AgentState) -> Literal["finalize", "agent"]:
    return "finalize" if state.get("answer") else "agent"


def route_after_agent(state: AgentState) -> Literal["execute_code", "finalize"]:
    return "finalize" if state.get("llm_failed") else "execute_code"


def route_after_execute(state: AgentState, config: RunnableConfig) -> Literal["finalize", "agent"]:
    if state.get("answer"):
        return "finalize"
    cfg = Configuration.from_runnable_config(config)
    return "agent" if agent_budget_left(state, cfg) else "finalize"
