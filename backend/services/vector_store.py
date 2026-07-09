"""
ChromaDB 向量存储封装

按课程 ID 隔离 Collection（course_{course_id}），支持：
- 添加/删除文档块
- 向量相似度搜索
- 元数据过滤
"""
import logging
from config import Config

logger = logging.getLogger(__name__)


class VectorStore:
    """
    ChromaDB 向量存储

    使用 PersistentClient，数据持久化到 backend/chroma_data/
    每个课程一个 Collection，隔离存储
    """

    def __init__(self, persist_dir=None):
        self._persist_dir = persist_dir or Config.CHROMA_DATA_PATH
        self._client = None

    @property
    def client(self):
        """懒加载 ChromaDB 客户端"""
        if self._client is None:
            try:
                import chromadb
            except ImportError:
                print("[VectorStore] ChromaDB 不可用，向量检索将降级为仅BM25")
                self._client = False  # 标记为不可用
                return None

            import os
            os.makedirs(self._persist_dir, exist_ok=True)
            try:
                self._client = chromadb.PersistentClient(
                    path=self._persist_dir,
                    settings=chromadb.Settings(
                        anonymized_telemetry=False,
                        allow_reset=True,
                    ),
                )
                print(f"[VectorStore] ChromaDB 初始化完成")
            except Exception as e:
                print(f"[VectorStore] ChromaDB 初始化失败: {e}，向量检索将降级为仅BM25")
                self._client = False
                return None
        return self._client if self._client is not False else None

    def _collection_name(self, course_id):
        """生成 Collection 名称"""
        return f"course_{course_id}"

    def get_or_create_collection(self, course_id):
        """
        获取或创建课程的 Collection

        Args:
            course_id: 课程 ID

        Returns:
            Collection 或 None（ChromaDB不可用时）
        """
        if self.client is None:
            return None
        name = self._collection_name(course_id)
        try:
            return self.client.get_or_create_collection(
                name=name,
                metadata={"course_id": str(course_id)},
            )
        except Exception as e:
            logger.error(f"创建 Collection 失败 ({name}): {e}")
            raise

    def add_chunks(self, course_id, chunks, embeddings):
        """
        批量添加文档块到向量存储

        Args:
            course_id: 课程 ID
            chunks: 块列表
            embeddings: 对应嵌入向量列表
        """
        if not chunks or not embeddings:
            return

        collection = self.get_or_create_collection(course_id)
        if collection is None:
            print("[VectorStore] ChromaDB 不可用，跳过向量存储")
            return

        # 准备数据
        ids = []
        documents = []
        metadatas = []
        embeds = []

        for chunk, embedding in zip(chunks, embeddings):
            chunk_id = f"chunk_{course_id}_{chunk.get('document_id', 'unknown')}_{chunk['index']}"
            ids.append(chunk_id)
            documents.append(chunk['content'])
            metadatas.append({
                'chunk_index': chunk['index'],
                'document_id': str(chunk.get('document_id', '')),
                'heading_path': chunk.get('heading_path', ''),
                'page_start': chunk.get('page_start', 1),
                'page_end': chunk.get('page_end', 1),
                'chunk_type': chunk.get('chunk_type', 'text'),
            })
            embeds.append(embedding)

        try:
            collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
                embeddings=embeds,
            )
        except Exception as e:
            logger.error(f"ChromaDB 添加块失败: {e}")
            # 尝试逐个添加以定位问题
            for i in range(len(ids)):
                try:
                    collection.add(
                        ids=[ids[i]],
                        documents=[documents[i]],
                        metadatas=[metadatas[i]],
                        embeddings=[embeds[i]],
                    )
                except Exception as inner_e:
                    logger.error(f"添加单个块失败 ({ids[i]}): {inner_e}")

    def search(self, course_id, query_embedding, top_k=10, metadata_filter=None):
        """向量相似度搜索"""
        try:
            collection = self.get_or_create_collection(course_id)
            if collection is None:
                return []  # ChromaDB 不可用
        except Exception:
            return []

        where_filter = metadata_filter or {}
        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, 50),
                where=where_filter if where_filter else None,
                include=['documents', 'metadatas', 'distances'],
            )
        except Exception as e:
            logger.warning(f"ChromaDB 查询失败: {e}")
            return []

        if not results or not results['ids'] or not results['ids'][0]:
            return []

        output = []
        for i, chunk_id in enumerate(results['ids'][0]):
            output.append({
                'chunk_id': chunk_id,
                'content': results['documents'][0][i] if results['documents'] else '',
                'score': results['distances'][0][i] if results['distances'] else 0.0,
                'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
            })

        return output

    def delete_document(self, course_id, document_id):
        """
        删除指定文档的所有块

        Args:
            course_id: 课程 ID
            document_id: 文档 ID
        """
        try:
            collection = self.get_or_create_collection(course_id)
            # ChromaDB delete by metadata filter
            collection.delete(
                where={"document_id": str(document_id)}
            )
        except Exception as e:
            logger.warning(f"删除文档向量失败: {e}")

    def delete_course(self, course_id):
        """
        删除整个课程的 Collection

        Args:
            course_id: 课程 ID
        """
        name = self._collection_name(course_id)
        try:
            self.client.delete_collection(name)
        except Exception as e:
            logger.warning(f"删除 Collection 失败 ({name}): {e}")

    def count_chunks(self, course_id):
        """获取课程的块数量"""
        try:
            collection = self.get_or_create_collection(course_id)
            return collection.count()
        except Exception:
            return 0


# 全局单例
vector_store = VectorStore()
