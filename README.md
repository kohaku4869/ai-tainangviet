# AI26C0061: Hỏi đáp trên bảng tính Excel (Bảng C)

Đọc thư mục `.xlsx` cùng `queries.json` và xuất `submission.csv` (`id,answer`). LLM duy nhất được dùng là
`qwen/qwen3.7-flash` qua OpenRouter, key do hệ thống chấm truyền vào.

## Chạy bằng Docker (cách hệ thống chấm chạy)

```bash
docker build --platform linux/amd64 -t ai26c0061 .
docker run --rm -v <input>:/input:ro -v <output>:/output ai26c0061 \
  --xlsx-dir /input/xlsx_files --queries /input/queries.json --output /output/submission.csv \
  --openrouter-key <key> --openrouter-model qwen/qwen3.7-flash --openrouter-base-url https://openrouter.ai/api/v1
```

ENTRYPOINT là `python main.py`. `main.py` chỉ chuyển tham số sang CLI của package `excel_qa_agent`.

- **Kết quả:** CSV UTF-8 (không BOM) `id,answer`, mỗi id đúng một dòng, sắp id tăng dần, câu không trả lời được để trống.
  Chương trình luôn ghi file rồi mới thoát với mã 0; log ra stderr; không ghi gì vào `/input`.
- **Khóa API:** chỉ lấy từ `--openrouter-key`, không nằm trong bài nộp.
- **Song song:** mặc định xử lý 32 câu cùng lúc (`--workers` hoặc biến `XLQA_WORKERS`). RAM đo được khoảng 200 MB.

## Chạy ở máy (phát triển)

```bash
uv sync
cp .env.example .env   # điền OPENROUTER_API_KEY
uv run python main.py --data-dir data/public_2 --gold data/public_2/sample_submission.csv --log outputs/run.jsonl
```

Tùy chọn thêm khi phát triển:
- `--data-dir` (thư mục chứa `queries.json` và `xlsx_files/`)
- `--gold` (tính Exact Match)
- `--log` (ghi chi tiết từng câu ra `.jsonl`)
- `--ids` (chỉ chạy một số câu)
- `--mode auto|fast|agent` (ép đường đi)

Cấu hình LLM qua biến môi trường (khi không truyền `--openrouter-*`):

| Biến | Ý nghĩa |
|---|---|
| `LLM_PROVIDER` | `openrouter` (mặc định khi có `OPENROUTER_API_KEY`), `gemini`, `openai` (endpoint OpenAI-compatible tự host) |
| `OPENROUTER_API_KEY` / `GEMINI_API_KEY` / `LLM_API_KEY` | khóa API của provider tương ứng |
| `LLM_BASE_URL` | base URL cho provider `openai` |
| `LLM_MODEL` | mặc định `qwen/qwen3.7-flash` |
| `LLM_REASONING` | `none`/`low`/`medium`/`high` (mặc định `none` với openrouter: nhanh, ít token) |
| `XLQA_<TÊN>` | ghi đè tham số trong `Configuration`, vd `XLQA_AGENT_MAX_STEPS=10`, `XLQA_REQUEST_TIMEOUT=180` |

## Kiến trúc (LangGraph)

```
START ─┬─> load_workbook ─┐
       └─> parse_format  ─┴─> dispatch ─(bảng nhỏ, cấu trúc rõ)─> fast_solver ─(đồng thuận)─> finalize ─> END
                                 │                                  └─(không chắc)─┐
                                 └─(lớn / bất thường)──────────────────> agent <─> execute_code ─> finalize
```

- **`load_workbook`:** đọc Excel bằng code (không dùng LLM):
  - điền giá trị ô gộp, tính các công thức đơn giản;
  - chuyển chuỗi số thành số;
  - đoán các bảng: tiêu đề, header nhiều tầng đã làm phẳng, dữ liệu, chú thích, bảng xếp chồng.

  Bảng nhỏ và rõ ràng thì đi đường nhanh. Bảng lớn hoặc bất thường (bảng đặt cạnh nhau, không có header…) thì đi agent.
- **`parse_format`:** chạy song song với `load_workbook`. LLM đọc yêu cầu định dạng ở cuối câu hỏi, viết bằng **bất kỳ
  ngôn ngữ nào**, thành spec JSON (số chữ số thập phân, số nguyên, từ Có/Không, dấu %, chỉ lấy độ lớn…).
  Bộ định dạng cố định áp spec lên giá trị thô. Nếu LLM lỗi thì dùng regex tiếng Anh.
- **`fast_solver`:** 1 lời giải temperature 0 (LLM viết code pandas, chạy trong sandbox, tự sửa khi lỗi).
  Lời giải hỏng (code lỗi, đáp án bị từ chối) thì chuyển sang agent. `XLQA_FAST_SAMPLES=2` bật thêm lời giải temperature 0.7 để đối chiếu (đo trên public_2 và public_like: không đúng hơn mà tốn thêm khoảng 40% token).
- **`agent` ⇄ `execute_code`:** agent kiểu CodeAct, mỗi lượt viết một khối Python dùng các công cụ
  `overview()`, `view()`, `find()`, `grid()`, `table()`, `make_table()`, `final()`. Tối đa 8 lượt.
- **`finalize`:** chốt đáp án. Nếu agent hết lượt mà chưa gọi `final()` thì lấy dự phòng: ứng viên của đường nhanh,
  rồi biến kết quả trong code, rồi dòng in cuối.
- **Lỗi API** (timeout, 5xx…): chỉ làm hỏng lời giải gặp lỗi, không làm hỏng cả câu.

Prompt chỉ chứa chính sách diễn giải tổng quát, cộng quy ước chính thức của BTC (`doc/…Giải đáp thắc mắc…pdf`, câu 01:
trung bình "across all…" lấy trên tất cả các cột, kể cả cột Total).

```
main.py               # entrypoint (ENTRYPOINT ["python", "main.py"])
excel_qa_agent/
  graph/              # state.py (InputState / AgentState / OutputState), builder.py (build_graph, graph)
  config/             # configuration.py: Configuration (env + config["configurable"])
  prompts/            # templates.py: chính sách chung + prompt parse_format / fast / agent
  nodes/              # load_workbook, parse_format, dispatch, fast_solver, agent, execute_code, finalize, routing
  tools/              # workbook_tools (công cụ cho agent), session (sandbox theo từng câu)
  models/             # llm (ChatOpenAI cho OpenRouter / endpoint tự host), usage (token + chi phí)
  utils/              # excel_reader, formulas, table_detector, rendering, format_spec, answer_format,
                      # code_runner, validation, values
  cli.py              # chạy theo lô -> submission.csv
langgraph.json        # cho `langgraph dev`
```

## Kiểm thử

- `uv run python tests/test_agent_faults.py`: kiểm tra offline với model giả (lỗi API, đường dẫn header, agent không
  gọi `final()`).
- `uv run python scripts/score.py --pred out/submission.csv --gold data/public_2/sample_submission.csv`: chấm Exact
  Match và kiểm tra định dạng nộp bài.
- `tests/make_synthetic.py`: sinh bộ test tổng hợp có đáp án tính bằng code.

## Đóng gói bài nộp

```bash
uv export --no-hashes --format requirements-txt --no-dev --no-emit-project > requirements.txt
uv run python scripts/make_submission.py --team AI26C0061   # -> dist/AI26C0061.zip (Dockerfile ở gốc zip)
```
