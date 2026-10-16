"""Kiểm tra xử lý lỗi API của excel_qa_agent mà không gọi LLM thật (model giả).

    uv run python tests/test_agent_faults.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from langchain_core.messages import AIMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from excel_qa_agent.config import Configuration  # noqa: E402
from excel_qa_agent.graph import graph  # noqa: E402
from excel_qa_agent.tools.session import SESSIONS  # noqa: E402

# Lấy module (không phải hàm cùng tên được export trong nodes/__init__.py) để thay model giả.
agent_mod = sys.modules["excel_qa_agent.nodes.agent"]
fast_mod = sys.modules["excel_qa_agent.nodes.fast_solver"]
format_mod = sys.modules["excel_qa_agent.nodes.parse_format"]

FILE = str(Path(__file__).resolve().parents[1] / "data" / "public_1" / "xlsx_files" / "p4_t04.xlsx")
QUESTION = ("What is the absolute difference between civilian noninstitutional population and civilian labor force "
            "for women with 'Some college, no degree'? Answer with only the integer, without commas or units.")
GOOD = "```python\nfinal(abs(df.loc[25, 'E'] - df.loc[26, 'E']))\n```"


class FakeModel:
    def __init__(self, fail: bool, reply: str = GOOD):
        self.fail, self.reply = fail, reply

    def invoke(self, messages, config=None):
        if self.fail:
            raise RuntimeError("Internal Server Error (simulated)")
        return AIMessage(self.reply)


def run(fast_factory, agent_factory, mode="fast", samples=2) -> dict:
    fast_mod.get_chat_model = fast_factory
    format_mod.get_chat_model = lambda cfg, t=0.0: FakeModel(fail=True)  # parse_format lỗi -> regex dự phòng
    agent_mod.get_chat_model = agent_factory
    cfg = Configuration(api_key="test", mode=mode, fast_samples=samples)
    out = graph.invoke({"question_id": "t", "question": QUESTION, "file_path": FILE},
                       config={"configurable": {"_base": cfg}})
    return out


def main() -> int:
    ok = True

    # 1) Một lời giải ở đường nhanh lỗi API, lời giải kia đúng -> vẫn có đáp án, không cần agent.
    out = run(lambda cfg, t=0.0: FakeModel(fail=t > 0), lambda cfg, t=0.0: FakeModel(fail=True))
    print("1.", out["answer"], out["route"], out["trace"][-1])
    ok &= out["answer"] == "7668" and out["route"] == "fast"

    # 2) Mọi lệnh gọi đều lỗi -> không ném exception, đáp án rỗng, phiên được đóng.
    out = run(lambda cfg, t=0.0: FakeModel(fail=True), lambda cfg, t=0.0: FakeModel(fail=True))
    print("2.", repr(out["answer"]), out["route"], out["trace"][-1])
    ok &= out["answer"] == "" and len(SESSIONS) == 0

    # 3) Đường nhanh có ứng viên nhưng một lời giải bị lỗi logic -> sang agent; agent lỗi API -> dùng ứng viên.
    def fast_factory(cfg, t=0.0):
        return FakeModel(fail=False, reply=GOOD if t == 0 else "```python\nfinal(None)\n```")

    out = run(fast_factory, lambda cfg, t=0.0: FakeModel(fail=True))
    print("3.", out["answer"], out["route"], out["trace"][-2:])
    ok &= out["answer"] == "7668" and out["route"] == "agent"

    # 4) Đáp án là header đã làm phẳng ("2023 > ... > Some college, no degree") -> chỉ lấy tầng cuối.
    header_code = "```python\nfinal(headers['cpsaat07#1']['E'])\n```"
    out = run(lambda cfg, t=0.0: FakeModel(fail=False, reply=header_code), lambda cfg, t=0.0: FakeModel(fail=True))
    print("4.", repr(out["answer"]))
    ok &= out["answer"] == "Some college, no degree"

    # 5) Agent hết bước mà không gọi final() -> lấy biến kết quả trong sandbox.
    no_final = "```python\nresult = abs(grid().loc[25, 'E'] - grid().loc[26, 'E'])\nprint('Difference:', result)\n```"
    fast_mod.get_chat_model = lambda cfg, t=0.0: FakeModel(fail=True)
    agent_mod.get_chat_model = lambda cfg, t=0.0: FakeModel(fail=False, reply=no_final)
    cfg = Configuration(api_key="test", mode="agent", agent_max_steps=2)
    out = graph.invoke({"question_id": "t", "question": QUESTION, "file_path": FILE},
                       config={"configurable": {"_base": cfg}})
    print("5.", repr(out["answer"]), out["trace"][-1])
    ok &= out["answer"] == "7668"

    # 6) Mặc định 1 lời giải: lời giải đó lỗi API -> chuyển sang agent; agent trả lời được.
    out = run(lambda cfg, t=0.0: FakeModel(fail=True), lambda cfg, t=0.0: FakeModel(fail=False), samples=1)
    print("6.", repr(out["answer"]), out["route"])
    ok &= out["answer"] == "7668" and out["route"] == "agent"

    print("sessions left:", len(SESSIONS))
    ok &= len(SESSIONS) == 0
    print("ALL OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
