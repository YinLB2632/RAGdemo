# MarkItDown Loader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 Microsoft MarkItDown 把 `data/` 下多格式文档统一转换为 Markdown，Loader 命中 `.md` 缓存缺失则触发转换；保留原文件的页码/幻灯片/工作表等 metadata；让 LangChain 的 `RecursiveCharacterTextSplitter` 切分后的 chunk 仍携带语义结构。

**Architecture:** 新增 `utils/markdown_converter.py` 单一职责（任意文件 → 含 YAML frontmatter 的 Markdown）；`utils/file_handler.py` 中 8 个 Loader 改造为先尝试 `data/<basename>.md` 缓存、缺失则调用 `convert_to_markdown` 生成；新增 `markdown_loader` 解析 frontmatter；`rag/vector_store.py` 中 `get_file_documents` dispatch 表简化为只匹配 `.md`。产物分两目录：`data_orig/`（gitignore，原始文件） + `data/`（git 追踪，Markdown 产物）。

**Tech Stack:** Python 3.x, `markitdown[all]` 0.1.x, LangChain `langchain-text-splitters`, LangChain Chroma, `pdfplumber`, `python-pptx`, `openpyxl`, `pytest`。

## Global Constraints

- 切分参数（`config/chroma.yml`）：`chunk_size: 200`、`chunk_overlap: 20`、`separators: ["\n\n", "\n", ".", "!", "?", "。", "！", "？", " ", ""]` —— 不改动。
- 所有日志统一通过 `utils/logger_handler.logger`，输出到 `logs/` 与控制台 —— 不新增 logger 实例。
- frontmatter 解析自己实现（约 30 行），不引入 `python-frontmatter` 等新依赖。
- 不传任何 LLM client 给 MarkItDown（关闭 OCR/AI 增强），不引入网络调用。
- 不实现自动重新转换；`data/<name>.md` 是否存在即为天然标记。
- `data_orig/` 加入 `.gitignore`；`data/*.md` 纳入 git 追踪。
- 每个 Loader 函数仍保留（保持单测可观察的边界），仅实现改为「缓存优先 + 缺失转换」。
- 测试使用 `pytest`，新增与改造统一定位在 `tests/test_agent_tools.py`。
- 每个 Task 结束后 git commit 一次。

---

## File Structure

| 文件 | 类型 | 职责 |
|---|---|---|
| `utils/markdown_converter.py` | 新建 | `convert_to_markdown(path) -> str`：任意格式 → Markdown + YAML frontmatter |
| `utils/file_handler.py` | 改造 | 8 个 Loader 改缓存优先；新增 `markdown_loader`、`_read_markdown_with_frontmatter`、`_write_markdown_cache`、frontmatter 解析 helper |
| `rag/vector_store.py` | 改造 | `get_file_documents` 只 dispatch `.md` |
| `config/chroma.yml` | 改造 | `allow_knowledge_file_type: ["md"]`；新增 `data_orig_path: data_orig` |
| `requirements.txt` | 改造 | 新增 `markitdown[all]` |
| `.gitignore` | 改造 | 新增 `data_orig/` |
| `tests/test_agent_tools.py` | 改造 | 调整 3 个旧测试；新增 7 个测试 |
| `data_orig/` | 新建 | 存放 11 个原始文件（从 `data/` 迁移） |
| `data/` | 改造 | 仅存 `.md` 产物（git 追踪） |

---

### Task 1: 安装 markitdown 并加入 requirements.txt

**Files:**
- Modify: `requirements.txt`
- (无测试)

**Interfaces:**
- Produces: `markitdown[all]` 在 `requirements.txt` 中存在；`markitdown` 可被 `import markitdown` 导入。

- [ ] **Step 1: 验证 markitdown 已可被 import**

Run:
```bash
python -c "import markitdown; print(markitdown.__version__ if hasattr(markitdown, '__version__') else 'ok')"
```
Expected: 输出版本号或 `ok`（依赖此前手动 `pip install`）。若 `ModuleNotFoundError`，先运行 `pip install "markitdown[all]"` 再继续。

- [ ] **Step 2: 在 requirements.txt 新增一行**

Read `requirements.txt`，在末尾追加：

```
markitdown[all]
```

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "deps: add markitdown[all]"
```

---

### Task 2: 新增 utils/markdown_converter.py 骨架与 frontmatter 解析 helper

**Files:**
- Create: `utils/markdown_converter.py`
- Test: `tests/test_markdown_converter.py`

**Interfaces:**
- Consumes: 无（无外部依赖此 Task 引入）。
- Produces:
  - `convert_to_markdown(source_path: str) -> str`：将任意文件转为 Markdown。**本 Task 仅声明签名 + 占位实现返回原内容。**
  - `_parse_frontmatter(text: str) -> tuple[dict[str, Any], str]`：解析 frontmatter，返回 (metadata, body)。

- [ ] **Step 1: 写失败测试**

Create `tests/test_markdown_converter.py`:

```python
from utils.markdown_converter import _parse_frontmatter


def test_parse_frontmatter_returns_metadata_and_body():
    text = (
        "---\n"
        "source: a.txt\n"
        "file_type: txt\n"
        "---\n"
        "正文开始\n第二行\n"
    )

    metadata, body = _parse_frontmatter(text)

    assert metadata == {"source": "a.txt", "file_type": "txt"}
    assert body == "正文开始\n第二行\n"


def test_parse_frontmatter_without_block_returns_empty_metadata_and_full_body():
    text = "无 frontmatter 的纯文本"

    metadata, body = _parse_frontmatter(text)

    assert metadata == {}
    assert body == "无 frontmatter 的纯文本"


def test_parse_frontmatter_logs_warning_and_skips_when_block_is_malformed(caplog):
    text = (
        "---\n"
        "source: a.txt\n"
        "  bad indent: : :\n"
        "---\n"
        "正文\n"
    )

    with caplog.at_level("WARNING"):
        metadata, body = _parse_frontmatter(text)

    assert metadata == {}
    assert body == text
    assert any("frontmatter" in record.message.lower() for record in caplog.records)
```

- [ ] **Step 2: 跑测试，确认失败**

Run:
```bash
pytest tests/test_markdown_converter.py -v
```
Expected: `ModuleNotFoundError: No module named 'utils.markdown_converter'` 或 `ImportError`。

- [ ] **Step 3: 实现 utils/markdown_converter.py 骨架**

Create `utils/markdown_converter.py`:

```python
from __future__ import annotations

import logging
import os
from typing import Any

from utils.logger_handler import logger


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """解析 Markdown 文本开头的 YAML frontmatter。

    返回 (metadata, body)。无 frontmatter 时 metadata 为空 dict。
    frontmatter 损坏时 logger 记录 WARNING 并跳过 frontmatter，整段作 body。
    """
    if not text.startswith("---"):
        return {}, text

    lines = text.splitlines(keepends=True)
    # 找第一个 '---' 之后的下一个 '---'
    end_index = None
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            end_index = i
            break

    if end_index is None:
        return {}, text

    frontmatter_lines = lines[1:end_index]
    body = "".join(lines[end_index + 1 :])

    metadata: dict[str, Any] = {}
    for raw in frontmatter_lines:
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        if ":" not in line:
            logger.warning(
                "frontmatter 解析失败：跳过该 frontmatter，行=%r", line
            )
            return {}, text
        key, _, value = line.partition(":")
        metadata[key.strip()] = value.strip()

    return metadata, body


def convert_to_markdown(source_path: str) -> str:
    """占位实现：返回文件原内容。后续 Task 替换为真正的 MarkItDown 调用。"""
    with open(source_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()
```

- [ ] **Step 4: 跑测试，确认通过**

Run:
```bash
pytest tests/test_markdown_converter.py -v
```
Expected: 3 passed。

- [ ] **Step 5: Commit**

```bash
git add utils/markdown_converter.py tests/test_markdown_converter.py
git commit -m "feat: add markdown_converter skeleton and frontmatter parser"
```

---

### Task 3: 实现 convert_to_markdown 通用调用

**Files:**
- Modify: `utils/markdown_converter.py`
- Test: `tests/test_markdown_converter.py`

**Interfaces:**
- Consumes: `_parse_frontmatter`（Task 2）。
- Produces: `convert_to_markdown(path: str) -> str` 调用 `MarkItDown().convert(path).text_content`，并在 frontmatter 不存在时插入基础 frontmatter（`source` / `file_type` / `converted_by`）。

- [ ] **Step 1: 写失败测试**

Append to `tests/test_markdown_converter.py`:

```python
from utils.markdown_converter import convert_to_markdown


def test_convert_to_markdown_inserts_basic_frontmatter_for_txt(tmp_path):
    src = tmp_path / "note.txt"
    src.write_text("hello\nworld\n", encoding="utf-8")

    result = convert_to_markdown(str(src))

    assert result.startswith("---\n")
    assert "source: note.txt" in result
    assert "file_type: txt" in result
    assert "converted_by: markitdown" in result
    assert "hello" in result


def test_convert_to_markdown_raises_and_logs_error_on_failure(tmp_path, caplog):
    import pytest

    src = tmp_path / "broken.txt"
    src.write_text("content", encoding="utf-8")

    def boom(_self, _path):
        raise RuntimeError("simulated markitdown failure")

    from unittest.mock import patch

    with patch("utils.markdown_converter.MarkItDown.convert", boom):
        with caplog.at_level("ERROR"):
            with pytest.raises(RuntimeError, match="simulated markitdown failure"):
                convert_to_markdown(str(src))

    assert any("simulated markitdown failure" in r.message for r in caplog.records)
```

- [ ] **Step 2: 跑测试，确认失败**

Run:
```bash
pytest tests/test_markdown_converter.py -v
```
Expected: `test_convert_to_markdown_inserts_basic_frontmatter_for_txt` 失败（因为当前占位实现直接返回原内容，没有 frontmatter）；`test_convert_to_markdown_raises_and_logs_error_on_failure` 失败（因为当前不调用 `MarkItDown.convert`）。

- [ ] **Step 3: 实现真正的 convert_to_markdown**

Modify `utils/markdown_converter.py`，把 `convert_to_markdown` 替换为：

```python
from markitdown import MarkItDown

_CONVERTER = MarkItDown()


def convert_to_markdown(source_path: str) -> str:
    """把任意受支持文件转换为含 YAML frontmatter 的 Markdown。

    失败时通过 logger 记录 ERROR（含 traceback）并抛出原异常。
    """
    file_name = os.path.basename(source_path)
    _, ext = os.path.splitext(source_path)
    file_type = ext.lstrip(".").lower() or "unknown"

    try:
        result = _CONVERTER.convert(source_path)
        raw_text = result.text_content
    except Exception as exc:
        logger.error(
            "Markdown 转换失败：%s 错误=%s", source_path, exc, exc_info=True
        )
        raise

    if raw_text.startswith("---"):
        # MarkItDown 已经输出 frontmatter（部分格式可能），原样返回
        return raw_text

    frontmatter_lines = [
        "---",
        f"source: {file_name}",
        f"file_type: {file_type}",
        "converted_by: markitdown",
        "---",
        "",
    ]
    return "\n".join(frontmatter_lines) + raw_text
```

- [ ] **Step 4: 跑测试，确认通过**

Run:
```bash
pytest tests/test_markdown_converter.py -v
```
Expected: 全部 5 个测试通过。

- [ ] **Step 5: Commit**

```bash
git add utils/markdown_converter.py tests/test_markdown_converter.py
git commit -m "feat: convert files to markdown with basic frontmatter"
```

---

### Task 4: PDF/PPTX/XLSX 结构化 frontmatter

**Files:**
- Modify: `utils/markdown_converter.py`
- Test: `tests/test_markdown_converter.py`

**Interfaces:**
- Consumes: `convert_to_markdown`（Task 3）。
- Produces: `convert_to_markdown` 在 PDF 输入时 frontmatter 含 `page_count` 与 `pages`、正文中用 `---` 分页；在 PPTX 输入时 frontmatter 含 `slides`、正文中每张幻灯片用 `## Slide N` 起头；在 XLSX 输入时 frontmatter 含 `sheets`、正文中每个工作表用 `## Sheet: <name>` 起头。

- [ ] **Step 1: 写失败测试**

Append to `tests/test_markdown_converter.py`:

```python
from openpyxl import Workbook
from pptx import Presentation
import pypdf


def _make_pdf(tmp_path, pages):
    path = tmp_path / "mini.pdf"
    writer = pypdf.PdfWriter()
    for text in pages:
        writer.add_blank_page(width=72, height=72)
        writer.pages[-1].extract_text = lambda _t=text: _t  # placeholder
    writer.write(str(path))
    return path


def test_convert_to_markdown_pdf_appends_pages_metadata(tmp_path, monkeypatch):
    # 简化：构造一个真实 PDF 但 frontmatter 验证不依赖 MarkItDown 内部解析。
    # 这里改为验证 _enrich_pdf_metadata helper。
    from utils.markdown_converter import _enrich_pdf_metadata

    # 准备 PDF
    path = _make_pdf(tmp_path, ["第 1 页内容", "第 2 页内容"])

    frontmatter = {"source": "mini.pdf", "file_type": "pdf"}
    body = "MarkItDown 抽取出来的纯文本\n"

    new_fm, new_body = _enrich_pdf_metadata(str(path), frontmatter, body)

    assert "page_count" in new_fm
    assert "pages" in new_fm
    assert isinstance(new_fm["pages"], list)
    assert "第 1 页" in new_body or "页" in new_body


def test_convert_to_markdown_pptx_appends_slides_metadata(tmp_path):
    from utils.markdown_converter import _enrich_pptx_metadata

    path = tmp_path / "mini.pptx"
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = "Slide Title"
    slide.placeholders[1].text = "Slide Body"
    presentation.save(str(path))

    frontmatter = {"source": "mini.pptx", "file_type": "pptx"}
    body = "MarkItDown 抽取出来的文本\n"

    new_fm, new_body = _enrich_pptx_metadata(str(path), frontmatter, body)

    assert "slides" in new_fm
    assert new_fm["slides"] == [1]
    assert "Slide Title" in new_body or "## Slide 1" in new_body


def test_convert_to_markdown_xlsx_appends_sheets_metadata(tmp_path):
    from utils.markdown_converter import _enrich_xlsx_metadata

    path = tmp_path / "mini.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Params"
    worksheet.append(["topic", "value"])
    worksheet.append(["spreadsheet smoke", 42])
    workbook.save(str(path))

    frontmatter = {"source": "mini.xlsx", "file_type": "xlsx"}
    body = "spreadsheet smoke 42\n"

    new_fm, new_body = _enrich_xlsx_metadata(str(path), frontmatter, body)

    assert new_fm["sheets"] == ["Params"]
    assert "Params" in new_body or "Sheet" in new_body
```

- [ ] **Step 2: 跑测试，确认失败**

Run:
```bash
pytest tests/test_markdown_converter.py -v
```
Expected: 3 个新增测试因 `ImportError: cannot import name '_enrich_pdf_metadata'` 失败。

- [ ] **Step 3: 实现 enrich helper**

Modify `utils/markdown_converter.py`，新增 3 个 helper：

```python
def _enrich_pdf_metadata(source_path: str, frontmatter: dict[str, Any], body: str) -> tuple[dict[str, Any], str]:
    import pypdf

    try:
        reader = pypdf.PdfReader(source_path)
        page_numbers = list(range(1, len(reader.pages) + 1))
    except Exception as exc:
        logger.warning("PDF 元信息读取失败：%s 错误=%s", source_path, exc)
        return frontmatter, body

    frontmatter["page_count"] = len(page_numbers)
    frontmatter["pages"] = page_numbers

    # 用 --- 分页提示，便于阅读
    page_bodies: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        page_bodies.append(f"\n## Page {index}\n\n{text.strip()}\n")

    return frontmatter, body + "\n---\n".join(page_bodies) + "\n"


def _enrich_pptx_metadata(source_path: str, frontmatter: dict[str, Any], body: str) -> tuple[dict[str, Any], str]:
    from pptx import Presentation

    try:
        presentation = Presentation(source_path)
        slides = list(presentation.slides)
    except Exception as exc:
        logger.warning("PPTX 元信息读取失败：%s 错误=%s", source_path, exc)
        return frontmatter, body

    frontmatter["slides"] = list(range(1, len(slides) + 1))

    slide_blocks: list[str] = []
    for index, slide in enumerate(slides, start=1):
        texts: list[str] = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                texts.append(shape.text.strip())
        slide_blocks.append(f"\n## Slide {index}\n\n" + "\n".join(texts) + "\n")

    return frontmatter, body + "\n---\n".join(slide_blocks) + "\n"


def _enrich_xlsx_metadata(source_path: str, frontmatter: dict[str, Any], body: str) -> tuple[dict[str, Any], str]:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(source_path, read_only=True, data_only=True)
    except Exception as exc:
        logger.warning("XLSX 元信息读取失败：%s 错误=%s", source_path, exc)
        return frontmatter, body

    sheet_blocks: list[str] = []
    sheet_names: list[str] = []
    try:
        for worksheet in workbook.worksheets:
            sheet_names.append(worksheet.title)
            rows: list[str] = []
            for row in worksheet.iter_rows(values_only=True):
                cells = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
                if cells:
                    rows.append(" | ".join(cells))
            sheet_blocks.append(f"\n## Sheet: {worksheet.title}\n\n" + "\n".join(rows) + "\n")
    finally:
        workbook.close()

    frontmatter["sheets"] = sheet_names
    return frontmatter, body + "\n---\n".join(sheet_blocks) + "\n"
```

并在 `convert_to_markdown` 末尾追加：

```python
    if file_type == "pdf":
        frontmatter, body = _parse_frontmatter(result_text if result_text.startswith("---") else "\n".join(frontmatter_lines) + result_text)
        frontmatter, body = _enrich_pdf_metadata(source_path, frontmatter, body)
        return _compose_with_frontmatter(frontmatter, body)

    if file_type == "pptx":
        frontmatter, body = _parse_frontmatter(result_text if result_text.startswith("---") else "\n".join(frontmatter_lines) + result_text)
        frontmatter, body = _enrich_pptx_metadata(source_path, frontmatter, body)
        return _compose_with_frontmatter(frontmatter, body)

    if file_type == "xlsx":
        frontmatter, body = _parse_frontmatter(result_text if result_text.startswith("---") else "\n".join(frontmatter_lines) + result_text)
        frontmatter, body = _enrich_xlsx_metadata(source_path, frontmatter, body)
        return _compose_with_frontmatter(frontmatter, body)

    return result_text
```

并新增 helper：

```python
def _compose_with_frontmatter(frontmatter: dict[str, Any], body: str) -> str:
    lines = ["---"]
    for key, value in frontmatter.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append(body.lstrip("\n"))
    return "\n".join(lines)
```

> 注：上面 `convert_to_markdown` 内重复解析仅为了让占位结构清晰，实现者可重构为更紧凑的版本（不影响行为即可）。

- [ ] **Step 4: 跑测试，确认通过**

Run:
```bash
pytest tests/test_markdown_converter.py -v
```
Expected: 全部测试通过（含 Task 3 的 5 个 + 本 Task 的 3 个）。

- [ ] **Step 5: Commit**

```bash
git add utils/markdown_converter.py tests/test_markdown_converter.py
git commit -m "feat: enrich pdf/pptx/xlsx frontmatter with structure metadata"
```

---

### Task 5: 在 utils/file_handler.py 增加 markdown_loader 与 frontmatter 解析

**Files:**
- Modify: `utils/file_handler.py`
- Test: `tests/test_file_handler.py`（新建）

**Interfaces:**
- Consumes: `markdown_converter._parse_frontmatter`（Task 2）。
- Produces:
  - `markdown_loader(md_path: str) -> list[Document]`：解析 `.md`，frontmatter 进 `metadata`，正文进 `page_content`。
  - `_write_markdown_cache(md_path: str, content: str) -> None`：写文件，UTF-8。
  - `_read_markdown_with_frontmatter(md_path: str) -> list[Document]`：仅读 + 解析。

- [ ] **Step 1: 写失败测试**

Create `tests/test_file_handler.py`:

```python
from langchain_core.documents import Document
from utils.file_handler import (
    _read_markdown_with_frontmatter,
    _write_markdown_cache,
    markdown_loader,
)


def test_write_and_read_markdown_round_trip(tmp_path):
    path = tmp_path / "note.md"
    content = (
        "---\n"
        "source: note.txt\n"
        "file_type: txt\n"
        "---\n"
        "正文第一行\n第二行\n"
    )
    _write_markdown_cache(str(path), content)

    documents = _read_markdown_with_frontmatter(str(path))

    assert len(documents) == 1
    assert isinstance(documents[0], Document)
    assert documents[0].page_content == "正文第一行\n第二行\n"
    assert documents[0].metadata == {"source": "note.txt", "file_type": "txt"}


def test_markdown_loader_handles_missing_frontmatter(tmp_path):
    path = tmp_path / "no_fm.md"
    path.write_text("纯文本\n", encoding="utf-8")

    documents = markdown_loader(str(path))

    assert len(documents) == 1
    assert documents[0].page_content == "纯文本\n"
    assert documents[0].metadata.get("source") is None or documents[0].metadata == {}
```

- [ ] **Step 2: 跑测试，确认失败**

Run:
```bash
pytest tests/test_file_handler.py -v
```
Expected: `ImportError`（当前 `utils/file_handler.py` 还没有这些函数）。

- [ ] **Step 3: 在 utils/file_handler.py 末尾追加**

Append to `utils/file_handler.py`:

```python
from utils.markdown_converter import _parse_frontmatter


def _write_markdown_cache(md_path: str, content: str) -> None:
    """把 Markdown 文本写入指定路径。"""
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)


def _read_markdown_with_frontmatter(md_path: str) -> list[Document]:
    """读取 .md 文件并解析 frontmatter，返回单 Document 列表。"""
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()

    metadata, body = _parse_frontmatter(text)
    metadata.setdefault("source", os.path.basename(md_path))
    return [Document(page_content=body, metadata=metadata)]


def markdown_loader(md_path: str) -> list[Document]:
    """纯 Markdown loader：不调 MarkItDown，仅解析 frontmatter。"""
    return _read_markdown_with_frontmatter(md_path)
```

- [ ] **Step 4: 跑测试，确认通过**

Run:
```bash
pytest tests/test_file_handler.py -v
```
Expected: 2 passed。

- [ ] **Step 5: Commit**

```bash
git add utils/file_handler.py tests/test_file_handler.py
git commit -m "feat: add markdown_loader with frontmatter parsing"
```

---

### Task 6: 让 8 个 Loader 走「缓存优先 + 缺失转换」

**Files:**
- Modify: `utils/file_handler.py`
- Test: `tests/test_file_handler.py`

**Interfaces:**
- Consumes: `markdown_converter.convert_to_markdown`（Task 3）、`markdown_loader` 等（Task 5）。
- Produces: 8 个 Loader（`txt_loader`、`pdf_loader`、`markdown_loader`、`docx_loader`、`csv_loader`、`excel_loader`、`pptx_loader`、`html_loader`）当 `data/<basename>.md` 存在时直接读取；缺失时调 `convert_to_markdown` 写入并返回。

> `markdown_loader` 自身不调转换，仅解析 frontmatter；其余 7 个 Loader 走转换。

- [ ] **Step 1: 写失败测试**

Append to `tests/test_file_handler.py`:

```python
import os
from unittest.mock import patch

from utils import file_handler


def test_pdf_loader_prefers_markdown_cache(tmp_path):
    src = tmp_path / "manual.pdf"
    src.write_bytes(b"%PDF-1.4\n%fake content\n")

    cache = tmp_path / "manual.md"
    cache.write_text(
        "---\nsource: manual.pdf\nfile_type: pdf\n---\n缓存内容\n",
        encoding="utf-8",
    )

    with patch("utils.file_handler.convert_to_markdown") as mock_convert:
        documents = file_handler.pdf_loader(str(src))

    mock_convert.assert_not_called()
    assert len(documents) == 1
    assert "缓存内容" in documents[0].page_content
    assert documents[0].metadata["source"] == "manual.pdf"


def test_txt_loader_falls_back_to_conversion_when_cache_missing(tmp_path):
    src = tmp_path / "note.txt"
    src.write_text("hello", encoding="utf-8")

    with patch("utils.file_handler.convert_to_markdown", return_value="---\nsource: note.txt\nfile_type: txt\n---\nhello\n") as mock_convert:
        documents = file_handler.txt_loader(str(src))

    mock_convert.assert_called_once_with(str(src))
    assert documents[0].page_content == "hello\n"


def test_html_loader_creates_cache_file(tmp_path):
    src = tmp_path / "page.html"
    src.write_text("<html><body>正文</body></html>", encoding="utf-8")

    with patch("utils.file_handler.convert_to_markdown", return_value="---\nsource: page.html\nfile_type: html\n---\n正文\n") as mock_convert:
        documents = file_handler.html_loader(str(src))

    mock_convert.assert_called_once_with(str(src))
    cache = tmp_path / "page.md"
    assert cache.exists()
    assert "正文" in cache.read_text(encoding="utf-8")
    assert documents[0].page_content == "正文\n"
```

- [ ] **Step 2: 跑测试，确认失败**

Run:
```bash
pytest tests/test_file_handler.py -v
```
Expected: `test_pdf_loader_prefers_markdown_cache`、`test_txt_loader_falls_back_to_conversion_when_cache_missing`、`test_html_loader_creates_cache_file` 失败（当前 `pdf_loader` 等不会读缓存也不会调 `convert_to_markdown`）。

- [ ] **Step 3: 改造 8 个 Loader**

Modify each loader in `utils/file_handler.py`：

```python
from utils.markdown_converter import convert_to_markdown


def _ensure_markdown_cache(src_path: str) -> list[Document]:
    """检查 <src_path>.md 缓存；命中则读，未命中则转换并写。"""
    base, _ = os.path.splitext(src_path)
    md_path = base + ".md"
    if os.path.exists(md_path):
        return _read_markdown_with_frontmatter(md_path)

    content = convert_to_markdown(src_path)
    _write_markdown_cache(md_path, content)
    return _read_markdown_with_frontmatter(md_path)


def pdf_loader(filepath: str, passwd=None) -> list[Document]:
    return _ensure_markdown_cache(filepath)


def txt_loader(filepath: str) -> list[Document]:
    return _ensure_markdown_cache(filepath)


def markdown_loader(filepath: str) -> list[Document]:
    # 纯 Markdown 文件：直接读 frontmatter，不调转换。
    return _read_markdown_with_frontmatter(filepath)


def docx_loader(filepath: str) -> list[Document]:
    return _ensure_markdown_cache(filepath)


def csv_loader(filepath: str) -> list[Document]:
    return _ensure_markdown_cache(filepath)


def excel_loader(filepath: str) -> list[Document]:
    return _ensure_markdown_cache(filepath)


def pptx_loader(filepath: str) -> list[Document]:
    return _ensure_markdown_cache(filepath)


def html_loader(filepath: str) -> list[Document]:
    return _ensure_markdown_cache(filepath)
```

> 删除旧的 `BSHTMLLoader`、`PyPDFLoader`、`TextLoader`、`Docx2txtLoader`、`CSVLoader`、`openpyxl`、`Presentation` 引用（如不再被使用）。`get_file_md5_hex`、`listdir_with_allowed_type` 保留。

- [ ] **Step 4: 跑测试，确认通过**

Run:
```bash
pytest tests/test_file_handler.py -v
```
Expected: 全部通过（5 个测试）。

- [ ] **Step 5: Commit**

```bash
git add utils/file_handler.py tests/test_file_handler.py
git commit -m "refactor: loaders prefer markdown cache, fall back to markitdown"
```

---

### Task 7: 修改 rag/vector_store.py dispatch 表与 chroma.yml

**Files:**
- Modify: `rag/vector_store.py`
- Modify: `config/chroma.yml`

**Interfaces:**
- Consumes: 8 个 Loader 函数（Task 6）。
- Produces: `rag/vector_store.py:get_file_documents` dispatch 表简化为 `{".md": markdown_loader}`；`config/chroma.yml` 中 `allow_knowledge_file_type: ["md"]`、`data_orig_path: data_orig`。

- [ ] **Step 1: 写失败测试**

Append to `tests/test_file_handler.py`（或新建 `tests/test_vector_store_dispatch.py`）：

```python
import rag.vector_store as vector_store


def test_get_file_documents_dispatches_md_only(monkeypatch):
    expected = [object()]
    monkeypatch.setattr(vector_store, "markdown_loader", lambda _path: expected, raising=False)

    assert vector_store.get_file_documents("note.md") is expected
    assert vector_store.get_file_documents("note.txt") == []
    assert vector_store.get_file_documents("note.pdf") == []
    assert vector_store.get_file_documents("note.html") == []
```

- [ ] **Step 2: 跑测试，确认失败**

Run:
```bash
pytest tests/test_file_handler.py -v
```
Expected: `test_get_file_documents_dispatches_md_only` 失败（当前 dispatch 仍含 8 个后缀）。

- [ ] **Step 3: 修改 rag/vector_store.py**

Modify `rag/vector_store.py:22-36`：

```python
def get_file_documents(read_path: str) -> list[Document]:
    """读取 Markdown 缓存文件；未知后缀返回空列表。"""
    suffix = os.path.splitext(read_path)[1].lower()
    loaders = {".md": markdown_loader}
    loader = loaders.get(suffix)
    return loader(read_path) if loader else []
```

确保 `from utils.file_handler import markdown_loader` 已存在（见 Task 5/6 的 import）。

- [ ] **Step 4: 修改 config/chroma.yml**

```yaml
collection_name: agent
persist_directory: chroma_db
k: 3
data_path: data
data_orig_path: data_orig
md5_hex_store: md5.text
allow_knowledge_file_type: ["md"]

chunk_size: 200
chunk_overlap: 20
separators: ["\n\n", "\n", ".", "!", "?", "。", "！", "？", " ", ""]
```

- [ ] **Step 5: 跑测试，确认通过**

Run:
```bash
pytest tests/test_file_handler.py -v
```
Expected: 全部通过（含新 dispatch 用例）。

- [ ] **Step 6: Commit**

```bash
git add rag/vector_store.py config/chroma.yml tests/test_file_handler.py
git commit -m "refactor: vector_store dispatches only md, config restricts allow list"
```

---

### Task 8: 调整 tests/test_agent_tools.py

**Files:**
- Modify: `tests/test_agent_tools.py`

**Interfaces:**
- Consumes: Task 5/6/7 后的 Loader 与 dispatch。
- Produces:
  - 删除 `test_get_file_documents_dispatches_case_insensitively` 参数化用例中 7 个非 `.md` 项，保留 `.md` 用例。
  - 删除 `test_html_loader_reads_utf8_chinese_page_content`、`test_office_loaders_parse_minimal_excel_and_powerpoint`，改造为 `markdown_converter` 测试（已在 `tests/test_markdown_converter.py` 中覆盖 Task 3/4 内容）。
  - 保留 `test_listdir_with_allowed_type_matches_uppercase_suffix`。

- [ ] **Step 1: 替换用例**

Modify `tests/test_agent_tools.py`，把 `test_get_file_documents_dispatches_case_insensitively` 改为：

```python
def test_get_file_documents_dispatches_md(monkeypatch):
    expected_documents = [object()]
    monkeypatch.setattr(vector_store, "markdown_loader", lambda _path: expected_documents, raising=False)

    assert vector_store.get_file_documents("knowledge.MD") is expected_documents
```

删除 `test_html_loader_reads_utf8_chinese_page_content` 与 `test_office_loaders_parse_minimal_excel_and_powerpoint` 整个函数体。

- [ ] **Step 2: 跑全部测试，确认通过**

Run:
```bash
pytest tests/ -v
```
Expected: 全部测试通过（不含已删除的两个用例）。

- [ ] **Step 3: Commit**

```bash
git add tests/test_agent_tools.py
git commit -m "test: retire legacy loader tests in favor of converter coverage"
```

---

### Task 9: 迁移 data/ → data_orig/，生成 data/*.md

**Files:**
- Modify: `.gitignore`
- Modify: `data/`、`data_orig/`

**Interfaces:**
- Consumes: Task 6 改造后的 Loader、`convert_to_markdown`（Task 3）。
- Produces: `data_orig/` 含 11 个原文件；`data/` 含对应 `.md`（含 frontmatter）。

- [ ] **Step 1: 移动原文件到 data_orig/**

```bash
mkdir -p data_orig
git mv data/* data_orig/
ls data_orig/
```

Expected: `data_orig/` 含 11 个原文件；`data/` 为空。

- [ ] **Step 2: 在 .gitignore 新增 data_orig/**

Append to `.gitignore`:

```
data_orig/
```

- [ ] **Step 3: 一次性生成 Markdown 缓存**

Run:

```bash
python -c "
import os
from utils.markdown_converter import convert_to_markdown
from utils.logger_handler import logger

src_dir = 'data_orig'
dst_dir = 'data'
os.makedirs(dst_dir, exist_ok=True)

for name in sorted(os.listdir(src_dir)):
    src_path = os.path.join(src_dir, name)
    if not os.path.isfile(src_path):
        continue
    base, _ = os.path.splitext(name)
    md_path = os.path.join(dst_dir, base + '.md')
    try:
        content = convert_to_markdown(src_path)
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info('转换成功：%s -> %s', src_path, md_path)
    except Exception as exc:
        logger.error('转换失败：%s 错误=%s', src_path, exc)
"
```

Expected: 11 条 INFO 日志；`data/` 含 11 个 `.md`。

- [ ] **Step 4: 抽样验证 frontmatter**

```bash
head -n 8 data/电动汽车100问.md
head -n 8 data/车网互动V2G知识图谱.md
head -n 8 data/中国充电基础设施统计与趋势.md
```

Expected: 三个文件均以 `---` 起头，且对应 frontmatter 字段正确（PPT/XLSX 含 `slides` / `sheets`）。

- [ ] **Step 5: 跑 load_document 入库**

Run:

```bash
rm -f md5.text   # 强制重新入库
python -m rag.vector_store
```

Expected: `logs/` 中 11 个文件全部成功；不抛异常；`md5.text` 写入 11 行。

- [ ] **Step 6: Commit**

```bash
git add .gitignore data/
git commit -m "feat: generate markdown cache and ingest knowledge base"
```

---

### Task 10: 集成验证与最终清理

**Files:**
- Verify-only

**Interfaces:**
- Consumes: 全部 Task 产出。
- Produces: 全套测试通过；向量库重建后检索结果合理。

- [ ] **Step 1: 跑全部测试**

```bash
pytest tests/ -v
```

Expected: 全部通过（含 `test_markdown_converter.py`、`test_file_handler.py`、精简后的 `test_agent_tools.py`）。

- [ ] **Step 2: 端到端检索 smoke test**

```bash
python -c "
from rag.vector_store import VectorStoreService
retriever = VectorStoreService().get_retriever()
for r in retriever.invoke('电池安全'):
    print('---')
    print(r.page_content[:200])
"
```

Expected: 至少 1 条结果含与电池安全相关的中文文本。

- [ ] **Step 3: 删除临时验证脚本（如有）**

```bash
rm -f tmp/convert_once.py
```

- [ ] **Step 4: 最终 commit**

```bash
git status
git log --oneline -10
```

Expected: 工作区干净；最近 10 个 commit 与本计划 Task 对齐。