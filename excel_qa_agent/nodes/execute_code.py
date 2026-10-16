"""Node 4: chạy khối code của agent trong sandbox của phiên, trả kết quả (observation) về cho agent."""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from .. import prompts as P
from ..config import Configuration
from ..graph.state import AgentState
from ..tools.session import SESSIONS
from ..utils.answer_format import format_answer
from ..utils.code_runner import extract_code, truncate
from ..utils.validation import check_answer, unflatten_headers
from .common import message_text


def execute_code(state: AgentState, config: RunnableConfig) -> dict:
    cfg = Configuration.from_runnable_config(config)
    session = SESSIONS.get(state["session_id"])
    code = extract_code(message_text(state["messages"][-1]))
    if not code:
        return {"messages": [HumanMessage(P.NO_CODE_USER)], "trace": [f"step {state['steps']}: no code"]}

    toolkit = session.toolkit
    toolkit.final_called = False
    res = session.sandbox.run(code, cfg.code_timeout)
    observation = res.stdout
    if res.error:
        observation += f"\nERROR:\n{res.error}"
    elif toolkit.final_called:
        toolkit.final_value = unflatten_headers(toolkit.final_value, session.header_paths())
        answer = format_answer(toolkit.final_value, state["question"], state.get("format_spec"))
        problem = check_answer(toolkit.final_value, answer, state["question"],
                               session.row_numbers(), session.column_letters())
        if not problem:
            return {"answer": answer, "final_value": repr(toolkit.final_value),
                    "trace": [f"step {state['steps']}: final {answer!r}"]}
        observation += f"\nANSWER REJECTED: {problem}"
    observation = truncate(observation.strip() or "(no output)", cfg.observation_max_chars)
    update = {"messages": [HumanMessage(f"Output:\n{observation}")],
              "trace": [f"step {state['steps']}: {'error' if res.error else 'ok'}"]}
    last_line = _last_short_line(res.stdout) if not res.error else None
    if last_line:
        update["last_output"] = last_line  # dự phòng cho finalize nếu agent hết bước mà chưa gọi final()
    return update


# Dòng do pandas tự in (kích thước bảng, dtype...) hoặc do công cụ view()/overview() in ra không phải là giá trị kết quả.
_PANDAS_NOISE = re.compile(
    r"^\[\d+ rows x \d+ columns\]$|^(dtype|Name|Length|Index)\b.*:|^Empty DataFrame|^Columns:"
    r"|^\.\.\. ?\(|call view|^merged ranges:|^row \||^Sheet '|^\s*(WARNING|first row labels):"
)


def _last_short_line(stdout: str, max_len: int = 150) -> str | None:
    lines = [ln.strip() for ln in stdout.strip().splitlines() if ln.strip()]
    if not lines or len(lines[-1]) > max_len or _PANDAS_NOISE.search(lines[-1]):
        return None
    return lines[-1]
