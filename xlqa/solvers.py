"""Các chiến lược trả lời: direct (đọc bảng), pot (sinh code pandas), hybrid (cả hai + phân xử)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from . import prompts as P
from .excel import Block, load_workbook_blocks, render_blocks
from .executor import extract_code, run_code
from .formatting import _strip_footnote, format_answer
from .llm import LLM

MAX_RENDER_CHARS = 60_000
ANSWER_RE = re.compile(r"ANSWER:\s*(.+?)\s*$", re.S | re.I)


@lru_cache(maxsize=64)
def get_blocks(path: str) -> tuple[Block, ...]:
    return tuple(load_workbook_blocks(path))


def tables_text(blocks: list[Block], query: str) -> tuple[str, list[Block]]:
    """Hiển thị toàn bộ bảng nếu đủ nhỏ; nếu không thì chọn bảng liên quan và rút gọn số dòng."""
    text = render_blocks(blocks)
    if len(text) <= MAX_RENDER_CHARS:
        return text, blocks
    words = set(re.findall(r"[a-z]{3,}", query.lower()))

    def score(b: Block) -> int:
        return len(words & set(re.findall(r"[a-z]{3,}", b.render(max_rows=200).lower())))

    ranked = sorted(blocks, key=score, reverse=True)
    chosen: list[Block] = []
    for b in ranked:
        if len(render_blocks(chosen + [b], max_rows=150)) > MAX_RENDER_CHARS and chosen:
            break
        chosen.append(b)
    return render_blocks(chosen, max_rows=150), chosen


@dataclass
class Result:
    answer: str
    raw: object = None
    trace: list = field(default_factory=list)


def _final_line(text: str) -> str:
    m = ANSWER_RE.search(text or "")
    return m.group(1).strip().splitlines()[0] if m else (text or "").strip().splitlines()[-1] if text else ""


def solve_direct(llm: LLM, blocks: list[Block], query: str) -> Result:
    tables, _ = tables_text(blocks, query)
    msgs = [
        {"role": "system", "content": P.SYSTEM},
        {"role": "user", "content": P.DIRECT_USER.format(tables=tables, query=query, guidelines=P.GUIDELINES)},
    ]
    out = llm.chat(msgs)
    raw = _final_line(out)
    return Result(format_answer(raw, query), raw, [out])


def _letters_to_headers(value, chosen: list[Block]):
    """LLM đôi khi trả về chữ cái cột ('K') thay vì tên cột -> đổi sang tầng header cuối cùng."""
    if isinstance(value, (list, tuple)):
        return [_letters_to_headers(v, chosen) for v in value]
    if isinstance(value, str) and re.fullmatch(r"[A-Z]{1,2}", value.strip()):
        for b in chosen:
            desc = b.columns.get(value.strip())
            if desc and value.strip() != b.label_col:
                return _strip_footnote(desc.split(" > ")[-1])
    if isinstance(value, str) and " > " in value:  # trả nguyên đường dẫn header -> lấy tầng cuối
        if any(value.strip() == d for b in chosen for d in b.columns.values()):
            return value.split(" > ")[-1]
    return value


SUMMARY_LABELS = {"total", "grand total", "all items", "sum", "subtotal", "tổng", "tổng cộng"}


def _suspicious(value, ans: str, query: str, chosen: list[Block]) -> str | None:
    """Phát hiện các lỗi hay gặp để yêu cầu LLM sửa: trả về số dòng thay vì nhãn, chọn nhầm dòng tổng."""
    q = query.lower()
    if re.match(r"\s*(which|who)\b", q) and isinstance(value, (int, float)) and not isinstance(value, bool):
        if float(value).is_integer() and any(int(value) in b.df.index for b in chosen) and not re.search(
            r"\b(year|number|how many|age)\b", q
        ):
            return (f"Your answer {value!r} looks like an Excel row number, but the question asks for a name. "
                    "Return the row's label text instead.")
    if ans.lower() in SUMMARY_LABELS and not any(w in q for w in ("total", "summary", "sum")):
        return ("Your answer is a summary/total row, but the question asks about an individual item. "
                "Exclude total/subtotal rows and recompute.")
    return None


def solve_pot(llm: LLM, blocks: list[Block], query: str, max_fix: int = 2, temperature: float = 0.0) -> Result:
    tables, chosen = tables_text(blocks, query)
    msgs = [
        {"role": "system", "content": P.SYSTEM},
        {
            "role": "user",
            "content": P.POT_USER.format(
                tables=tables, query=query, guidelines=P.GUIDELINES, first_name=chosen[0].name
            ),
        },
    ]
    trace = []
    code = None
    for attempt in range(max_fix + 1):
        out = llm.chat(msgs, temperature=temperature)
        trace.append(out)
        code = extract_code(out)
        if not code:
            msgs += [{"role": "assistant", "content": out}, {"role": "user", "content": "Reply with one ```python block."}]
            continue
        value, err, _ = run_code(code, chosen)
        if err:
            trace.append(err)
            msgs += [{"role": "assistant", "content": out}, {"role": "user", "content": P.FIX_USER.format(error=err)}]
            continue
        value = _letters_to_headers(value, chosen)
        ans = format_answer(value, query)
        problem = _suspicious(value, ans, query, chosen)
        if problem and attempt < max_fix:
            trace.append(f"CHECK: {problem}")
            msgs += [{"role": "assistant", "content": out},
                     {"role": "user", "content": f"{problem} Reply with one corrected ```python block that assigns `answer`."}]
            continue
        if ans == "" and attempt < max_fix:
            msgs += [{"role": "assistant", "content": out}, {"role": "user", "content": P.EMPTY_USER.format(value=value)}]
            continue
        return Result(ans, value, trace + [code])
    return Result("", None, trace + [code])


def solve_hybrid(llm: LLM, blocks: list[Block], query: str) -> Result:
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(2) as ex:
        fa = ex.submit(_safe, solve_direct, llm, blocks, query)
        fb = ex.submit(_safe, solve_pot, llm, blocks, query)
        a, b = fa.result(), fb.result()
    if a.answer == b.answer or not a.answer:
        return Result(b.answer or a.answer, b.raw, ["agree" if a.answer == b.answer else "pot-only", a.trace, b.trace])
    if not b.answer:
        return Result(a.answer, a.raw, ["direct-only", a.trace, b.trace])
    tables, _ = tables_text(blocks, query)
    msgs = [
        {"role": "system", "content": P.SYSTEM},
        {
            "role": "user",
            "content": P.JUDGE_USER.format(
                tables=tables,
                query=query,
                a_text=a.trace[-1][-1500:],
                a_answer=a.answer,
                b_code=b.trace[-1],
                b_answer=b.answer,
                guidelines=P.GUIDELINES,
            ),
        },
    ]
    out = llm.chat(msgs)
    raw = _final_line(out)
    return Result(format_answer(raw, query), raw, ["judge", a.trace, b.trace, out])


def _safe(fn, *args, **kw) -> Result:
    try:
        return fn(*args, **kw)
    except Exception as e:  # noqa: BLE001 - một nhánh lỗi không làm hỏng cả câu
        return Result("", None, [f"ERROR: {e}"])


def solve_pot_vote(llm: LLM, blocks: list[Block], query: str, temperature: float = 0.7) -> Result:
    """Self-consistency: 2 lời giải song song (temp 0 và temp>0); nếu lệch thì thêm lời giải thứ 3 và lấy đa số."""
    from collections import Counter
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(2) as ex:
        runs = list(ex.map(lambda t: _safe(solve_pot, llm, blocks, query, temperature=t), [0.0, temperature]))
    if runs[0].answer and runs[0].answer == runs[1].answer:
        return Result(runs[0].answer, runs[0].raw, ["agree", runs[0].trace])
    runs.append(_safe(solve_pot, llm, blocks, query, temperature=temperature))
    votes = Counter(r.answer for r in runs if r.answer)
    if not votes:
        return Result("", None, ["no-answer"] + [r.trace for r in runs])
    best, n = votes.most_common(1)[0]
    if n == 1 and runs[0].answer:  # không có đa số -> tin lời giải temp 0
        best = runs[0].answer
    return Result(best, None, [f"vote {dict(votes)}"] + [r.trace for r in runs])


SOLVERS = {"direct": solve_direct, "pot": solve_pot, "pot_vote": solve_pot_vote, "hybrid": solve_hybrid}
