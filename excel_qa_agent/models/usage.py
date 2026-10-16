"""Callback đếm số lượt gọi, token và chi phí (USD, do OpenRouter trả về) cho từng câu hỏi."""

from __future__ import annotations

import threading
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


class UsageCallback(BaseCallbackHandler):
    def __init__(self) -> None:
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost = 0.0
        self._lock = threading.Lock()

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        with self._lock:
            for gens in response.generations:
                for g in gens:
                    msg = getattr(g, "message", None)
                    self.calls += 1
                    usage = getattr(msg, "usage_metadata", None) or {}
                    self.input_tokens += usage.get("input_tokens", 0)
                    self.output_tokens += usage.get("output_tokens", 0)
                    meta = getattr(msg, "response_metadata", None) or {}
                    cost = (meta.get("token_usage") or {}).get("cost")
                    self.cost += float(cost or 0.0)

    def as_dict(self) -> dict:
        return {"calls": self.calls, "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "cost": round(self.cost, 8)}
