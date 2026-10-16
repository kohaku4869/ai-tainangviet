"""Đóng gói bài nộp theo "Hướng dẫn nộp bài Bảng C": <team>.zip, Dockerfile nằm ngay ở gốc zip.

    uv run python scripts/make_submission.py --team team001

Chỉ đưa vào zip những gì Docker cần để build + README; không có .env / khóa API / dữ liệu.
"""

from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ["Dockerfile", "main.py", ".dockerignore", "requirements.txt", "README.md", "pyproject.toml", "uv.lock", "langgraph.json",
         ".env.example"]
DIRS = ["excel_qa_agent"]
SECRET_RE = re.compile(r"sk-or-[A-Za-z0-9-]{20,}|sk-[A-Za-z0-9]{32,}")
MAX_BYTES = 100 * 1024 * 1024


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", required=True, help="Tên đội, vd team001 -> team001.zip")
    ap.add_argument("--out-dir", default=str(ROOT / "dist"))
    args = ap.parse_args()

    paths: list[Path] = [ROOT / f for f in FILES if (ROOT / f).is_file()]
    for d in DIRS:
        paths += [p for p in (ROOT / d).rglob("*") if p.is_file() and "__pycache__" not in p.parts
                  and p.suffix != ".pyc"]
    for p in paths:  # chặn lọt khóa API vào bài nộp
        if p.suffix in {".py", ".md", ".txt", ".json", ".toml", ".example", ""} and SECRET_RE.search(
                p.read_text(encoding="utf-8", errors="ignore")):
            raise SystemExit(f"Possible API key found in {p.relative_to(ROOT)}; refusing to package.")

    out = Path(args.out_dir) / f"{args.team}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(paths):
            zf.write(p, p.relative_to(ROOT).as_posix())
    size = out.stat().st_size
    if size > MAX_BYTES:
        raise SystemExit(f"{out} is {size / 1e6:.1f} MB > 100 MB")
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert "Dockerfile" in names, "Dockerfile must be at the zip root"
    print(f"wrote {out} ({size / 1024:.0f} KB, {len(names)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
