"""Chạy graph trên cả bộ câu hỏi và xuất submission.csv.

Cách BTC chạy (theo "Hướng dẫn nộp bài Bảng C"):
    python -m excel_qa_agent --xlsx-dir /input/xlsx_files --queries /input/queries.json \\
        --output /output/submission.csv --openrouter-key <key> \\
        --openrouter-model qwen/qwen3.7-flash --openrouter-base-url https://openrouter.ai/api/v1

Chạy thử ở máy (key lấy từ .env):
    uv run python -m excel_qa_agent --data-dir data/public_2 --gold data/public_2/sample_submission.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import find_dotenv, load_dotenv


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _id_key(qid) -> tuple:
    """Sắp id tăng dần: id dạng số theo giá trị số, id dạng chuỗi theo phần số (p4_q002 < p4_q010)."""
    s = str(qid)
    if re.fullmatch(r"\d+", s):
        return (0, int(s), s)
    return (1, [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)], s)


def _file_name(item: dict) -> str:
    for key in ("file_name", "file name", "filename", "file"):
        if item.get(key):
            return str(item[key])
    raise KeyError(f"query {item.get('id')!r} has no file_name")


def _parse_args(argv):
    ap = argparse.ArgumentParser(prog="excel_qa_agent", description="Excel QA agent (LangGraph) -> submission.csv")
    # --- tham số hệ thống chấm cung cấp
    ap.add_argument("--xlsx-dir", help="Thư mục chứa các file .xlsx")
    ap.add_argument("--queries", help="Đường dẫn queries.json")
    ap.add_argument("--output", default="submission.csv", help="Đường dẫn file kết quả CSV")
    ap.add_argument("--openrouter-key", help="OpenRouter API key (ưu tiên hơn biến môi trường)")
    ap.add_argument("--openrouter-model", help="Model, vd qwen/qwen3.7-flash")
    ap.add_argument("--openrouter-base-url", help="Base URL, vd https://openrouter.ai/api/v1")
    # --- tiện ích khi phát triển
    ap.add_argument("--data-dir", default="data", help="Thư mục chứa queries.json và xlsx_files/ (khi chạy thử)")
    ap.add_argument("--workers", type=int, default=int(os.getenv("XLQA_WORKERS", "32")),
                    help="Số câu hỏi xử lý song song")
    ap.add_argument("--mode", choices=["auto", "fast", "agent"], help="Ép đường đi (mặc định auto)")
    ap.add_argument("--gold", help="CSV đáp án để tính Exact Match (tùy chọn)")
    ap.add_argument("--log", help="Ghi chi tiết từng câu ra .jsonl (tùy chọn)")
    ap.add_argument("--ids", help="Chỉ chạy các id này (phân tách bằng dấu phẩy)")
    return ap.parse_args(argv)


def _apply_openrouter_args(args) -> None:
    """Tham số --openrouter-* của hệ thống chấm được ưu tiên hơn .env / biến môi trường."""
    if args.openrouter_key:
        os.environ["LLM_PROVIDER"] = "openrouter"
        os.environ["OPENROUTER_API_KEY"] = args.openrouter_key
    if args.openrouter_model:
        os.environ["LLM_MODEL"] = args.openrouter_model
    if args.openrouter_base_url:
        os.environ["OPENROUTER_BASE_URL"] = args.openrouter_base_url


def _write_submission(path: str, results: list[dict]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:  # UTF-8 không BOM, xuống dòng kiểu Unix
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "answer"])
        for r in sorted(results, key=lambda r: _id_key(r["id"])):
            w.writerow([r["id"], r["answer"] or ""])


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # console Windows (cp1252) không in được tiếng Việt
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = _parse_args(argv)
    load_dotenv(find_dotenv(usecwd=True))  # chỉ dùng khi chạy ở máy; trong Docker không có .env
    _apply_openrouter_args(args)

    data_dir = Path(args.data_dir)
    qpath = Path(args.queries) if args.queries else data_dir / "queries.json"
    xdir = Path(args.xlsx_dir) if args.xlsx_dir else (
        data_dir / "xlsx_files" if (data_dir / "xlsx_files").is_dir() else data_dir)
    queries = json.loads(qpath.read_text(encoding="utf-8-sig"))
    if args.ids:
        keep = set(args.ids.split(","))
        queries = [q for q in queries if str(q["id"]) in keep]
    # Mỗi id đúng một dòng: bỏ id trùng (giữ câu đầu tiên).
    seen: set[str] = set()
    queries = [q for q in queries if not (str(q["id"]) in seen or seen.add(str(q["id"])))]
    _log(f"{len(queries)} queries, xlsx dir: {xdir}")

    # Từ đây trở đi luôn ghi file kết quả (câu lỗi để trống), kể cả khi cấu hình LLM hỏng.
    results: list[dict] = []
    t_start = time.time()
    base_cfg = None
    try:
        from .config import Configuration
        from .graph import graph
        from .models.usage import UsageCallback
        from .tools.session import SESSIONS

        base_cfg = Configuration.from_env()
        if args.mode:
            base_cfg.mode = args.mode
        _log(f"model={base_cfg.model} provider={base_cfg.provider} mode={base_cfg.mode} workers={args.workers}")

        def run_one(item: dict) -> dict:
            usage = UsageCallback()
            t0 = time.time()
            qid = str(item["id"])
            try:
                out = graph.invoke(
                    {"question_id": qid, "question": item["query"], "file_path": str(xdir / _file_name(item))},
                    config={"configurable": {"_base": base_cfg}, "callbacks": [usage], "recursion_limit": 60},
                )
                answer, route, trace = out.get("answer", ""), out.get("route", ""), out.get("trace", [])
            except Exception as e:  # noqa: BLE001 - luôn có một dòng kết quả cho mỗi id
                answer, route, trace = "", "error", [f"ERROR: {type(e).__name__}: {e}"]
            finally:
                SESSIONS.close_owner(qid)  # dọn phiên nếu graph dừng giữa chừng
            r = {"id": item["id"], "answer": answer, "route": route, "seconds": round(time.time() - t0, 2),
                 "usage": usage.as_dict(), "trace": trace}
            _log(f"[{qid}] {route} {r['seconds']}s -> {answer!r}")
            return r

        with ThreadPoolExecutor(max(1, args.workers)) as ex:
            results = list(ex.map(run_one, queries))
    except Exception as e:  # noqa: BLE001 - lỗi cấu hình/khởi tạo: vẫn ghi file với đáp án rỗng
        _log(f"FATAL: {type(e).__name__}: {e}")
        done = {str(r["id"]) for r in results}
        results += [{"id": q["id"], "answer": "", "route": "error", "seconds": 0.0,
                     "usage": {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}, "trace": [str(e)]}
                    for q in queries if str(q["id"]) not in done]
    elapsed = time.time() - t_start

    _write_submission(args.output, results)
    _log(f"wrote {len(results)} rows to {args.output}")
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
    model = base_cfg.model if base_cfg else "?"
    _log(f"[{model}] {len(results)} queries in {elapsed:.1f}s ({elapsed / n:.2f}s/q), routes={dict(routes)}, "
         f"LLM calls={calls}, tokens={tok} ({tok / n:.0f}/q), "
         f"cost=${cost:.4f} (${cost / n:.5f}/q, max ${max((r['usage']['cost'] for r in results), default=0):.5f})")
    if args.gold:
        with open(args.gold, encoding="utf-8-sig") as f:
            gold = {row["id"]: row["answer"] for row in csv.DictReader(f)}
        correct = 0
        for r in sorted(results, key=lambda r: _id_key(r["id"])):
            g = gold.get(str(r["id"]))
            ok = g is not None and r["answer"].strip() == g.strip()
            correct += ok
            if not ok:
                _log(f"  WRONG {r['id']} [{r['route']}]: got={r['answer']!r} gold={g!r}")
        _log(f"Exact Match: {correct}/{len(results)} = {correct / n:.1%}")
    return 0
