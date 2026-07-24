# 新能源汽车知识库问答助手

一个基于 Streamlit、LangChain、Chroma 和 DashScope 模型构建的新能源汽车智能客服助手。它可以检索本地知识库文档，调用天气与定位工具，并在同一个浏览器会话中支持相互隔离的多轮对话。

## 功能特性

- 基于本地新能源汽车知识文档的 RAG 检索问答。
- Streamlit 会话启动时自动增量导入知识库。
- 支持 TXT、PDF、Markdown、Word（.docx）、CSV、Excel（.xlsx）、PPT（.pptx）和 UTF-8 编码的 HTML 文档导入。
- 流式输出的 ReAct Agent，内置知识检索、天气、IP 定位和当前月份 4 个工具。
- 侧边栏多会话管理：新建、切换、删除相互独立的内存对话。
- 基于文件 MD5 的导入去重，跳过未变更文件的重复向量化。

## 环境要求

- Python 3.10 或更高版本。
- 一个可访问所配置对话与向量模型的 DashScope API Key。

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:DASHSCOPE_API_KEY = "你的-dashscope-api-key"
```

API Key 由 DashScope 集成组件读取。请勿将 Key 或本地 `.env` 文件提交到仓库。

## 运行

```powershell
python -m streamlit run app.py
```

首次打开页面时，应用会扫描 `data/` 目录，把支持的文件增量写入 Chroma。已入库且内容未变的文件会通过 `md5.text` 记录跳过。

手动执行导入：

```powershell
python -m rag.vector_store
```

## 知识库文件

把源文档放进 `data/` 目录。当前支持的扩展名为：

```text
txt, pdf, md, docx, csv, xlsx, pptx, html
```

仓库中已提交的 `data/` 目录包含新能源汽车参考资料。生成的向量数据不纳入版本管理，在本地重新构建。

## 多会话

侧边栏可以新建、切换和删除对话。每个对话拥有独立的消息历史，多轮上下文在不同对话之间互不共享。对话记录仅存在于当前 Streamlit 浏览器会话的内存中；刷新浏览器或开启新会话会重新开始。

## 配置

- `config/rag.yml`：DashScope 对话与向量模型名称。
- `config/chroma.yml`：Chroma 集合、分块参数、检索数量、数据路径和支持的文件类型。
- `config/prompts.yml`：提示词文件路径。
- `prompts/`：系统提示词与 RAG 总结提示词。

## 测试

```powershell
python -m pytest tests/test_agent_tools.py -v
python -m compileall -q app.py agent rag model utils
```

## 项目结构

```text
agent/      ReAct Agent、工具与中间件
config/     RAG、Chroma 与提示词配置
data/       知识库源文档
model/      对话与向量模型工厂
prompts/    系统与 RAG 提示词
rag/        Chroma 导入与检索服务
tests/      回归测试
utils/      公共工具与会话状态管理
app.py      Streamlit 入口
```
