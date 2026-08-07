
"""
总结服务类：用户提问，搜索参考资料，将提问和参考资料提交给模型，让模型总结回复
"""
import os
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from rag.vector_store import VectorStoreService
from utils.prompt_loader import load_rag_prompts
from langchain_core.prompts import PromptTemplate
from model.factory import chat_model
from utils.config_handler import rag_conf
from utils.logger_handler import logger


def _rewrite_query(query: str) -> list[str]:
    """用小模型将原始提问改写为多个检索友好的 query，失败时返回仅含原始 query 的列表。"""
    if not rag_conf.get("query_rewrite_enabled", True):
        return [query]

    count = rag_conf.get("query_rewrite_count", 2)
    model_name = rag_conf.get("query_rewrite_model_name", "qwen-turbo")

    try:
        from langchain_community.chat_models.tongyi import ChatTongyi
        from langchain_core.messages import HumanMessage, SystemMessage

        rewrite_model = ChatTongyi(model=model_name)
        system = (
            "你是检索优化助手。将用户的口语化提问改写为多个检索友好的表达，"
            "只扩展关键词和表达方式，不改变提问意图。"
            f"输出恰好 {count} 个改写结果，每行一个，不加序号或其他符号。"
        )
        resp = rewrite_model.invoke([
            SystemMessage(content=system),
            HumanMessage(content=query),
        ])
        content = resp.content or ""
        rewrites = [line.strip() for line in content.strip().splitlines() if line.strip()]
        if rewrites:
            return [query] + rewrites[:count]
    except Exception as e:
        logger.warning(f"[Query改写] 失败，降级使用原始query：{e}")

    return [query]


def _rerank(query: str, docs: list[Document], top_n: int) -> list[Document]:
    """用 DashScope gte-rerank 对候选 chunk 重排序，失败时原序返回。"""
    try:
        from dashscope import TextReRank

        passages = [{"text": doc.page_content} for doc in docs]
        resp = TextReRank.call(
            model=rag_conf.get("rerank_model_name", "gte-rerank"),
            query=query,
            documents=passages,
            top_n=top_n,
            return_documents=False,
        )
        if resp.status_code == 200:
            ranked = sorted(resp.output.results, key=lambda r: r.relevance_score, reverse=True)
            return [docs[r.index] for r in ranked]
    except Exception as e:
        logger.warning(f"[Rerank] DashScope API 调用失败，降级使用原始排序：{e}")
    return docs[:top_n]


class RagSummarizeService(object):
    def __init__(self):
        self.vector_store_service = VectorStoreService()
        self.retriever = self.vector_store_service.get_hybrid_retriever()
        self.prompt_text = load_rag_prompts()
        self.prompt_template = PromptTemplate.from_template(self.prompt_text)
        self.model = chat_model
        self.chain = self.prompt_template | self.model | StrOutputParser()

    def retriever_docs(self, query: str) -> list[Document]:
        queries = _rewrite_query(query)

        # 多路检索，按 (content, source) 去重，保留首次出现的文档
        seen: set[tuple] = set()
        candidates: list[Document] = []
        for q in queries:
            for doc in self.retriever.invoke(q):
                key = (doc.page_content, doc.metadata.get("source", ""))
                if key not in seen:
                    seen.add(key)
                    candidates.append(doc)

        top_n = rag_conf.get("rerank_top_n", 4)
        # reranker 始终用原始 query 评分，避免改写偏差影响相关性判断
        return _rerank(query, candidates, top_n)

    def rag_summarize(self, query: str) -> str:
        context_docs = self.retriever_docs(query)

        if not context_docs:
            return "参考资料中未找到相关信息。"

        context = ""
        for counter, doc in enumerate(context_docs, start=1):
            source = os.path.basename(doc.metadata.get("source", "未知来源"))
            sheet = doc.metadata.get("sheet_name", "")
            source_label = f"{source}（{sheet}）" if sheet else source
            context += f"【参考资料{counter}】（来源：{source_label}）\n{doc.page_content}\n\n"

        return self.chain.invoke({"input": query, "context": context})


if __name__ == '__main__':
    rag = RagSummarizeService()
    # print(rag.rag_summarize("电动汽车冬天续航为什么变短"))
