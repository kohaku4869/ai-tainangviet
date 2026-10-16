SYSTEM = (
    "You are a precise data analyst answering questions about tables extracted from Excel spreadsheets. "
    "Each table is shown with its column legend (Excel column letter -> flattened multi-level header) "
    "and its rows prefixed by the Excel row number. Rows that contain only a label (e.g. 'Men', 'Women', 'TOTAL') "
    "are section headers: the rows below them belong to that section until the next section header. "
    "Indented labels are children of the less-indented label above them."
)

GUIDELINES = """Guidelines:
- Locate the exact rows/columns the question refers to; pay attention to the section a row belongs to.
- Use the values exactly as stored in the table (units are as given, do not rescale thousands).
- "Total/sum across all X": if the table already has a total row/column for X, use that value.
- "Average/mean across all X": take the simple mean of every column (or row) shown for X, including subtotal
  columns such as "... > Total"; do not drop hierarchy levels and do not weight.
- For a text answer, return the label exactly as it appears in the table, without footnote markers like (1).
  If the question itself names the items (e.g. "rank Agriculture, Manufacturing, and Construction"), answer with
  the names exactly as written in the question.
- When counting, filtering, averaging or ranking individual records, exclude summary rows such as "Total",
  "All items" or subtotal rows (unless the question asks about them).
- When the answer is a row (e.g. "which warehouse/branch/item"), return its label text, never the row number.
- Ages: if each person has a birth date and another event date (e.g. admission date), a person's age is measured
  at that event date (event date - birth date), even if the question does not repeat it. Youngest = smallest age,
  oldest = largest age. Double-check the sort direction.
- Follow the requested answer format exactly (e.g. only the last name, integer, decimals, order of items)."""

DIRECT_USER = """{tables}

Question: {query}

{guidelines}

Reason briefly (cite the Excel rows/columns you use and show any arithmetic), then finish with a final line:
ANSWER: <final answer only>"""

POT_USER = """{tables}

In Python you have:
- `tables`: dict mapping table name (e.g. "{first_name}") -> pandas DataFrame
- `df`: the first table ({first_name})
- `headers`: dict table name -> {{column letter: header text}} (the legend above)
Each DataFrame has index = Excel row number (int) and columns = Excel column letters (as in the legend above).
Numeric columns are numeric dtype, date columns are datetime64, label columns are strings (NaN when empty).

Question: {query}

{guidelines}

Write Python code that computes the answer and assigns it to a variable named `answer`
(a number, a string, or a list for multi-part answers in the requested order). When the answer is a column
(e.g. an industry or category that is a column header), return its header name, never the column letter. Prefer selecting cells by
explicit row number and column letter (e.g. `df.loc[25, 'E']`) after locating them in the printed table,
and use pandas for sorting/aggregation over many rows. Give 1-3 lines of reasoning, then one ```python block."""

FIX_USER = """Running your code failed:
{error}

Fix the code. Reply with one corrected ```python block that assigns `answer`."""

EMPTY_USER = """Your code ran but `answer` is empty ({value!r}). Check the row/column selection and reply with one corrected ```python block that assigns `answer`."""

JUDGE_USER = """{tables}

Question: {query}

Two candidate solutions disagree.

Candidate A (read directly from the table):
{a_text}
=> {a_answer}

Candidate B (computed with Python code):
```python
{b_code}
```
=> {b_answer}

{guidelines}

Check the relevant cells yourself and decide the correct answer. It may be A, B, or something else.
Reason briefly, then finish with a final line:
ANSWER: <final answer only>"""
