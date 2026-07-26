# MarkItDown Loader 统一设计

日期：2026-07-27
目标：用 Microsoft MarkItDown 把 `data/` 下多格式文档统一转换为 Markdown，由 LangChain 的文本切分器统一切分后入库。

## 1. 背景与动机

`data/` 当前包含 11 个文件，覆盖 8 种格式：txt / md / csv / xlsx / docx / pptx / pdf / html。
当前实现每个格式各有一个专属 Loader（`utils/file_handler.py`），转换结果各异：

- Excel：每个工作表一段纯文本，行用换行连接，列用 ` | ` 连接。
- PPTX：每张幻灯片一段纯文本。
- PDF：依赖 `PyPDFLoader` 按页抽取。
- DOCX / CSV / HTML：各自 Loader 行为不同。

切分阶段统一使用 `RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=20)`。但因输入文本格式不一致，标题、表格、列表结构在切分前已经丢失，影响后续检索质量。

引入 MarkItDown 可以把任意格式转换为 Markdown，保留标题、列表、表格、链接等结构，从而让 `RecursiveCharacterTextSplitter` 切分后的 chunk 仍然携带语义信息。

## 2. 决策摘要

| 维度 | 决策 |
|---|---|
| 触发时机 | 离线预处理产物优先；运行时 Loader 内部缺失则触发转换 |
| 依赖策略 | `markitdown[all]` 全量依赖 |
| 产物组织 | `data_orig/` 保留原文件 + `data/` 仅放 `.md` |
| 失败策略 | 用 `utils/logger_handler` 输出到日志与控制台，转换失败 → 抛出（不静默） |
| metadata | 通过 YAML frontmatter 嵌入（PDF 页码、PPT 幻灯片号、Excel 工作表名） |
| 调用边界 | Loader 内部隐藏转换，扫描路径仍是 `data/` |

## 3. 架构

```text
data_orig/                          # 原始文件（gitignore）
  *.txt | *.md | *.csv | *.docx
  *.xlsx | *.pptx | *.pdf | *.html
         ↓  MarkItDown.convert() + 结构化 frontmatter
data/                               # Markdown 产物（git 追踪）
  <basename>.md  含 YAML frontmatter
         ↓  markdown_loader（解析 frontmatter）
List[Document]                      # 每个 Document 携带 source/file_type/pages/slides/sheets
         ↓  RecursiveCharacterTextSplitter
List[Document]                      # chunks
         ↓  Chroma.add_documents
```

## 4. 组件

### 4.1 utils/markdown_converter.py（新文件）

单一职责：任意受支持文件 → 含 YAML frontmatter 的 Markdown 文本。

签名：

```python
def convert_to_markdown(source_path: str) -> str: ...
```

实现要点：

- 调用 `MarkItDown().convert(source_path).text_content`。
- 根据 `file_type` 注入结构化 frontmatter：
  - PDF：用 `pdfplumber` 打开，按页读取文本，每页之间用 `---` 水平分隔，frontmatter 包含 `pages: [...]` 与 `page_count`。
  - PPTX：用 `python-pptx` 打开，每张幻灯片用 `## Slide N` 起头，frontmatter 包含 `slides: [...]`。
  - XLSX：用 `openpyxl` 打开，每个工作表用 `## Sheet: <name>` 起头，frontmatter 包含 `sheets: [...]`。
  - 其他格式（txt/md/csv/docx/html）：仅基础 frontmatter（`source`、`file_type`、`converted_by`）。
- 失败时通过 `utils/logger_handler.logger.error` 记录 ERROR（含 traceback），再抛出原异常。

frontmatter 模板示例（PDF）：

```markdown
---
source: 汽车OTA升级与网络安全合规.pdf
file_type: pdf
converted_by: markitdown 0.1.6
page_count: 18
pages: [1, 2, 3, ..., 18]
---

第 1 页文本

---

第 2 页文本
```

### 4.2 utils/file_handler.py（改造）

每个 Loader 函数仍然保留，但实现变为：先尝试 `data/<basename>.md`，命中则解析 frontmatter 并返回；未命中则调用 `markdown_converter.convert_to_markdown` 生成 `.md`，再返回。

新增 helper：

- `_read_markdown_with_frontmatter(md_path) -> list[Document]`：解析 frontmatter，正文作为 `page_content`；frontmatter 字段合并进 `metadata`。
- `_write_markdown_cache(md_path, content: str)`：写入 `.md` 文件。
- `markdown_loader(md_path: str) -> list[Document]`：对 `data/` 中纯 `.md` 走 frontmatter 解析（不调 MarkItDown）。

PDF/PPTX/XLSX 等专属 Loader 仍存在，用于兼容；它们各自尝试命中 `.md` 缓存，否则调转换。

### 4.3 rag/vector_store.py（轻改）

- `get_file_documents` dispatch 表简化为只匹配 `.md`：
  ```python
  loaders = {".md": markdown_loader}
  ```
- `load_document` 扫描路径仍为 `chroma_conf["data_path"]`（即 `data/`），过滤类型改为 `["md"]`。
- MD5 计算、`split_documents`、`add_documents` 流程不变。
- 当 `data/<name>.md` 已存在但 `data_orig/<name>.<ext>` 被更新时，MD5 哈希不变不会触发重新入库。手动重新生成 `.md` 即可刷新（如需自动化，可在后续迭代加入 `data_orig_mtime` 检查；本次不做）。

### 4.4 config/chroma.yml

```yaml
collection_name: agent
persist_directory: chroma_db
k: 3
data_path: data                # Markdown 产物目录
data_orig_path: data_orig      # 原文件目录（新增）
md5_hex_store: md5.text
allow_knowledge_file_type: ["md"]
chunk_size: 200
chunk_overlap: 20
separators: ["\n\n", "\n", ".", "!", "?", "。", "！", "？", " ", ""]
```

### 4.5 requirements.txt

新增 `markitdown[all]`。原有 `pypdf` / `python-pptx` / `openpyxl` / `docx2txt` / `beautifulsoup4` 仍保留（被 MarkItDown 的可选依赖或 fallback 需要）。

### 4.6 .gitignore

新增 `data_orig/`，避免 PDF/PPTX 等大体积原文件污染仓库。

## 5. 失败处理矩阵

| 阶段 | 失败信号 | 行为 |
|---|---|---|
| MarkItDown.convert | 抛异常 | `logger_handler` ERROR 记录 `path` + traceback；向上抛 |
| frontmatter 解析 | 缺失 frontmatter | 视为无 metadata，整段作正文 |
| frontmatter 解析 | YAML 损坏 | `logger_handler` WARN；跳过 frontmatter，整段作正文 |
| `.md` 写入 | IO 失败 | `logger_handler` ERROR；向上抛 |
| `load_document` 整体 | 单文件异常 | `try/except` 包裹单文件 → 日志 ERROR → 继续下一个 |
| 启动时 | `data_orig/` 缺失 | `logger_handler` WARNING；视为正常（直接用 `data/` 现有 `.md`） |

所有日志统一走 `utils/logger_handler.logger`，输出到 `logs/` 与控制台。

## 6. 测试策略

### 6.1 调整现有测试

- `test_get_file_documents_dispatches_case_insensitively`：删除参数化用例中 7 个非 `.md` 项，保留 `.md` 用例验证 dispatch 仍走 `markdown_loader`。
- `test_html_loader_reads_utf8_chinese_page_content`：改造为 `test_markdown_converter_handles_html_with_chinese_content`，验证 `convert_to_markdown("*.html")` 输出含中文并写出 `.md`。
- `test_office_loaders_parse_minimal_excel_and_powerpoint`：改造为 `test_markdown_converter_handles_xlsx_and_pptx`，验证 frontmatter 含 `sheets` / `slides`。
- `test_listdir_with_allowed_type_matches_uppercase_suffix`：保留。

### 6.2 新增测试

1. `test_markdown_converter_writes_yaml_frontmatter` —— 任意样例文件转换后 `.md` 首行以 `---` 起头。
2. `test_markdown_converter_appends_pdf_pages_metadata` —— 模拟小 PDF，验证 frontmatter 含 `pages` 与 `page_count`。
3. `test_markdown_converter_appends_pptx_slides_metadata` —— 模拟小 PPTX，frontmatter 含 `slides`。
4. `test_markdown_converter_appends_xlsx_sheets_metadata` —— 模拟小 XLSX，frontmatter 含 `sheets`。
5. `test_markdown_converter_logs_and_raises_on_failure` —— monkeypatch 替换 `MarkItDown.convert` 抛异常，验证 ERROR 日志 + 异常传播。
6. `test_markdown_loader_reads_frontmatter_metadata` —— 直接构造 `.md` 文件，验证 `markdown_loader` 把 frontmatter 解析成 metadata。
7. `test_pdf_loader_prefers_markdown_cache` —— 临时目录放 `.md` 缓存，验证 `pdf_loader` 不再调用 MarkItDown。

### 6.3 集成验证

- `pytest` 全部通过。
- `python -m rag.vector_store` 完整跑一次 `load_document()`，观察 `logs/` 中 11 个文件全部成功转换并入库。

## 7. 迁移步骤

1. `pip install "markitdown[all]"` 并写入 `requirements.txt`。
2. 新增 `utils/markdown_converter.py`。
3. 扩展 `utils/file_handler.py`：重写 8 个 Loader，新增 `markdown_loader`、`_read_markdown_with_frontmatter`、`_write_markdown_cache`、内嵌 frontmatter 解析。
4. 修改 `rag/vector_store.py`：`get_file_documents` dispatch 表简化为 `.md`。
5. 修改 `config/chroma.yml`：`allow_knowledge_file_type` → `["md"]`、新增 `data_orig_path: data_orig`。
6. 在 `.gitignore` 新增 `data_orig/`。
7. 移动 `data/*` 现有 11 个文件到 `data_orig/`。
8. 临时一次性脚本（不入库）遍历 `data_orig/`，调 `convert_to_markdown` 写入 `data/<basename>.md`。
9. 调整 `tests/test_agent_tools.py`：删除 7 个非 `.md` dispatch 用例，改造 2 个旧 Loader 测试为 converter 测试。
10. 新增 7 条针对 `markdown_converter` 和 frontmatter 解析的测试。
11. 跑 `pytest` 与集成验证。

每 1–2 步一个 git commit，便于逐 commit revert。

## 8. 回滚

- `data_orig/` 保留原始文件，任何步骤都可手动逆向：删除 `data/*.md`，把 `data_orig/*` 移回 `data/`，恢复 Loader 旧实现。
- 通过分阶段 git commit 隔离，可逐 commit 回滚。

## 9. 不做的事（YAGNI）

- 不实现自动重新转换（手动触发即可；MD5 命中即跳过）。
- 不实现增量转换标记文件（`data/` 中 `.md` 是否存在已是天然标记）。
- 不修改 `chunk_size` / `chunk_overlap` / `separators`。
- 不引入 `python-frontmatter` 等新依赖（自己解析 frontmatter）。
- 不引入 OCR / AI 增强（避免额外网络依赖与新组件）。
- 不改 `chunk_size`、`chunk_overlap`、`separators`。