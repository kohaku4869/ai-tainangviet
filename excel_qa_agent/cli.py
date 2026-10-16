"""Chạy graph trên cả bộ câu hỏi và xuất submission.csv.

    uv run python -m excel_qa_agent --data-dir data --output submission.csv
    uv run python -m excel_qa_agent --data-dir data --gold data/sample_submission.csv --log outputs/agent.jsonl
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import find_dotenv, load_dotenv


def _inputs(args) -> tuple[list[dict], Path]:
    data_dir = Path(args.data_dir)
    qpath = Path(args.queries) if args.queries else data_dir / "queries.json"
    xdir = Path(args.xlsx_dir) if args.xlsx_dir else (
        data_dir / "xlsx_files" if (data_dir / "xlsx_files").is_dir() else data_dir)
    queries = json.loads(qpath.read_text(encoding="utf-8"))
    if args.ids:
        keep = set(args.ids.split(","))
        queries = [q for q in queries if str(q["id"]) in keep]
    return queries, xdir


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # console Windows (cp1252) không in được tiếng Việt
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv(find_dotenv(usecwd=True))
    from .config import Configuration
    from .graph import graph
    from .models.usage import UsageCallback
    from .tools.session import SESSIONS

    ap = argparse.ArgumentParser(prog="excel_qa_agent", description="Excel QA agent (LangGraph) -> submission.csv")
    ap.add_argument("--data-dir", default="data", help="Thư mục chứa queries.json và xlsx_files/")
    ap.add_argument("--queries", help="Đường dẫn queries.json")
    ap.add_argument("--xlsx-dir", help="Thư mục chứa các file .xlsx")
    ap.add_argument("--output", default="submission.csv")
    ap.add_argument("--workers", type=int, default=8, help="Số câu hỏi xử lý song song")
    ap.add_argument("--mode", choices=["auto", "fast", "agent"], help="Ép đường đi (mặc định auto)")
    ap.add_argument("--gold", help="CSV đáp án để tính Exact Match (tùy chọn)")
    ap.add_argument("--log", help="Ghi chi tiết từng câu ra .jsonl (tùy chọn)")
    ap.add_argument("--ids", help="Chỉ chạy các id này (phân tách bằng dấu phẩy)")
    args = ap.parse_args(argv)

    queries, xdir = _inputs(args)
    base_cfg = Configuration.from_env()
    if args.mode:
        base_cfg.mode = args.mode

    def run_one(item: dict) -> dict:
        usage = UsageCallback()
        t0 = time.time()
        try:
            out = graph.invoke(
                {"question_id": str(item["id"]), "question": item["query"],
                 "file_path": str(xdir / item["file_name"])},
                config={"configurable": {"_base": base_cfg}, "callbacks": [usage], "recursion_limit": 60},
            )
            answer, route, trace = out.get("answer", ""), out.get("route", ""), out.get("trace", [])
        except Exception as e:  # noqa: BLE001 - luôn có một dòng kết quả cho mỗi id
            answer, route, trace = "", "error", [f"ERROR: {type(e).__name__}: {e}"]
        finally:
            SESSIONS.close_owner(str(item["id"]))  # dọn phiên nếu graph dừng giữa chừng
        return {"id": item["id"], "answer": answer, "route": route, "seconds": round(time.time() - t0, 2),
                "usage": usage.as_dict(), "trace": trace}

    t_start = time.time()
    with ThreadPoolExecutor(max(1, args.workers)) as ex:
        results = list(ex.map(run_one, queries))
    elapsed = time.time() - t_start

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "answer"])
        for r in results:
            w.writerow([r["id"], r["answer"]])
    if args.log:
        Path(args.log).parent.mkdir(parents=True, exist_ok=True)
        with open(args.log, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    n = max(1, len(results))
    tok = sum(r["usage"]["input_tokens"] + r["usage"]["output_tokens"] for r in results)
    cost = sum(r["usage"]["cost"] for r in results)
    calls = sum(r["usage"]["calls"] for r in results)
    routes = Counter(r["route"] for r in results)
    print(f"[{base_cfg.model} | mode={base_cfg.mode}] {len(results)} queries in {elapsed:.1f}s ({elapsed / n:.2f}s/q), "
          f"routes={dict(routes)}, LLM calls={calls}, tokens={tok} ({tok / n:.0f}/q), "
          f"cost=${cost:.4f} (${cost / n:.5f}/q, max ${max((r['usage']['cost'] for r in results), default=0):.5f})",
          file=sys.stderr)
    if args.gold:
        with open(args.gold, encoding="utf-8-sig") as f:
            gold = {row["id"]: row["answer"] for row in csv.DictReader(f)}
        correct = 0
        for r in results:
            g = gold.get(str(r["id"]))
            ok = g is not None and r["answer"].strip() == g.strip()
            correct += ok
            if not ok:
                print(f"  WRONG {r['id']} [{r['route']}]: got={r['answer']!r} gold={g!r}", file=sys.stderr)
        print(f"Exact Match: {correct}/{len(results)} = {correct / n:.1%}", file=sys.stderr)
    return 0
