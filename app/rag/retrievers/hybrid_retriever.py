"""
混合检索器模块
"""

"""
【模块功能】：混合检索器，结合语义和关键词检索

【小白视角解释】：
这是系统的"智能搜索引擎"，像百度+谷歌的结合体：
1. 向量检索：理解语义（"苹果手机"能搜到"iPhone"）
2. BM25检索：精准关键词匹配（搜索特定术语）
3. 动态权重：根据查询长度自动调整两种检索的比例
   - 长查询（>50字）：侧重语义理解（向量权重0.7）
   - 短查询（<20字）：侧重关键词匹配（BM25权重0.7）
4. 用户隔离：每个人只能搜到自己的文档

【使用的技术】：
- EnsembleRetriever: LangChain混合检索器
- BM25算法: 基于词频-逆文档频率的传统检索
- 向量检索(ChromaDB): 基于语义相似度的检索
- 动态权重算法: 根据查询特征自适应调整
- 用户权限过滤: 基于metadata的多租户隔离
"""


"""
混合检索器（BM25 + 向量检索）
"""
import asyncio
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain_core.retrievers import BaseRetriever

from app.rag.retrievers.empty_retriever import EmptyRetriever
from app.utils.config_handler import chroma_conf


class HybridRetriever:
    """
    混合检索器（BM25 + 向量检索）
    混合检索器，用于将向量数据库和文档处理器结合在一起。
    """

    def __init__(self, vectors_store: Chroma):
        self.vectors_store = vectors_store

    async def get_bm25_retriever(self, user_id: str = None):
        """
        获取BM25检索器
        :param user_id: 用户ID，必须提供，否则返回None
        :return: BM25Retriever实例
        """
        if not user_id:
            return None

        all_docs_result = await asyncio.to_thread(
            self.vectors_store.get, # 获取所有文档
            include=["documents", "metadatas"], # 只返回文档和元数据
            where={"user_id": user_id} # 只返回指定用户的文档
        ) # 获取所有文档
        documents = []
        for i,doc_content in enumerate(all_docs_result["documents"]): # 遍历所有文档,获取文档内容,获取元数据,添加到列表中
            metadata = all_docs_result["metadatas"][i] # 获取元数据,添加到列表中
            documents.append(Document(page_content=doc_content, metadata=metadata)) # 创建文档对象,添加到列表中

        if documents:
            bm25_retriever = BM25Retriever.from_documents(
                documents=documents,
                k=chroma_conf['k'] # 设置BM25的k值,默认为5
            )
            return bm25_retriever
        else:
            return None

    async def _get_all_documents(self) -> list[Document]:
        """
        获取向量库中的所有文档
        :return: 文档列表
        """
        all_docs = await asyncio.to_thread(
            self.vectors_store.get, # 获取所有文档
            include=["documents", "metadatas"] # 只返回文档和元数据
        )
        documents = []
        for i,doc in enumerate(all_docs["documents"]): # 遍历所有文档,获取文档内容,获取元数据,添加到列表中
            metadata = all_docs["metadatas"][i] if i < len(all_docs["metadatas"]) else {} # 获取元数据,添加到列表中
            documents.append(Document(page_content=doc, metadata=metadata))
        return documents


    async def get_retriever(self, query: str = None, user_id: str = None) -> BaseRetriever:
        """
        获取混合检索器（BM25 + 向量检索）
        :param query: 查询语句，用于动态调整权重
        :param user_id: 用户ID，用于过滤用户的文档，为空时不返回任何文档
        :return: EnsembleRetriever实例或单独的向量检索器
        """
        if not user_id:
            return EmptyRetriever()

        filter_dict = {"user_id": user_id} # 过滤用户
        vector_retriever = self.vectors_store.as_retriever(
            search_type='similarity', # 设置检索类型为相似度
            search_kwargs={'k': chroma_conf['k'], 'filter': filter_dict} # 设置向量检索器的k值,并设置过滤条件
        ) # 创建向量检索器, 默认使用相似度检索

        bm25_retriever = await self.get_bm25_retriever(user_id)

        if bm25_retriever:
            weights = await self.get_dynamic_weights(query) # 获取动态权重

            from langchain_classic.retrievers import EnsembleRetriever
            ensemble_retriever = EnsembleRetriever(
                retrievers=[vector_retriever, bm25_retriever], # 创建混合检索器, 使用向量检索器和BM25检索器
                weights=weights # 设置权重
            ) # 创建混合检索器实例
            return ensemble_retriever # 返回混合检索器实例
        else:
            return vector_retriever # 如果没有BM25检索器,则返回向量检索器


    @staticmethod
    async def get_dynamic_weights(query: str = None):
        """
        根据查询动态调整权重
        :param query: 查询语句
        :return: 权重列表 [向量检索权重, BM25检索权重]
        """
        default_vector_weight = 0.5 # 默认权重, 向量检索器
        default_bm25_weight = 0.5 # 默认权重, BM25检索器

        if not query:
            return [default_vector_weight, default_bm25_weight]

        query_length = len(query) # 查询长度
        query_words = len(query.split())  # 查询词数, 用于计算权重

        if query_length >50: # 如果查询长度大于50,则将向量检索权重调高,BM25权重调低
            vector_weight = 0.7
            bm25_weight = 0.3
        elif query_length < 20: # 如果查询长度小于20,则将向量检索权重调低,BM25权重调高
            vector_weight = 0.3
            bm25_weight = 0.7
        else:
            vector_weight = default_vector_weight
            bm25_weight = default_bm25_weight

        if query_words > 0: # 如果查询词数大于0,则根据查询词数调整权重,否则保持不变

            word_density = query_words / query_length # 查询词密度, 用于计算权重, 越长则权重越低

            if word_density > 0.1: # 如果查询词密度大于0.1,则将向量检索权重调低,BM25权重调高
                bm25_weight = min(bm25_weight + 0.1, 0.7)
                vector_weight = max(vector_weight - 0.1, 0.3)

        return [vector_weight, bm25_weight]


