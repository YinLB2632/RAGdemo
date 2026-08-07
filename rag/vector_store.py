from langchain_chroma import Chroma
from langchain_core.documents import Document
from utils.config_handler import chroma_conf
from model.factory import embed_model
from langchain_text_splitters import RecursiveCharacterTextSplitter
from utils.path_tool import get_abs_path
from utils.file_handler import (
    csv_loader,
    docx_loader,
    excel_loader,
    get_file_md5_hex,
    html_loader,
    listdir_with_allowed_type,
    markdown_loader,
    pdf_loader,
    txt_loader,
)
from utils.logger_handler import logger
import json
import os
from typing import List
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from pydantic import ConfigDict


class RRFRetriever(BaseRetriever):
    """Reciprocal Rank Fusion 合并 BM25 与向量检索结果。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    bm25: object
    vector: object
    top_k: int = 3
    rrf_k: int = 60  # RRF 常数，越大对头部排名差异越不敏感
    score_threshold: float = 0.0  # 低于此分数的结果直接丢弃

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        bm25_docs = self.bm25._get_relevant_documents(query, run_manager=run_manager)
        vector_docs = self.vector._get_relevant_documents(query, run_manager=run_manager)

        # 用 (page_content, source) 为 key，避免不同文件相同正文的 chunk 互相覆盖
        scores: dict[tuple, float] = {}
        doc_map: dict[tuple, Document] = {}

        for rank, doc in enumerate(bm25_docs):
            key = (doc.page_content, doc.metadata.get("source", ""))
            scores[key] = scores.get(key, 0.0) + 1.0 / (self.rrf_k + rank + 1)
            doc_map[key] = doc

        for rank, doc in enumerate(vector_docs):
            key = (doc.page_content, doc.metadata.get("source", ""))
            scores[key] = scores.get(key, 0.0) + 1.5 / (self.rrf_k + rank + 1)
            doc_map[key] = doc

        sorted_keys = sorted(scores, key=lambda k: scores[k], reverse=True)
        return [
            doc_map[k] for k in sorted_keys[: self.top_k]
            if scores[k] >= self.score_threshold
        ]


def get_file_documents(read_path: str) -> list[Document]:
    """根据文件后缀调用对应 Loader；未知格式返回空列表，由调用方记录跳过日志。"""
    suffix = os.path.splitext(read_path)[1].lower()
    loaders = {
        ".txt": txt_loader,
        ".pdf": pdf_loader,
        ".md": markdown_loader,
        ".docx": docx_loader,
        ".csv": csv_loader,
        ".xlsx": excel_loader,
        ".html": html_loader,
    }
    loader = loaders.get(suffix)
    return loader(read_path) if loader else []


class VectorStoreService:
    def __init__(self):
        self.vector_store = Chroma(
            collection_name=chroma_conf["collection_name"],
            embedding_function=embed_model,
            persist_directory=chroma_conf["persist_directory"],
        )

        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=chroma_conf["chunk_size"],
            chunk_overlap=chroma_conf["chunk_overlap"],
            separators=chroma_conf["separators"],
            length_function=len,
        )
        self._hybrid_retriever_cache = None  # 知识库变更时置 None 触发重建

    def get_retriever(self):
        return self.vector_store.as_retriever(search_kwargs={"k": chroma_conf["k"]})

    def get_hybrid_retriever(self):
        """BM25 + 向量混合检索：关键词命中与语义理解互补。BM25 索引在首次调用时构建并缓存，知识库同步后自动失效。"""
        if self._hybrid_retriever_cache is not None:
            return self._hybrid_retriever_cache

        from langchain_community.retrievers.bm25 import BM25Retriever
        import jieba

        # 从 Chroma 取出所有已入库 chunk，用于构建 BM25 索引
        collection_data = self.vector_store.get()
        raw_docs = collection_data.get("documents") or []
        raw_metas = collection_data.get("metadatas") or [{}] * len(raw_docs)

        if not raw_docs:
            # 知识库为空时降级为纯向量检索
            logger.warning("[混合检索] 知识库为空，降级为向量检索")
            return self.get_retriever()

        all_docs = [
            Document(page_content=text, metadata=meta or {})
            for text, meta in zip(raw_docs, raw_metas)
        ]

        bm25_k = chroma_conf.get("bm25_k", chroma_conf["k"])
        vector_k = chroma_conf.get("vector_k", chroma_conf["k"])
        top_k = chroma_conf.get("hybrid_top_k", chroma_conf["k"])
        score_threshold = chroma_conf.get("rrf_score_threshold", 0.0)

        bm25_retriever = BM25Retriever.from_documents(
            all_docs,
            preprocess_func=lambda text: jieba.lcut(text),
        )
        bm25_retriever.k = bm25_k

        vector_retriever = self.vector_store.as_retriever(search_kwargs={"k": vector_k})

        self._hybrid_retriever_cache = RRFRetriever(
            bm25=bm25_retriever,
            vector=vector_retriever,
            top_k=top_k,
            score_threshold=score_threshold,
        )
        return self._hybrid_retriever_cache

    def load_document(self):
        """
        增量同步知识库，处理四种情况：
        - 新文件：读取、分片、写入向量库，记录 路径→MD5 映射
        - 已修改文件：MD5 变化时，先删除向量库中的旧 chunks，再重新入库
        - 已删除文件：从 data 目录消失的文件，清理向量库中对应的 chunks
        - 未变文件：MD5 一致，直接跳过，不重复入库

        映射存储在 md5_hex_store 指定的 JSON 文件中，格式为 {文件绝对路径: MD5 十六进制值}。
        """

        # md5 映射文件的绝对路径
        store_path = get_abs_path(chroma_conf["md5_hex_store"])

        def load_md5_map() -> dict[str, str]:
            """从 JSON 文件读取 {路径: MD5} 映射；文件不存在或损坏时返回空字典。"""
            if not os.path.exists(store_path):
                return {}
            with open(store_path, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except (json.JSONDecodeError, ValueError):
                    # 文件损坏（如旧版纯文本格式），视为空映射，触发全量重建
                    return {}

        def save_md5_map(md5_map: dict[str, str]):
            """将 {路径: MD5} 映射持久化到 JSON 文件，每次成功入库后立即调用以保证崩溃可恢复。"""
            with open(store_path, "w", encoding="utf-8") as f:
                json.dump(md5_map, f, ensure_ascii=False, indent=2)

        def delete_chunks_by_source(source_path: str):
            """
            按文件路径批量删除向量库中对应的所有 chunks。
            Chroma 入库时会在每个 chunk 的 metadata['source'] 中保留文件绝对路径，
            通过 where 过滤可精确定位，避免修改或删除文件后旧内容残留影响检索结果。
            """
            result = self.vector_store.get(where={"source": source_path})
            old_ids = result.get("ids", [])
            if old_ids:
                self.vector_store.delete(ids=old_ids)
                logger.info(f"[加载知识库] 已删除 {source_path} 的 {len(old_ids)} 个旧 chunk")

        # 扫描 data 目录，获取所有允许类型的文件绝对路径列表
        allowed_files_path: list[str] = list(listdir_with_allowed_type(
            get_abs_path(chroma_conf["data_path"]),
            tuple(chroma_conf["allow_knowledge_file_type"]),
        ))

        # 加载已持久化的 路径→MD5 映射
        md5_map = load_md5_map()
        # 转为集合用于 O(1) 查找，判断映射中的路径是否仍存在于 data 目录
        allowed_set = set(allowed_files_path)

        # 第一阶段：清理已从 data 目录删除的文件对应的向量数据
        # 先收集需要删除的路径列表，避免在迭代 md5_map 的同时修改它
        deleted_paths = [p for p in md5_map if p not in allowed_set]
        for path in deleted_paths:
            delete_chunks_by_source(path)
            del md5_map[path]
            logger.info(f"[加载知识库] 文件已删除，清理向量库：{path}")
        if deleted_paths:
            # 有删除操作时立即持久化，保持映射文件与向量库状态一致
            save_md5_map(md5_map)

        # 第二阶段：处理当前 data 目录中的每个文件
        for path in allowed_files_path:
            # 计算当前文件的 MD5，用于与已记录值比较，判断内容是否变化
            md5_hex = get_file_md5_hex(path)
            if md5_hex is None:
                # 计算失败（权限问题等），跳过；错误已由 get_file_md5_hex 内部记录
                continue

            if path in md5_map:
                if md5_map[path] == md5_hex:
                    # MD5 一致：文件内容未改变，跳过，不重复入库
                    logger.info(f"[加载知识库] {path} 内容未变，跳过")
                    continue
                # MD5 不一致：文件已被修改，先删除向量库中的旧 chunks，再重新入库
                logger.info(f"[加载知识库] {path} 内容已修改，重新入库")
                delete_chunks_by_source(path)

            # 以下为新文件或已修改文件的入库流程
            try:
                # 根据文件后缀选择对应的 Loader 读取文档内容
                documents: list[Document] = get_file_documents(path)

                if not documents:
                    logger.warning(f"[加载知识库] {path} 内没有有效文本内容，跳过")
                    continue

                # 将文档切分为 chunks（大小和重叠由 chroma.yml 的 chunk_size/chunk_overlap 控制）
                split_document: list[Document] = self.spliter.split_documents(documents)

                if not split_document:
                    logger.warning(f"[加载知识库] {path} 分片后没有有效文本内容，跳过")
                    continue

                # 将 chunks 写入向量库
                self.vector_store.add_documents(split_document)
                # 入库成功后立即更新映射并持久化，确保进程崩溃时已处理的文件不会重复入库
                md5_map[path] = md5_hex
                save_md5_map(md5_map)
                logger.info(f"[加载知识库] {path} 内容加载成功")
            except Exception as e:
                # 单个文件失败不影响其他文件；md5_map 不更新，下次启动时会自动重试该文件
                logger.error(f"[加载知识库] {path} 加载失败：{str(e)}", exc_info=True)
                continue


def sync_knowledge_base_once(session_state: dict) -> bool:
    """在同一个 Streamlit 页面会话中仅增量同步一次知识库。"""
    if session_state.get("knowledge_base_synced"):
        return False

    # load_document 内部依赖 MD5 跳过已入库内容；同步成功后才写入标记，异常时下次启动仍可重试。
    VectorStoreService().load_document()
    session_state["knowledge_base_synced"] = True
    return True


if __name__ == '__main__':
    vs = VectorStoreService()

    vs.load_document()

    retriever = vs.get_hybrid_retriever()

    res = retriever.invoke("迷路")
    for r in res:
        print(r.page_content)
        print("-"*20)
