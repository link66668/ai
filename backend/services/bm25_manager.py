"""
BM25 倒排索引管理

按课程 ID 构建独立的 BM25 索引：
- 索引持久化到 pickle 文件
- 增删文档后自动重建对应课程索引
- 支持中文的字符级 n-gram 分词
"""
import os
import pickle
import logging
import re
from config import Config

logger = logging.getLogger(__name__)


class BM25Manager:
    """
    BM25 检索管理器

    每个课程维护一个独立的 BM25Okapi 索引
    索引文件存储为: bm25_indexes/course_{course_id}.pkl
    """

    def __init__(self, index_dir=None):
        self._index_dir = index_dir or Config.BM25_INDEX_PATH
        os.makedirs(self._index_dir, exist_ok=True)
        self._indexes = {}  # course_id -> BM25Okapi
        self._corpora = {}  # course_id -> list[dict] (chunk metadata)
        self._load_existing_indexes()

    def _load_existing_indexes(self):
        """启动时加载已有索引"""
        if not os.path.exists(self._index_dir):
            return

        for filename in os.listdir(self._index_dir):
            if filename.startswith('course_') and filename.endswith('.pkl'):
                try:
                    course_id = int(filename.replace('course_', '').replace('.pkl', ''))
                    filepath = os.path.join(self._index_dir, filename)
                    with open(filepath, 'rb') as f:
                        data = pickle.load(f)
                    self._indexes[course_id] = data['index']
                    self._corpora[course_id] = data['corpus']
                    print(f"[BM25] 加载索引: course_{course_id} ({len(data['corpus'])} 个块)")
                except Exception as e:
                    logger.warning(f"加载 BM25 索引失败 ({filename}): {e}")

    def _tokenize(self, text):
        """
        中文友好的分词

        策略：
        - 中文：字符级 2-gram + 单字
        - 英文：按空格和标点分割
        - 数字/英文混合：保持完整
        """
        tokens = []

        # 提取中文字符序列做 n-gram
        chinese_chars = re.findall(r'[一-鿿]+', text)
        for segment in chinese_chars:
            # 2-gram
            for i in range(len(segment) - 1):
                tokens.append(segment[i:i + 2])
            # 单字
            tokens.extend(list(segment))

        # 提取英文/数字词
        other_parts = re.findall(r'[a-zA-Z0-9]+', text)
        tokens.extend([w.lower() for w in other_parts if len(w) >= 2])

        # 如果没有提取到任何 token，按字符分割
        if not tokens:
            tokens = list(text)

        return tokens

    def build_index(self, course_id, chunks):
        """
        为课程构建 BM25 索引

        Args:
            course_id: 课程 ID
            chunks: 块列表 [{'index': int, 'content': str, 'document_id': int, ...}, ...]
        """
        if not chunks:
            return

        from rank_bm25 import BM25Okapi

        # 保留语料库元数据
        corpus = []
        for chunk in chunks:
            corpus.append({
                'chunk_index': chunk.get('index', 0),
                'content': chunk['content'],
                'document_id': chunk.get('document_id'),
                'heading_path': chunk.get('heading_path', ''),
                'page_start': chunk.get('page_start', 1),
            })

        # 构建索引
        tokenized_corpus = [self._tokenize(item['content']) for item in corpus]

        if not tokenized_corpus:
            return

        try:
            index = BM25Okapi(tokenized_corpus)
        except Exception as e:
            logger.error(f"构建 BM25 索引失败: {e}")
            return

        self._indexes[course_id] = index
        self._corpora[course_id] = corpus

        # 持久化
        self._save_index(course_id)

        print(f"[BM25] 索引构建完成: course_{course_id} ({len(corpus)} 个块)")

    def search(self, course_id, query, top_k=10):
        """
        BM25 关键词搜索

        Args:
            course_id: 课程 ID
            query: 查询文本
            top_k: 返回结果数

        Returns:
            list[dict]: [
                {
                    'content': str,
                    'score': float,
                    'chunk_index': int,
                    'document_id': int,
                    ...
                }
            ]
        """
        if course_id not in self._indexes:
            return []

        index = self._indexes[course_id]
        corpus = self._corpora[course_id]

        tokenized_query = self._tokenize(query)
        if not tokenized_query:
            return []

        try:
            scores = index.get_scores(tokenized_query)
        except Exception as e:
            logger.warning(f"BM25 搜索失败: {e}")
            return []

        # 按分数排序
        ranked = sorted(
            enumerate(scores),
            key=lambda x: x[1],
            reverse=True,
        )

        results = []
        for idx, score in ranked[:top_k]:
            if score <= 0:
                continue
            item = corpus[idx].copy()
            item['score'] = float(score)
            results.append(item)

        return results

    def _save_index(self, course_id):
        """保存索引到文件"""
        if course_id not in self._indexes:
            return

        filepath = os.path.join(self._index_dir, f'course_{course_id}.pkl')
        data = {
            'index': self._indexes[course_id],
            'corpus': self._corpora[course_id],
        }

        try:
            # 使用临时文件 + 原子重命名
            tmp_path = filepath + '.tmp'
            with open(tmp_path, 'wb') as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp_path, filepath)
        except Exception as e:
            logger.error(f"保存 BM25 索引失败 ({course_id}): {e}")

    def remove_course(self, course_id):
        """删除课程索引"""
        self._indexes.pop(course_id, None)
        self._corpora.pop(course_id, None)

        filepath = os.path.join(self._index_dir, f'course_{course_id}.pkl')
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception as e:
                logger.warning(f"删除 BM25 索引文件失败: {e}")

    def has_index(self, course_id):
        """检查课程是否已有索引"""
        return course_id in self._indexes

    def get_chunk_count(self, course_id):
        """获取课程的索引块数量"""
        if course_id in self._corpora:
            return len(self._corpora[course_id])
        return 0


# 全局单例
bm25_manager = BM25Manager()
