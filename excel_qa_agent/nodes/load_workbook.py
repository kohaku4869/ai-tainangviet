"""Node 1: đọc workbook, đoán bảng, tạo phiên sandbox và quyết định đi đường nhanh hay agent."""

from __future__ import annotations

import time
from functools import lru_cache

from langchain_core.runnables import RunnableConfig

from ..config import Configuration
from ..graph.state import AgentState
from ..tools.session import SESSIONS, Session
from ..utils.excel_reader import read_workbook
from ..utils.rendering import render_overview, render_tables
from ..utils.table_detector import Table, detect_tables


@lru_cache(maxsize=32)
def _tables_for(path: str) -> tuple[Table, ...]:
    wb = read_workbook(path)
    return tuple(t for sd in wb.sheets.values() for t in detect_tables(sd))


def load_workbook(state: AgentState, config: RunnableConfig) -> dict:
    cfg = Configuration.from_runnable_config(config)
    path = state["file_path"]
    wb = read_workbook(path)
    tables = list(_tables_for(path))
    sid = SESSIONS.put(Session.create(wb, tables), owner=state["question_id"])

    tables_text = render_tables(tables)
    reasons: list[str] = []
    if not tables:
        reasons.append("no table detected")
    if len(tables_text) > cfg.fast_path_max_chars:
        reasons.append(f"tables too large to show in full ({len(tables_text)} chars)")
    reasons += [f"{t.name}: {w}" for t in tables for w in t.warnings]

    if cfg.mode in ("fast", "agent"):
        route = cfg.mode
    else:
        route = "agent" if reasons else "fast"
    return {
        "session_id": sid,
        "overview": render_overview(wb, tables),
        "tables_text": tables_text if len(tables_text) <= cfg.fast_path_max_chars else "",
        "route": route,
        "started_at": time.time(),
        "steps": 0,
        "trace": [f"load: {len(wb.sheets)} sheet(s), {len(tables)} table(s), route={route}"
                  + (f" ({'; '.join(reasons)})" if reasons else "")],
    }
