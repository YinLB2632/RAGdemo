# Electric Vehicle RAG Assistant

An electric vehicle customer-service assistant built with Streamlit, LangChain, Chroma, and DashScope models. It retrieves local knowledge-base documents, can call weather and location tools, and supports isolated multi-turn conversations in one browser session.

## Features

- RAG retrieval over local electric vehicle knowledge documents.
- Automatic incremental knowledge-base ingestion when a Streamlit session starts.
- TXT, PDF, Markdown, DOCX, CSV, XLSX, PPTX, and UTF-8 HTML ingestion.
- Streaming ReAct agent responses with retrieval, weather, location, and current-month tools.
- Sidebar conversations: create, switch, and delete independent in-memory chats.
- MD5-based ingestion deduplication to avoid inserting unchanged files twice.

## Requirements

- Python 3.10 or later.
- A DashScope API key with access to the configured chat and embedding models.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:DASHSCOPE_API_KEY = "your-dashscope-api-key"
```

The API key is read by the DashScope integrations. Do not commit the key or a local `.env` file.

## Run

```powershell
python -m streamlit run app.py
```

On the first page load, the app scans `data/` and incrementally inserts supported files into Chroma. Existing file content is skipped through `md5.text`.

To run ingestion manually:

```powershell
python -m rag.vector_store
```

## Knowledge Files

Put source documents in `data/`. The configured supported extensions are:

```text
txt, pdf, md, docx, csv, xlsx, pptx, html
```

The committed `data/` directory contains electric-vehicle reference materials. Generated vector data is intentionally excluded from Git and is rebuilt locally.

## Conversations

The sidebar creates, switches, and deletes conversations. Each conversation has an independent message history, so multi-turn context is not shared between windows. Conversation records exist only in the active Streamlit browser session; a full browser refresh or a new browser session starts fresh state.

## Configuration

- `config/rag.yml`: DashScope chat and embedding model names.
- `config/chroma.yml`: Chroma collection, chunking, retrieval count, data path, and supported file types.
- `config/prompts.yml`: prompt file paths.
- `prompts/`: system and RAG summarization prompts.

## Test

```powershell
python -m pytest tests/test_agent_tools.py -v
python -m compileall -q app.py agent rag model utils
```

## Project Layout

```text
agent/      ReAct agent, tools, and middleware
config/     RAG, Chroma, and prompt configuration
data/       Knowledge-base source documents
model/      Chat and embedding model factories
prompts/    System and RAG prompts
rag/        Chroma ingestion and retrieval service
tests/      Regression tests
utils/      Shared helpers and conversation state management
app.py      Streamlit entry point
```
