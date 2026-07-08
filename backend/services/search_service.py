import re
from models.document import Document

class SearchService:
    """资料检索服务"""

    def __init__(self):
        self.stop_words = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这'}

    def search(self, user_id, keyword, course_id=None, file_type=None):
        """
        全文检索
        支持按课程、文件类型筛选
        """
        if not keyword or not keyword.strip():
            return []

        # 清理关键词
        keyword = keyword.strip()

        # 执行搜索
        results = Document.search(user_id, keyword, course_id, file_type)

        # 添加高亮
        for doc in results:
            doc['highlighted_name'] = self._highlight(doc['original_name'], keyword)
            if doc.get('content_text'):
                doc['highlighted_content'] = self._highlight(doc['content_text'][:200], keyword)

        return results

    def _highlight(self, text, keyword):
        """关键词高亮"""
        if not text or not keyword:
            return text

        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        return pattern.sub(f'<mark>{keyword}</mark>', text)

    def extract_keywords(self, text):
        """从文本中提取关键词"""
        if not text:
            return []

        # 简单的关键词提取
        words = re.findall(r'[一-龥]{2,}|[a-zA-Z]{3,}', text)

        # 过滤停用词
        keywords = [w for w in words if w not in self.stop_words]

        # 统计词频
        freq = {}
        for word in keywords:
            freq[word] = freq.get(word, 0) + 1

        # 返回频率最高的10个词
        sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, count in sorted_words[:10]]

    def get_related_documents(self, doc_id, limit=5):
        """获取相关文档"""
        doc = Document.find_by_id(doc_id)
        if not doc:
            return []

        # 提取当前文档的关键词
        text = doc.get('content_text', '') or doc['original_name']
        keywords = self.extract_keywords(text)

        if not keywords:
            return []

        # 搜索相关文档
        related = []
        for keyword in keywords[:3]:
            results = Document.search(doc['user_id'], keyword, doc['course_id'])
            for r in results:
                if r['id'] != doc_id and r not in related:
                    related.append(r)
                    if len(related) >= limit:
                        break
            if len(related) >= limit:
                break

        return related
