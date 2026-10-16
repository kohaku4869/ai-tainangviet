"""Node: trích yêu cầu định dạng đáp án từ câu hỏi (mọi ngôn ngữ) thành FormatSpec.

Chạy song song với load_workbook nên gần như không cộng thêm thời gian. Nếu LLM lỗi hoặc trả JSON hỏng,
dùng regex tiếng Anh làm dự phòng.
"""

from __future__ import annotations

from dataclasses import replace

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from .. import prompts as P
from ..config import Configuration
from ..graph.state import AgentState
from ..models.llm import get_chat_model
from ..utils.format_spec import spec_from_llm_text, spec_from_regex
from .common import message_text


def parse_format(state: AgentState, config: RunnableConfig) -> dict:
    cfg = Configuration.from_runnable_config(config)
    question = state["question"]
    note = ""
    try:
        llm = get_chat_model(replace(cfg, max_tokens=300))
        reply = llm.invoke([HumanMessage(P.FORMAT_SPEC_USER.format(question=question))], config=config)
        spec = spec_from_llm_text(message_text(reply))
        if spec is None:
            note = " (invalid JSON -> regex fallback)"
    except Exception as e:  # noqa: BLE001 - lỗi API không được làm hỏng câu hỏi
        spec, note = None, f" (api_error {type(e).__name__} -> regex fallback)"
    if spec is None:
        spec = spec_from_regex(question)
    return {"format_spec": spec.to_dict(), "trace": [f"format: {spec.describe()} [{spec.source}]{note}"]}
