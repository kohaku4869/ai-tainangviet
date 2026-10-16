# ai-tainang: Hỏi đáp trên bảng tính Excel

Đọc thư mục `.xlsx` cùng `queries.json` và xuất `submission.csv` (`id,answer`).

## Cài đặt

```bash
uv sync
cp .env.example .env   # rồi điền OPENROUTER_API_KEY (khi chấm thi)
```

## Chạy

```bash
uv run python main.py --data-dir <thư mục chứa queries.json và xlsx_files/> --output submission.csv
```

Các tùy chọn:
- `--method pot_vote|pot|direct|hybrid` (mặc định `pot_vote`)
- `--workers 8`
- `--queries`, `--xlsx-dir` để chỉ định đường dẫn riêng
- `--gold đáp_án.csv` để tính Exact Match
- `--log outputs/run.jsonl` để ghi chi tiết từng câu

## Cấu hình LLM (biến môi trường)

| Biến | Ý nghĩa |
|---|---|
| `LLM_PROVIDER` | `openrouter` (chấm thi), `gemini`, `openai` (endpoint OpenAI-compatible bất kỳ), `ollama` |
| `OPENROUTER_API_KEY` / `GEMINI_API_KEY` / `LLM_API_KEY` | khóa API (không đặt trong mã nguồn) |
| `LLM_BASE_URL` | ghi đè base URL (bắt buộc với `openai`) |
| `LLM_MODEL` | mặc định `qwen/qwen3.7-flash` (openrouter) |
| `LLM_REASONING` | `none`/`low`/`medium`/`high` (mặc định `none` với openrouter) |
| `LLM_TIMEOUT` | timeout mỗi request, tính bằng giây (mặc định 90) |

## Kiến trúc

1. **`xlqa/excel.py`**: chuẩn hóa Excel.
   - Điền giá trị ô gộp và tính các công thức đơn giản (tham chiếu ô, `+ - * /`, `SUM/AVERAGE/MIN/MAX/COUNT`) khi file không lưu sẵn giá trị.
   - Chuyển chuỗi số (`"1,234"`) thành số; ký hiệu `–` hoặc `�` thành giá trị rỗng.
   - Tách mỗi sheet thành các bảng: tiêu đề, header nhiều tầng đã làm phẳng, dòng dữ liệu, chú thích. Nhận diện được cả bảng xếp chồng trên một sheet.
   - Bảng được hiển thị dạng text gọn với số dòng Excel và chữ cái cột.
2. **`xlqa/solvers.py`**:
   - `pot`: LLM sinh code pandas, code được chạy và tự sửa khi lỗi (tối đa 2 lần).
   - `pot_vote`: chạy song song 2 lời giải `pot` (temperature 0 và 0.7). Nếu hai đáp án khớp thì chốt; nếu lệch thì chạy lời giải thứ 3 và lấy đa số.
   - `direct`: LLM đọc bảng và trả lời trực tiếp. `hybrid`: kết hợp `direct` và `pot`, lệch nhau thì gọi một lượt phân xử.
3. **`xlqa/formatting.py`**: chuẩn hóa đáp án theo yêu cầu trong câu hỏi.
   - Số nguyên không dấu phẩy, N chữ số thập phân, Yes/No, danh sách nối bằng `", "`.
   - Bỏ ký hiệu chú thích `(1)`.
   - Dùng đúng tên mục như câu hỏi đã liệt kê; đổi chữ cái cột hoặc đường dẫn header về tên cột.

## Kiểm thử

- `tests/oracle_check.py`: kiểm tra phần không dùng LLM bằng code viết tay (20/20).
- `tests/make_synthetic.py --out data/synth`: sinh 36 câu hỏi tổng hợp (đáp án tính bằng code) gồm nhiều sheet, nhiều bảng trên một sheet, bảng đặt cạnh nhau, header gộp, công thức, số dạng text, phân cấp bằng thụt lề.
  Chạy đánh giá: `uv run python main.py --data-dir data/synth --gold data/synth/answers.csv`.

---

# Giải pháp 2: `excel_qa_agent/` (LangGraph)

Graph tổng quát, không chứa quy ước riêng của bộ dữ liệu public:

```
START -> load_workbook --(bảng nhỏ, cấu trúc rõ)--> fast_solver --(các lời giải đồng thuận)--> finalize -> END
                      \--(lớn / bất thường / không đồng thuận)--> agent <-> execute_code --> finalize
```

Lỗi API (timeout, 5xx, hết credit) không làm hỏng cả câu: ở đường nhanh, lời giải lỗi API bị bỏ qua và lời giải còn
lại vẫn được dùng; agent gặp lỗi API thì dừng và `finalize` dùng đáp án ứng viên có sẵn. Kiểm tra offline:
`uv run python tests/test_agent_faults.py`.

```
excel_qa_agent/
  graph/              # state.py: InputState / AgentState / OutputState
                      # builder.py: build_graph() nối node + cạnh điều kiện, export `graph`
  config/             # configuration.py: Configuration (env + config["configurable"])
  prompts/            # templates.py: chính sách diễn giải chung + prompt fast/agent
  nodes/              # load_workbook, fast_solver, agent, execute_code, finalize, routing
  tools/              # workbook_tools (overview/view/find/grid/table/make_table/final), session
  models/             # llm (ChatOpenAI cho OpenRouter/Gemini/endpoint tự host), usage (token + cost)
  utils/              # excel_reader, formulas, table_detector, rendering, answer_format, code_runner, validation
  cli.py, __main__.py # chạy theo lô -> submission.csv
langgraph.json        # cho `langgraph dev`
```

Chạy:

```bash
uv run python -m excel_qa_agent --data-dir <thư mục dữ liệu> --output submission.csv
uv run python -m excel_qa_agent --data-dir data --gold data/sample_submission.csv --mode auto|fast|agent --log outputs/run.jsonl
```

Các tham số chỉnh qua biến môi trường `XLQA_<TÊN>`, ví dụ `XLQA_AGENT_MAX_STEPS=10`, `XLQA_FAST_SAMPLES=2`, `XLQA_FAST_PATH_MAX_CHARS=40000`.
