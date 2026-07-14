"""
Knowledge Service — 知识库检索的统一入口

职责单一:
1. 调用混合检索获取结果
2. 标准化结果格式（统一字段名）
3. 构建 LLM 上下文块
4. 构建前端引用列表

对应 cherry-studio 的 KnowledgeService + KnowledgeSearchTool:
  - 所有 KB 操作走这一个类
  - 返回格式统一的 KnowledgeResult[]
  - 引用构建和上下文格式化都在这里完成
"""
import json
import logging

logger = logging.getLogger(__name__)


class KnowledgeService:
    """知识库服务 — 搜索 + 格式化 + 引用构建"""

    def search(self, course_id, query, ai_config=None, top_k=8, max_per_document=3):
        """
        知识库检索 — 返回跨文档分布的标准化结果

        Args:
            course_id: 课程 ID
            query: 用户问题
            ai_config: AI 配置（含嵌入 API 设置）
            top_k: 返回结果数
            max_per_document: 每篇文档最多返回的块数（保证结果跨文档分布）

        Returns:
            KnowledgeResult[] — 每个元素:
                {num, content, doc_name, heading_path, score, document_id, source}
        """
        if not course_id:
            return []

        from services.retrieval_service import RetrievalService

        try:
            retrieval = RetrievalService()
            # 多取一些原始结果，给跨文档筛选留空间
            raw_results = retrieval.hybrid_search(
                course_id, query, top_k=top_k * 3, ai_config=ai_config,
            )
        except Exception as e:
            logger.warning(f"[KnowledgeService] 检索失败: {e}")
            return []

        if not raw_results:
            return []

        # 加载文档名映射（一次查询，供所有结果使用）
        doc_names = self._load_doc_names(course_id)

        # 标准化 + 跨文档去重
        standardized = []
        for r in raw_results:
            doc_id = r.get('document_id') or ''
            if not doc_id and 'metadata' in r:
                doc_id = r['metadata'].get('document_id', '')

            heading = r.get('heading_path') or ''
            if not heading and 'metadata' in r:
                heading = r['metadata'].get('heading_path', '')

            doc_name = '未知文档'
            if doc_id:
                try:
                    doc_name = doc_names.get(int(doc_id), '未知文档')
                except (ValueError, TypeError):
                    doc_name = '未知文档'

            standardized.append({
                'content': r.get('content', ''),
                'doc_name': doc_name,
                'heading_path': heading,
                'score': round(float(r.get('score', 0)), 4),
                'document_id': str(doc_id),
            })

        # 跨文档分布：每篇文档最多取 max_per_document 条
        # 按分数排序后，逐文档填充，保证多样性
        standardized.sort(key=lambda x: x['score'], reverse=True)
        doc_count = {}  # document_id -> count
        diverse_results = []

        for item in standardized:
            did = item['document_id']
            current = doc_count.get(did, 0)
            if current < max_per_document:
                diverse_results.append(item)
                doc_count[did] = current + 1
            if len(diverse_results) >= top_k:
                break

        # 如果跨文档后数量不够，补填（通常是 max_per_document 限制太严）
        if len(diverse_results) < top_k:
            for item in standardized:
                if item not in diverse_results:
                    diverse_results.append(item)
                    if len(diverse_results) >= top_k:
                        break

        # 编号
        results = []
        for i, r in enumerate(diverse_results):
            results.append({
                'num': i + 1,
                'content': r['content'],
                'doc_name': r['doc_name'],
                'heading_path': r['heading_path'],
                'score': r['score'],
                'document_id': r['document_id'],
                'source': 'course_kb',
            })

        docs_covered = len(set(r['document_id'] for r in results if r['document_id']))
        logger.info(
            f"[KnowledgeService] 检索 {len(results)} 条结果, "
            f"覆盖 {docs_covered} 篇文档 for course={course_id}"
        )
        return results

    def get_available_docs(self, course_id):
        """获取课程中所有可供检索的文档列表"""
        try:
            from database import db
            rows = db.fetch_all(
                "SELECT id, original_name, file_type, chunk_count "
                "FROM documents WHERE course_id = ? AND processing_status = 'completed' "
                "ORDER BY original_name",
                (course_id,)
            )
            return [
                {'id': r['id'], 'name': r['original_name'],
                 'type': r.get('file_type', ''), 'chunks': r.get('chunk_count', 0)}
                for r in rows
            ] if rows else []
        except Exception as e:
            logger.warning(f"[KnowledgeService] 获取文档列表失败: {e}")
            return []

    def organize_knowledge(self, course_id, organize_type, ai_config=None):
        """
        根据课程资料自动提取知识点或生成复习提纲

        优先读取知识库目录中的 .md 文件（完整内容），
        降级到文档表的 content_text 字段。

        Args:
            course_id: 课程 ID
            organize_type: 'points' — 知识点清单, 'outline' — 复习提纲
            ai_config: 用户 AI 配置（可选）

        Returns:
            dict: {title, content(markdown), source_count}
        """
        from models.document import Document
        from models.course import Course
        from config import Config
        import os

        # 获取课程信息
        course = Course.find_by_id(course_id)
        course_name = course['name'] if course else '未知课程'

        # 获取课程所有文档
        docs = Document.find_by_course(course_id)
        if not docs:
            return {
                'title': f'《{course_name}》知识点整理',
                'content': '_该课程暂无资料，请先上传课程资料。_',
                'source_count': 0,
            }

        # 拼接文档内容：优先读 .md 知识库文件，降级到 content_text
        def read_doc_text(doc):
            md_path = doc.get('md_path', '')
            if md_path and os.path.exists(md_path):
                try:
                    with open(md_path, 'r', encoding='utf-8', errors='replace') as f:
                        return f.read()
                except Exception:
                    pass
            return doc.get('content_text') or ''

        context_parts = []
        for doc in docs:
            text = read_doc_text(doc).strip()
            if text:
                # 每篇最多取 8000 字
                text = text[:8000]
                context_parts.append(f"## {doc['original_name']}\n\n{text}")

        if not context_parts:
            return {
                'title': f'《{course_name}》知识点整理',
                'content': '_课程资料暂无文本内容，请上传含文本的文档。_',
                'source_count': 0,
            }

        context = '\n\n---\n\n'.join(context_parts)
        source_count = len(context_parts)
        cfg = ai_config or {}
        use_real_llm = cfg.get('use_real_llm')
        if use_real_llm is None:
            use_real_llm = Config.USE_REAL_LLM

        if use_real_llm:
            total_chars = len(context)
            if organize_type == 'points':
                system_prompt = """你是一位专业的课程知识整理助手。请根据提供的课程资料，提取核心知识点。

要求：
1. 按章节或主题分类，列出最重要的知识点
2. 每个知识点包括：名称、重要程度（⭐⭐⭐/⭐⭐/⭐）、简要说明
3. 用 Markdown 格式输出，结构清晰
4. 如果资料中有公式、代码、定义等重要内容，需保留

输出格式示例：
# 《课程名》核心知识点清单

## 一、第一章名称
### ⭐⭐⭐ 知识点1名称
简要说明...

### ⭐⭐ 知识点2名称
简要说明..."""
                user_prompt = f"""以下是课程《{course_name}》的资料内容（共{total_chars}字），请提取核心知识点清单：

{context}"""
            else:  # outline
                system_prompt = """你是一位专业的课程复习规划助手。请根据提供的课程资料，生成复习提纲。

要求：
1. 按章节主题组织，构建知识框架
2. 每个章节标注：重点掌握内容、常考题型、典型例题
3. 标注易错点和难点
4. 最后给出复习建议（含时间分配建议）
5. 用 Markdown 格式输出，层级清晰

输出格式示例：
# 《课程名》复习提纲

## 第一章 名称
### 重点内容
- ...
### 常考题型
- ...
### 易错点
- ..."""
                user_prompt = f"""以下是课程《{course_name}》的资料内容（共{total_chars}字），请生成复习提纲：

{context}"""

            # 调用 LLM
            from services.ai_service import ai_service
            messages = [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ]
            llm_result = ai_service._call_llm(
                messages, temperature=0.3, max_tokens=4096, ai_config=ai_config
            )

            if llm_result:
                title = f'《{course_name}》{"知识点清单" if organize_type == "points" else "复习提纲"}'
                result = {
                    'title': title,
                    'content': llm_result,
                    'source_count': source_count,
                }
                self._save_knowledge_result(course_id, organize_type, result)
                return result

        # 降级：纯文本规则提取
        points = []
        seen = set()
        for doc in docs[:5]:
            text = read_doc_text(doc)
            sentences = [s.strip() for s in text.replace('\n', '。').split('。') if s.strip()]
            for s in sentences:
                if len(s) >= 15 and s not in seen:
                    seen.add(s)
                    if organize_type == 'points':
                        points.append(f'- **{s[:40]}...**\n  - 来源：{doc["original_name"]}')
                    else:
                        points.append(f'- {s}')
                    if len(points) >= 30:
                        break
            if len(points) >= 30:
                break

        if organize_type == 'points':
            content = f'## 核心知识点（共{len(points)}条）\n\n' + '\n'.join(points)
        else:
            content = f'## 复习提纲\n\n' + '\n'.join(points)

        title = f'《{course_name}》{"知识点清单" if organize_type == "points" else "复习提纲"}'
        result = {
            'title': title,
            'content': content + '\n\n> *注：当前为自动提取结果，配置 AI 模型后可获得更精准的整理。*',
            'source_count': source_count,
        }

        # 自动存储结果
        self._save_knowledge_result(course_id, organize_type, result)
        return result

    # ==================== 知识点整理结果缓存 ====================

    def get_stored_knowledge(self, course_id, organize_type):
        """
        获取缓存的知识点整理结果

        Args:
            course_id: 课程 ID
            organize_type: 'points' | 'outline'

        Returns:
            dict | None — {title, content, source_count, created_at} 或 None
        """
        from database import db
        try:
            row = db.fetch_one(
                "SELECT content, source_count, created_at FROM course_knowledge "
                "WHERE course_id = ? AND type = ? ORDER BY created_at DESC LIMIT 1",
                (course_id, organize_type)
            )
            if row:
                from models.course import Course
                course = Course.find_by_id(course_id)
                course_name = course['name'] if course else ''
                type_label = '知识点清单' if organize_type == 'points' else '复习提纲'
                return {
                    'title': f'《{course_name}》{type_label}',
                    'content': row['content'],
                    'source_count': row['source_count'],
                    'created_at': str(row['created_at']),
                }
            return None
        except Exception as e:
            logger.warning(f"[KnowledgeService] 获取缓存结果失败: {e}")
            return None

    def auto_generate_if_needed(self, course_id, ai_config=None):
        """
        上传资料后自动生成知识点清单和复习提纲（后台静默执行）

        避免阻塞上传流程，使用 threading.Thread 延迟执行。
        仅当该课程尚无缓存结果时生成。
        """
        import threading

        def _generate():
            import time
            time.sleep(3)  # 等待管线处理完成+批量上传合并
            for t in ('points', 'outline'):
                try:
                    existing = self.get_stored_knowledge(course_id, t)
                    if not existing:
                        self.organize_knowledge(course_id, t, ai_config=ai_config)
                except Exception as e:
                    logger.warning(f"[KnowledgeService] 自动生成 {t} 失败: {e}")

        threading.Thread(target=_generate, daemon=True).start()

    @staticmethod
    def _save_knowledge_result(course_id, organize_type, result):
        """存储知识点整理结果到数据库"""
        from database import db
        try:
            # 删旧（同课程同类型只保留最新一条）
            db.delete(
                "DELETE FROM course_knowledge WHERE course_id = ? AND type = ?",
                (course_id, organize_type)
            )
            db.insert(
                "INSERT INTO course_knowledge (course_id, type, content, source_count) VALUES (?, ?, ?, ?)",
                (course_id, organize_type, result['content'], result['source_count'])
            )
        except Exception as e:
            logger.warning(f"[KnowledgeService] 存储结果失败: {e}")

    def format_context(self, results, temp_text=''):
        """
        将知识库结果格式化为 LLM 上下文文本块

        Args:
            results: KnowledgeResult[]（来自 search()）
            temp_text: 临时文件文本（可选）

        Returns:
            str — 上下文文本，或 None（无上下文时）
        """
        parts = []

        if temp_text:
            parts.append('【附件内容】（仅限本次对话有效）')
            parts.append(temp_text)
            parts.append('')

        if results:
            parts.append('【课程知识库参考资料】')
            for r in results:
                source = f'[{r["num"]}] 来源: {r["doc_name"]}'
                if r['heading_path']:
                    source += f' > {r["heading_path"]}'
                score_label = f'（相关度: {r["score"]:.2f}）' if r.get('score') else ''
                content = (r.get('content') or '')[:500]
                parts.append(f'{source} {score_label}\n{content}')
            parts.append('')
            parts.append(
                '请根据以上资料回答。引用时在句子末尾标注编号如 [1]，'
                '回答末尾列出你实际引用的「参考资料」章节。'
            )

        return '\n\n'.join(parts) if parts else None

    def format_citations(self, results):
        """
        将知识库结果格式化为前端引用列表

        Args:
            results: KnowledgeResult[]（来自 search()）

        Returns:
            list[dict] — 前端用的 citation 格式
        """
        if not results:
            return []

        return [
            {
                'num': r['num'],
                'doc_name': r['doc_name'],
                'heading_path': r['heading_path'],
                'document_id': r['document_id'],
                'score': r['score'],
                'source': r['source'],
            }
            for r in results
        ]

    @staticmethod
    def verify_citations(response_text, citations):
        """
        验证回答中实际引用了哪些来源

        对应 cherry-studio normalizeCitations:
          扫描 text 中的 [N] 标记 → 只保留实际引用的

        Returns:
            list[dict]: 实际被引用的 citation 子集
        """
        if not response_text or not citations:
            return citations or []

        import re
        used_nums = set()
        for m in re.finditer(r'\[(\d+)\]', response_text):
            used_nums.add(int(m.group(1)))

        if not used_nums:
            return []

        return [c for c in citations if c.get('num') in used_nums]

    @staticmethod
    def _load_doc_names(course_id):
        """加载课程文档 ID → 文件名映射"""
        try:
            from database import db
            rows = db.fetch_all(
                "SELECT id, original_name FROM documents WHERE course_id = ?",
                (course_id,)
            )
            return {r['id']: r['original_name'] for r in rows} if rows else {}
        except Exception:
            return {}


# 全局单例
knowledge_service = KnowledgeService()
