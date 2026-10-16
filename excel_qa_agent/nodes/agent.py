"""Node 3 (agent): LLM suy nghĩ và viết một khối code khám phá/tính toán mỗi lượt (CodeAct)."""

from __future__ import annotations

import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from .. import prompts as P
from ..config import Configuration
from ..models.llm import get_chat_model
from ..graph.state import AgentState
from ..tools.workbook_tools import TOOL_DOCS


def agent(state: AgentState, config: RunnableConfig) -> dict:
    cfg = Configuration.from_runnable_config(config)
    new_msgs = []
    if not state.get("messages"):
        extra = ""
        if state.get("candidates"):
            extra = ("\nA quick one-shot attempt was inconclusive (candidate answers: "
                     f"{sorted(set(state['candidates']))}). Verify the relevant cells yourself.")
        new_msgs += [
            SystemMessage(P.AGENT_SYSTEM.format(tool_docs=TOOL_DOCS, max_steps=cfg.agent_max_steps)),
            HumanMessage(P.AGENT_USER.format(question=state["question"], overview=state["overview"], extra=extra)),
        ]
    steps = state.get("steps", 0)
    elapsed = time.time() - state.get("started_at", time.time())
    if steps + 1 >= cfg.agent_max_steps or elapsed > 0.8 * cfg.agent_max_seconds:
        new_msgs.append(HumanMessage(P.LAST_STEP_NOTE.strip()))
    llm = get_chat_model(cfg)
    try:
        reply = llm.invoke(list(state.get("messages", [])) + new_msgs, config=config)
    except Exception as e:  # noqa: BLE001 - lỗi API (đã hết lượt retry): dừng agent, finalize dùng ứng viên có sẵn
        return {"llm_failed": True, "steps": steps + 1,
                "trace": [f"step {steps + 1}: api_error {type(e).__name__}: {str(e)[:150]}"]}
    return {"messages": new_msgs + [reply], "steps": steps + 1}
