"""Entrypoint của bài nộp (Dockerfile: ENTRYPOINT ["python", "main.py"]).

Hệ thống chấm chạy:
    python main.py --xlsx-dir /input/xlsx_files --queries /input/queries.json --output /output/submission.csv \\
        --openrouter-key <key> --openrouter-model qwen/qwen3.7-flash --openrouter-base-url https://openrouter.ai/api/v1

Toàn bộ logic nằm trong package `excel_qa_agent` (LangGraph agent); file này chỉ chuyển tham số sang CLI của agent.
"""

from excel_qa_agent.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
