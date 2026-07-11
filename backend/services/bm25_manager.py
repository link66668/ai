"""
BM25 全文检索 — 基于 SQLite FTS5（仿 cherry-studio）

使用 SQLite FTS5 + trigram tokenizer 替代 rank_bm25 + pickle:
  - trigram 天然支持中文分词（3-gram 重叠），无需额外分词器
  - 无需外部依赖（Python 内置 sqlite3 + FTS5）
  - 事务安全，原子操作
  - 与主数据库共用文件，无独立 pickle 文件
"""
import logging
import sqlite3
from config import Config
from database import db as main_db

logger = logging.getLogger(__name__)

# FTS5 表名
FTS_TABLE = 'fts_knowledge_index'


class BM25Manager:
    """
    全文检索引擎 — 基于 SQLite FTS5 trigram

    每个课程的数据通过 course_id 列隔离，搜索时按 course_id 过滤。
    """

    def __init__(self):
        self._init_fts()

    def _conn(self):
        """获取 SQLite 连接（与主库同一文件）"""
        return main_db.get_connection()

    def _init_fts(self):
        """初始化 FTS5 虚拟表（幂等）"""
        try:
            conn = self._conn()
            conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE}
                USING fts5(
                    content,
                    course_id UNINDEXED,
                    document_id UNINDEXED,
                    chunk_index UNINDEXED,
                    heading_path UNINDEXED,
                    tokenize='trigram'
                )
            """)
            conn.commit()
        except Exception as e:
            logger.warning(f"[FTS5] 初始化失败（可能不支持 FTS5）: {e}")

    def build_index(self, course_id, chunks):
        """
        重建指定课程的 FTS 索引（原子替换）

        Args:
            course_id: 课程 ID
            chunks: 块列表
        """
        if not chunks:
            return

        course_id = int(course_id)
        conn = self._conn()

        try:
            # 事务内完成：删旧 + 插新
            conn.execute("BEGIN IMMEDIATE")

            # 删除该课程旧索引
            conn.execute(
                f"DELETE FROM {FTS_TABLE} WHERE course_id = ?",
                (course_id,)
            )

            # 批量插入
            rows = []
            for chunk in chunks:
                content = (chunk.get('content') or '').strip()
                if not content:
                    continue
                rows.append((
                    content,
                    course_id,
                    str(chunk.get('document_id', '')),
                    chunk.get('index', 0),
                    chunk.get('heading_path', '') or '',
                ))

            if rows:
                conn.executemany(
                    f"INSERT INTO {FTS_TABLE}(content, course_id, document_id, chunk_index, heading_path) "
                    f"VALUES (?, ?, ?, ?, ?)",
                    rows,
                )

            conn.commit()
            logger.info(f"[FTS5] 索引重建完成: course={course_id}, {len(rows)} 块")

        except Exception as e:
            conn.rollback()
            logger.error(f"[FTS5] 索引重建失败: {e}")

    def search(self, course_id, query, top_k=10):
        """
        FTS5 关键词搜索

        Args:
            course_id: 课程 ID
            query: 搜索关键词（FTS5 自动处理 trigram 分词）
            top_k: 返回结果数

        Returns:
            list[dict]: [{content, score, chunk_index, document_id, heading_path}, ...]
        """
        course_id = int(course_id)
        query = (query or '').strip()
        if not query:
            return []

        try:
            conn = self._conn()

            # FTS5 trigram 直接搜索
            # 转义特殊字符并构建匹配字符串
            safe_query = query.replace('"', '""')
            sql = f"""
                SELECT content, rank, chunk_index, document_id, heading_path
                FROM {FTS_TABLE}
                WHERE {FTS_TABLE} MATCH ? AND course_id = ?
                ORDER BY rank
                LIMIT ?
            """

            rows = conn.execute(sql, (f'"{safe_query}"', course_id, top_k)).fetchall()

            results = []
            for row in rows:
                # FTS5 rank 越低越相关，转换为正分数
                raw_rank = row[1] if row[1] is not None else 0
                score = max(0, 1.0 - abs(raw_rank) / 100.0) if raw_rank < 0 else 0.5

                results.append({
                    'content': row[0],
                    'score': score,
                    'chunk_index': row[2],
                    'document_id': row[3],
                    'heading_path': row[4] or '',
                })

            return results

        except Exception as e:
            logger.warning(f"[FTS5] 搜索失败: {e}")
            return []

    def remove_course(self, course_id):
        """删除课程的 FTS 索引"""
        try:
            conn = self._conn()
            conn.execute(
                f"DELETE FROM {FTS_TABLE} WHERE course_id = ?",
                (int(course_id),)
            )
            conn.commit()
        except Exception as e:
            logger.warning(f"[FTS5] 删除索引失败: {e}")

    def has_index(self, course_id):
        """检查课程是否有索引"""
        try:
            conn = self._conn()
            row = conn.execute(
                f"SELECT COUNT(*) FROM {FTS_TABLE} WHERE course_id = ?",
                (int(course_id),)
            ).fetchone()
            return row and row[0] > 0
        except Exception:
            return False

    def get_chunk_count(self, course_id):
        """获取课程的索引块数"""
        try:
            conn = self._conn()
            row = conn.execute(
                f"SELECT COUNT(*) FROM {FTS_TABLE} WHERE course_id = ?",
                (int(course_id),)
            ).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0


# 全局单例
bm25_manager = BM25Manager()
