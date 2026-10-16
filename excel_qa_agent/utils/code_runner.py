"""Trích và chạy code Python do LLM sinh ra trong một namespace giữ trạng thái giữa các bước."""

from __future__ import annotations

import contextlib
import io
import re
import threading
import traceback
from dataclasses import dataclass

CODE_RE = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.S)


def extract_code(text: str) -> str | None:
    blocks = CODE_RE.findall(text or "")
    return blocks[-1].strip() if blocks else None


def truncate(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    half = limit // 2
    return f"{s[:half]}\n... [{len(s) - limit} chars truncated] ...\n{s[-half:]}"


@dataclass
class ExecResult:
    stdout: str
    error: str | None


class Sandbox:
    """Namespace Python giữ trạng thái giữa các lần chạy (kiểu Jupyter) với giới hạn thời gian mỗi lần."""

    def __init__(self, namespace: dict):
        self.namespace = namespace
        self._lock = threading.Lock()

    def run(self, code: str, timeout: float = 20.0) -> ExecResult:
        out = io.StringIO()
        result: dict = {}

        def target():
            try:
                with contextlib.redirect_stdout(out):
                    exec(compile(code, "<llm_code>", "exec"), self.namespace)  # noqa: S102
            except Exception:  # noqa: BLE001
                result["error"] = traceback.format_exc(limit=3)[-1500:]

        with self._lock:
            th = threading.Thread(target=target, daemon=True)
            th.start()
            th.join(timeout)
        if th.is_alive():
            return ExecResult(out.getvalue(), f"TimeoutError: code ran longer than {timeout}s")
        return ExecResult(out.getvalue(), result.get("error"))
