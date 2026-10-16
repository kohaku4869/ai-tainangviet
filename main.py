"""CLI: trả lời câu hỏi trên file Excel và xuất submission.csv.

Ví dụ:
    uv run python main.py --data-dir data --output submission.csv
    uv run python main.py --data-dir data --method hybrid --gold data/sample_submission.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

from xlqa.llm import LLM
from xlqa.solvers import SOLVERS, get_blocks


def find_inputs(data_dir: Path, queries: str | None, xlsx_dir: str | None) -> tuple[Path, Path]:
    q = Path(queries) if queries else data_dir / "queries.json"
    if xlsx_dir:
        x = Path(xlsx_dir)
    else:
        x = data_dir / "xlsx_files" if (data_dir / "xlsx_files").is_dir() else data_dir
    return q, x


def main() -> int:
    load_dotenv()
    ap = argparse.ArgumentParser(description="Excel QA -> submission.csv")
    ap.add_argument("--data-dir", default="data", help="Thư mục chứa queries.json và xlsx_files/")
    ap.add_argument("--queries", help="Đường dẫn queries.json (mặc định: <data-dir>/queries.json)")
    ap.add_argument("--xlsx-dir", help="Thư mục chứa .xlsx (mặc định: <data-dir>/xlsx_files)")
    ap.add_argument("--output", default="submission.csv")
    ap.add_argument("--method", default=os.getenv("XLQA_METHOD", "pot_vote"), choices=sorted(SOLVERS))
    ap.add_argument("--model", help="Ghi đè LLM_MODEL")
    ap.add_argument("--workers", type=int, default=int(os.getenv("XLQA_WORKERS", "8")))
    ap.add_argument("--gold", help="CSV đáp án đúng để tính Exact Match (tùy chọn)")
    ap.add_argument("--log", help="Ghi chi tiết từng câu ra file .jsonl (tùy chọn)")
    ap.add_argument("--ids", help="Chỉ chạy các id này (phân tách bằng dấu phẩy)")
    args = ap.parse_args()

    qpath, xdir = find_inputs(Path(args.data_dir), args.queries, args.xlsx_dir)
    queries = json.loads(qpath.read_text(encoding="utf-8"))
    if args.ids:
        keep = set(args.ids.split(","))
        queries = [q for q in queries if str(q["id"]) in keep]
    llm = LLM(model=args.model, max_concurrency=args.workers)
    solver = SOLVERS[args.method]

    def run_one(item: dict) -> dict:
        t0 = time.time()
        try:
            blocks = list(get_blocks(str(xdir / item["file_name"])))
            res = solver(llm, blocks, item["query"])
            ans, trace = res.answer, res.trace
        except Exception as e:  # noqa: BLE001 - luôn phải có một dòng kết quả
            ans, trace = "", [f"ERROR: {e}"]
        return {"id": item["id"], "answer": ans, "seconds": round(time.time() - t0, 2), "trace": trace}

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
    print(
        f"[{args.method} | {llm.model}] {len(results)} queries in {elapsed:.1f}s "
        f"({elapsed / n:.1f}s/q), LLM calls={llm.usage.calls}, tokens={llm.usage.total} "
        f"({llm.usage.total / n:.0f}/q: in={llm.usage.prompt_tokens}, out={llm.usage.completion_tokens}), "
        f"cost=${llm.usage.cost:.4f} (${llm.usage.cost / n:.5f}/q)",
        file=sys.stderr,
    )
    if args.gold:
        gold = {}
        with open(args.gold, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                gold[row["id"]] = row["answer"]
        correct = 0
        for r in results:
            g = gold.get(str(r["id"]))
            ok = g is not None and r["answer"].strip() == g.strip()
            correct += ok
            if not ok:
                print(f"  WRONG {r['id']}: got={r['answer']!r} gold={g!r}", file=sys.stderr)
        print(f"Exact Match: {correct}/{len(results)} = {correct / n:.1%}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
