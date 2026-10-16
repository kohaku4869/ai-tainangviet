"""Khởi tạo chat model (OpenAI-compatible: OpenRouter, Gemini, endpoint tự host)."""

from __future__ import annotations

import threading

from langchain_openai import ChatOpenAI

from ..config import Configuration

_CACHE: dict[tuple, ChatOpenAI] = {}
_LOCK = threading.Lock()


def get_chat_model(cfg: Configuration, temperature: float = 0.0) -> ChatOpenAI:
    key = (cfg.provider, cfg.model, cfg.base_url, cfg.reasoning, cfg.max_tokens, cfg.request_timeout,
           cfg.max_retries, temperature)
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
        extra_body: dict = {}
        kwargs: dict = {}
        if cfg.provider == "openrouter":
            extra_body["usage"] = {"include": True}  # OpenRouter trả về usage.cost (USD)
            if cfg.reasoning == "none":
                extra_body["reasoning"] = {"enabled": False}
            elif cfg.reasoning:
                extra_body["reasoning"] = {"effort": cfg.reasoning}
        elif cfg.reasoning:
            kwargs["reasoning_effort"] = cfg.reasoning
        model = ChatOpenAI(
            model=cfg.model,
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            temperature=temperature,
            max_tokens=cfg.max_tokens,
            timeout=cfg.request_timeout,
            max_retries=cfg.max_retries,
            extra_body=extra_body or None,
            **kwargs,
        )
        _CACHE[key] = model
        return model
