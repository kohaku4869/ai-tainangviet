"""Kho phiên làm việc theo câu hỏi: giữ sandbox (namespace Python) ngoài state của graph.

State của LangGraph chỉ chứa `session_id` (chuỗi), còn đối tượng sandbox không serialize được nằm ở đây.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass

from ..utils.code_runner import Sandbox
from ..utils.excel_reader import WorkbookData
from ..utils.table_detector import Table
from .workbook_tools import WorkbookToolkit


@dataclass
class Session:
    workbook: WorkbookData
    tables: list[Table]
    toolkit: WorkbookToolkit
    sandbox: Sandbox

    @classmethod
    def create(cls, workbook: WorkbookData, tables: list[Table]) -> "Session":
        toolkit = WorkbookToolkit(workbook, tables)
        return cls(workbook, tables, toolkit, Sandbox(toolkit.namespace()))

    def row_numbers(self) -> set[int]:
        return {r for t in self.tables for r in t.rows}

    def column_letters(self) -> set[str]:
        return {c for t in self.tables for c in t.columns}


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._owners: dict[str, str] = {}  # session_id -> question_id
        self._lock = threading.Lock()

    def put(self, session: Session, owner: str = "") -> str:
        sid = uuid.uuid4().hex
        with self._lock:
            self._sessions[sid] = session
            self._owners[sid] = owner
        return sid

    def get(self, sid: str) -> Session:
        with self._lock:
            return self._sessions[sid]

    def close(self, sid: str) -> None:
        with self._lock:
            self._sessions.pop(sid, None)
            self._owners.pop(sid, None)

    def close_owner(self, owner: str) -> None:
        """Đóng mọi phiên của một câu hỏi (dọn dẹp khi graph dừng giữa chừng vì lỗi)."""
        with self._lock:
            for sid in [s for s, o in self._owners.items() if o == owner]:
                self._sessions.pop(sid, None)
                self._owners.pop(sid, None)

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)


SESSIONS = SessionStore()
