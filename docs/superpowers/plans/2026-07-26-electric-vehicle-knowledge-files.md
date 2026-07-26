# Electric Vehicle Knowledge Files Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create six source-traceable Chinese electric-vehicle knowledge files in distinct formats and topics under `data`.

**Architecture:** Research is recorded once in a temporary source ledger, then transformed into six topic-specific content packs. Each artifact is generated with a format-appropriate tool and independently parsed and rendered before final cross-file checks.

**Tech Stack:** OpenCLI/web retrieval, bundled Python (`reportlab`, `python-docx`, `openpyxl`, `pypdf`), `@oai/artifact-tool`, Poppler/LibreOffice render helpers.

## Global Constraints

- Preserve the current TXT files without modification.
- Do not restore files the user manually deleted.
- Replace the mistakenly downloaded `data/电动汽车安全指南.pdf` with the new OTA and cybersecurity PDF.
- Use only real Chinese sources and record source name, URL, and retrieval date in every artifact.
- Do not copy existing TXT, HTML, or mistaken PDF prose into new artifacts.
- Do not change project loader or business code.

---

### Task 1: Build the source ledger and overlap boundary

**Files:**
- Create: temporary `D:/code/python/RAG/tmp/ev-knowledge-build/source-ledger.txt`
- Read: `D:/code/python/RAG/data/*.txt`

**Interfaces:**
- Consumes: approved themes in the design specification.
- Produces: a source ledger containing URL, publisher, publication date, retrieval date, supported claims, and assigned artifact.

- [ ] Run OpenCLI live-registry and help preflight, then query one Chinese AI source once for candidate authoritative sources.
- [ ] Retrieve and verify primary pages from government, regulator, industry-association, or standards sources.
- [ ] Record at least two independent authoritative sources per narrative artifact and exact source coverage for every data row.
- [ ] Extract keywords from existing TXT files and confirm each planned topic adds materially different knowledge.

### Task 2: Create the PDF and Markdown artifacts

**Files:**
- Delete after replacement: `D:/code/python/RAG/data/电动汽车安全指南.pdf`
- Create: `D:/code/python/RAG/data/汽车OTA升级与网络安全合规.pdf`
- Create: `D:/code/python/RAG/data/动力电池回收利用与溯源管理.md`

**Interfaces:**
- Consumes: verified OTA/cybersecurity and battery-recycling entries from the source ledger.
- Produces: searchable Chinese PDF text and UTF-8 Markdown with inline source markers and full references.

- [ ] Draft topic outlines using only claims supported by the ledger.
- [ ] Generate the PDF with embedded Chinese fonts, page numbers, a source section, and no copied paragraphs.
- [ ] Write the Markdown with clear headings, tables where useful, and a source section.
- [ ] Extract both artifacts to text and confirm Chinese content, references, and topic separation.
- [ ] Render every PDF page and inspect for clipping, missing glyphs, or broken pagination.

### Task 3: Create the Word and CSV artifacts

**Files:**
- Create: `D:/code/python/RAG/data/新能源汽车保险与理赔边界.docx`
- Create: `D:/code/python/RAG/data/电驱动系统核心部件知识表.csv`

**Interfaces:**
- Consumes: verified insurance-clause and electric-drive references from the source ledger.
- Produces: a structured Word guide and UTF-8-BOM CSV with one traceable source per knowledge row.

- [ ] Draft the insurance guide around coverage, exclusions, charging-equipment scenarios, claim evidence, and dispute handling.
- [ ] Generate DOCX with a title page, heading hierarchy, tables, page numbers, and references.
- [ ] Build CSV columns for component, subsystem, function, principle, key parameter, engineering concern, source name, and source URL.
- [ ] Parse DOCX and CSV to verify non-empty Chinese content, valid row counts, UTF-8 compatibility, and URLs.
- [ ] Render every DOCX page and inspect text wrapping, table pagination, and source readability.

### Task 4: Create the Excel and PowerPoint artifacts

**Files:**
- Create: `D:/code/python/RAG/data/中国充电基础设施统计与趋势.xlsx`
- Create: `D:/code/python/RAG/data/车网互动V2G知识图谱.pptx`

**Interfaces:**
- Consumes: official charging-infrastructure figures and V2G policy/technical entries from the source ledger.
- Produces: an auditable workbook with formulas and a visually coherent slide deck with per-slide source notes.

- [ ] Populate workbook sheets for raw indicators, calculated trends, methodology, and sources; use formulas for changes and shares.
- [ ] Inspect workbook values and formulas, scan for formula errors, and render every sheet.
- [ ] Create a 6-8 slide V2G deck with distinct layouts, concise Chinese copy, and source notes on every sourced slide.
- [ ] Render every slide, inspect full-size images, and run slide overflow and overlap checks.

### Task 5: Run final acceptance and cleanup

**Files:**
- Verify: `D:/code/python/RAG/data/*`
- Remove: `D:/code/python/RAG/tmp/ev-knowledge-build/`

**Interfaces:**
- Consumes: all six final artifacts.
- Produces: a final verification report covering format validity, extraction, overlap, sources, and Git state.

- [ ] Confirm the six expected extensions exist exactly once among the new artifacts and retain current TXT files unchanged by hash.
- [ ] Open OOXML ZIP structures and parse PDF, Markdown, CSV, DOCX, XLSX, and PPTX content with independent libraries.
- [ ] Compare extracted text against existing TXT material using keyword and sentence-overlap checks; investigate any suspicious match.
- [ ] Scan all artifacts for placeholders, malformed URLs, empty sections, mojibake, and unsupported claims.
- [ ] Remove build intermediates, preserve user deletion state, and report final filenames, sources, and verification results without staging the generated artifacts.
