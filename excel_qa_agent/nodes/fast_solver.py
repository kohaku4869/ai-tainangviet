"""Node 2 (đường nhanh): sinh code pandas một lượt trên bảng đã hiển thị đầy đủ.

Chạy `fast_samples` lời giải song song (temperature 0 và >0). Nếu tất cả hợp lệ và trùng nhau thì chốt luôn;
nếu không, chuyển câu hỏi sang agent.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from .. import prompts as P
from ..config import Configuration
from ..models.llm import get_chat_model
from ..graph.state import AgentState
from ..tools.session import SESSIONS, Session
from ..tools.workbook_tools import WorkbookToolkit
from ..utils.answer_format import format_answer
from ..utils.code_runner import Sandbox, extract_code
from ..utils.validation import check_answer
from .common import message_text


def _solve_once(state: AgentState, session: Session, cfg: Configuration, temperature: float,
                config: RunnableConfig) -> tuple[str | None, str]:
    """Trả về (đáp án đã định dạng hoặc None, ghi chú)."""
    toolkit = WorkbookToolkit(session.workbook, session.tables)  # sandbox riêng cho mỗi lời giải
    sandbox = Sandbox(toolkit.namespace())
    llm = get_chat_model(cfg, temperature)
    question = state["question"]
    msgs = [SystemMessage(P.FAST_SYSTEM),
            HumanMessage(P.FAST_USER.format(tables=state["tables_text"], question=question))]
    note = "no attempt"
    for _ in range(cfg.fast_max_fix + 1):
        reply = llm.invoke(msgs, config=config)
        text = message_text(reply)
        code = extract_code(text)
        msgs.append(AIMessage(text))
        if not code:
            msgs.append(HumanMessage(P.NO_CODE_USER))
            note = "no code"
            continue
        toolkit.final_called = False
        res = sandbox.run(code, cfg.code_timeout)
        if res.error:
            msgs.append(HumanMessage(P.FIX_USER.format(error=res.error)))
            note = "code error"
            continue
        if not toolkit.final_called:
            msgs.append(HumanMessage(P.RETRY_USER.format(problem="You did not call final(value).")))
            note = "final() not called"
            continue
        answer = format_answer(toolkit.final_value, question)
        problem = check_answer(toolkit.final_value, answer, question, session.row_numbers(), session.column_letters())
        if problem:
            msgs.append(HumanMessage(P.RETRY_USER.format(problem=problem)))
            note = f"rejected: {problem}"
            continue
        return answer, "ok"
    return None, note


def _safe_solve(state: AgentState, session: Session, cfg: Configuration, temperature: float,
                config: RunnableConfig) -> tuple[str | None, str]:
    """Lỗi gọi API (timeout, 5xx, hết credit...) chỉ làm hỏng lời giải này, không làm hỏng cả câu hỏi."""
    try:
        return _solve_once(state, session, cfg, temperature, config)
    except Exception as e:  # noqa: BLE001
        return None, f"api_error: {type(e).__name__}: {str(e)[:150]}"


def fast_solver(state: AgentState, config: RunnableConfig) -> dict:
    cfg = Configuration.from_runnable_config(config)
    session = SESSIONS.get(state["session_id"])
    temps = [0.0] + [0.7] * max(0, cfg.fast_samples - 1)
    with ThreadPoolExecutor(len(temps)) as ex:
        results = list(ex.map(lambda t: _safe_solve(state, session, cfg, t, config), temps))
    answers = [a for a, _ in results if a]
    # Lời giải hỏng vì lỗi API bị coi là "thiếu" chứ không phải "bất đồng"; lời giải hỏng vì lỗi logic
    # (code lỗi, đáp án bị từ chối) vẫn tính là không chắc chắn.
    logic_failures = [n for a, n in results if not a and not n.startswith("api_error")]
    trace = [f"fast: {[(a, n) for a, n in results]}"]
    if answers and not logic_failures and len(set(answers)) == 1:
        return {"answer": answers[0], "candidates": answers, "trace": trace}
    # Không đồng thuận hoặc có lời giải hỏng -> nhờ agent kiểm tra kỹ hơn.
    return {"candidates": answers, "route": "agent", "trace": trace + ["fast: inconclusive -> agent"]}
