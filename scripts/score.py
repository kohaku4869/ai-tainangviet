"""Chấm Exact Match file kết quả với đáp án và kiểm tra định dạng nộp bài.

    uv run python scripts/score.py --pred out/submission.csv --gold data/public_2/sample_submission.csv
"""

from __future__ import annotations

import argparse
import csv
import sys


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--gold", required=True)
    args = ap.parse_args()

    with open(args.gold, encoding="utf-8-sig") as f:
        gold = {r["id"]: r["answer"] for r in csv.DictReader(f)}
    raw = open(args.pred, "rb").read()
    with open(args.pred, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    ids = [r["id"] for r in rows]

    print(f"BOM: {'YES (bad)' if raw.startswith(b'\xef\xbb\xbf') else 'no'} | rows: {len(rows)} | "
          f"unique ids: {len(set(ids)) == len(ids)} | missing ids: {sorted(set(gold) - set(ids))} | "
          f"sorted: {ids == sorted(ids, key=lambda x: int(x) if x.isdigit() else x)}")
    correct = 0
    for r in rows:
        g = gold.get(r["id"])
        if g is not None and r["answer"].strip() == g.strip():
            correct += 1
        else:
            print(f"  WRONG {r['id']}: got={r['answer']!r} gold={g!r}")
    print(f"Exact Match: {correct}/{len(gold)} = {correct / max(1, len(gold)):.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
