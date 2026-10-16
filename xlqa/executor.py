"""Chạy code pandas do LLM sinh ra trên các bảng đã chuẩn hóa."""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import math
import re
import threading
import traceback

import numpy as np
import pandas as pd

from .excel import Block

CODE_RE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S)


def extract_code(text: str) -> str | None:
    blocks = CODE_RE.findall(text or "")
    return blocks[-1].strip() if blocks else None


def run_code(code: str, blocks: list[Block], timeout: float = 20.0) -> tuple[object, str | None, str]:
    """Trả về (answer, error, stdout). Code phải gán biến `answer`."""
    env = {
        "pd": pd,
        "np": np,
        "math": math,
        "re": re,
        "datetime": dt,
        "tables": {b.name: b.df.copy() for b in blocks},
        "df": blocks[0].df.copy() if blocks else None,
        "headers": {b.name: dict(b.columns) for b in blocks},
    }
    out = io.StringIO()
    result: dict = {}

    def target():
        try:
            with contextlib.redirect_stdout(out):
                exec(compile(code, "<llm_code>", "exec"), env)
            result["answer"] = env.get("answer")
        except Exception:
            tb = traceback.format_exc(limit=3)
            result["error"] = tb[-1500:]

    th = threading.Thread(target=target, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        return None, f"Timeout after {timeout}s", out.getvalue()
    if "error" in result:
        return None, result["error"], out.getvalue()
    if "answer" not in env:
        return None, "Variable `answer` was not set.", out.getvalue()
    return result.get("answer"), None, out.getvalue()
