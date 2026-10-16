"""Cấu hình agent: đọc từ biến môi trường, có thể ghi đè qua `config["configurable"]` của LangGraph."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from typing import Any

from langchain_core.runnables import RunnableConfig

# provider -> (base_url, biến môi trường chứa key, model mặc định)
PROVIDERS = {
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "qwen/qwen3.7-flash"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY", "gemini-2.5-flash-lite"),
    "openai": ("", "LLM_API_KEY", "default"),  # endpoint OpenAI-compatible bất kỳ (vLLM, LM Studio, Ollama /v1...)
}


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(kw_only=True)
class Configuration:
    # --- LLM
    provider: str = "openrouter"
    model: str = "qwen/qwen3.7-flash"
    base_url: str = PROVIDERS["openrouter"][0]
    api_key: str = field(default="", repr=False)
    reasoning: str | None = "none"  # none|low|medium|high; None = mặc định của model
    max_tokens: int = 4096
    request_timeout: float = 90.0
    max_retries: int = 2

    # --- Router / đường nhanh
    mode: str = "auto"  # auto | fast | agent
    fast_path_max_chars: int = 40_000  # bảng hiển thị dài hơn -> dùng agent
    fast_samples: int = 2  # số lời giải song song ở đường nhanh (lệch nhau -> agent)
    fast_max_fix: int = 1  # số lần cho LLM sửa code lỗi ở đường nhanh

    # --- Agent
    agent_max_steps: int = 8
    agent_max_seconds: float = 150.0
    observation_max_chars: int = 3000
    code_timeout: float = 20.0

    @classmethod
    def from_env(cls) -> "Configuration":
        provider = _env("LLM_PROVIDER").lower() or (
            "openrouter" if _env("OPENROUTER_API_KEY") else "openai" if _env("LLM_BASE_URL") else "gemini"
        )
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown LLM_PROVIDER={provider!r}; choose one of {list(PROVIDERS)}")
        base_url, key_env, default_model = PROVIDERS[provider]
        if provider == "openai":
            base_url = _env("LLM_BASE_URL")
            if not base_url:
                raise ValueError("LLM_PROVIDER=openai requires LLM_BASE_URL")
        api_key = _env(key_env) or ("EMPTY" if provider == "openai" else "")
        if not api_key:
            raise ValueError(f"Missing API key: set {key_env}")
        reasoning = _env("LLM_REASONING").lower() or ("none" if provider == "openrouter" else "")
        cfg = cls(
            provider=provider,
            model=_env("LLM_MODEL") or default_model,
            base_url=base_url,
            api_key=api_key,
            reasoning=reasoning or None,
        )
        for f in fields(cls):  # ghi đè số liệu qua biến XLQA_<TÊN>, vd XLQA_AGENT_MAX_STEPS=10
            raw = os.getenv(f"XLQA_{f.name.upper()}")
            if raw is not None and f.name not in ("api_key", "provider", "model", "base_url", "reasoning"):
                setattr(cfg, f.name, type(getattr(cfg, f.name))(raw))
        return cfg

    @classmethod
    def from_runnable_config(cls, config: RunnableConfig | None = None) -> "Configuration":
        configurable: dict[str, Any] = (config or {}).get("configurable", {}) or {}
        base = configurable.get("_base") or cls.from_env()
        overrides = {f.name: configurable[f.name] for f in fields(cls) if f.name in configurable}
        if not overrides:
            return base
        return cls(**{**{f.name: getattr(base, f.name) for f in fields(cls)}, **overrides})
