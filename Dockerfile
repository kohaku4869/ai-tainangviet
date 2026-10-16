# Bảng C - Hỏi đáp trên bảng tính Excel. Ảnh chạy trên Linux amd64, chỉ dùng CPU.
# Build: docker build --platform linux/amd64 -t excel-qa .
# Hệ thống chấm truyền 6 tham số: --xlsx-dir --queries --output --openrouter-key --openrouter-model --openrouter-base-url
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY excel_qa_agent ./excel_qa_agent

ENTRYPOINT ["python", "-m", "excel_qa_agent"]
