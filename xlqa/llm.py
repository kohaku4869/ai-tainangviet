"""Client LLM dùng chuẩn OpenAI-compatible (OpenRouter, Gemini...). Cấu hình qua biến môi trường.

LLM_PROVIDER=openrouter|gemini|ollama|openai
    (mặc định: openrouter nếu có OPENROUTER_API_KEY; openai nếu có LLM_BASE_URL; ngược lại gemini)
OPENROUTER_API_KEY / GEMINI_API_KEY   khóa cho provider tương ứng
LLM_API_KEY, LLM_BASE_URL             dùng cho provider `openai` (endpoint OpenAI-compatible tự host)
LLM_MODEL     (mặc định qwen/qwen3.7-flash với openrouter, gemini-2.5-flash-lite với gemini)
LLM_REASONING (none|low|medium|high; mặc định none với openrouter)
"""

from __future__ import annotations

import os
import random
import threading
import time
from dataclasses import dataclass

from openai import OpenAI

PRESETS = {
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "qwen/qwen3.7-flash"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY", "gemini-2.5-flash-lite"),
    "ollama": ("http://localhost:11434", "", "qwen3.5:4b"),  # chỉ để thử nghiệm local
    "openai": ("", "LLM_API_KEY", "default"),  # endpoint OpenAI-compatible bất kỳ (vLLM, LM Studio...): cần LLM_BASE_URL, LLM_MODEL
}


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0  # USD, do OpenRouter trả về trong usage.cost

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLM:
    def __init__(self, model: str | None = None, max_concurrency: int = 8):
        provider = os.getenv("LLM_PROVIDER", "").strip().lower() or (
            "openrouter" if os.getenv("OPENROUTER_API_KEY") else "openai" if os.getenv("LLM_BASE_URL") else "gemini"
        )
        base_url, key_env, default_model = PRESETS[provider]
        self.provider = provider
        self.model = model or os.getenv("LLM_MODEL") or default_model
        # LLM_BASE_URL/LLM_API_KEY chỉ dành cho endpoint tự host, không áp lên openrouter/gemini.
        self.base_url = (os.getenv("LLM_BASE_URL") if provider in ("openai", "ollama") else None) or base_url
        # Mặc định tắt reasoning trên OpenRouter: nhanh/rẻ hơn ~3 lần và đúng không kém (đã đo trên bộ public + synth).
        self.reasoning = os.getenv("LLM_REASONING", "").strip().lower() or ("none" if provider == "openrouter" else None)
        self.usage = Usage()
        if provider != "ollama":
            api_key = os.getenv(key_env) or ("EMPTY" if provider == "openai" else None)
            if not api_key:
                raise RuntimeError(f"Missing API key: set LLM_API_KEY or {key_env}")
            self.client = OpenAI(api_key=api_key, base_url=self.base_url, max_retries=0,
                                 timeout=float(os.getenv("LLM_TIMEOUT", "90")))
        self._lock = threading.Lock()
        self._sem = threading.Semaphore(max_concurrency)

    def _extra(self) -> dict:
        if self.provider == "openrouter":
            body: dict = {"usage": {"include": True}}  # để nhận usage.cost
            if self.reasoning == "none":
                body["reasoning"] = {"enabled": False}
            elif self.reasoning:
                body["reasoning"] = {"effort": self.reasoning}
            return {"extra_body": body}
        return {"reasoning_effort": self.reasoning} if self.reasoning else {}

    def _chat_ollama(self, messages: list[dict], max_tokens: int, temperature: float) -> str:
        import json
        import urllib.request

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": self.reasoning not in (None, "none"),
            "options": {"num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "16384")), "temperature": temperature,
                        "num_predict": max_tokens},
        }
        req = urllib.request.Request(
            self.base_url.rstrip("/") + "/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=900) as r:
            data = json.loads(r.read())
        with self._lock:
            self.usage.calls += 1
            self.usage.prompt_tokens += data.get("prompt_eval_count", 0)
            self.usage.completion_tokens += data.get("eval_count", 0)
        return data["message"].get("content", "")

    def chat(self, messages: list[dict], max_tokens: int = 4096, temperature: float = 0.0, retries: int = 4) -> str:
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                if self.provider == "ollama":
                    with self._sem:
                        return self._chat_ollama(messages, max_tokens, temperature)
                with self._sem:
                    resp = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        **self._extra(),
                    )
                with self._lock:
                    self.usage.calls += 1
                    if resp.usage:
                        self.usage.prompt_tokens += resp.usage.prompt_tokens or 0
                        self.usage.completion_tokens += resp.usage.completion_tokens or 0
                        cost = getattr(resp.usage, "cost", None)
                        if cost is None and getattr(resp.usage, "model_extra", None):
                            cost = resp.usage.model_extra.get("cost")
                        self.usage.cost += float(cost or 0)
                return resp.choices[0].message.content or ""
            except Exception as e:  # noqa: BLE001 - retry mọi lỗi mạng/rate limit
                last_err = e
                status = getattr(e, "status_code", None)
                if status in (400, 401, 403, 404):
                    break
                if "timed out" in str(e).lower() and attempt >= 1:
                    break  # server treo: không đốt hết quỹ thời gian của câu hỏi
                time.sleep(min(30, 2**attempt + random.random()))
        raise RuntimeError(f"LLM call failed: {last_err}")
