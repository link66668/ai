import json
import re
import requests
import base64
from config import Config
from models.document import Document
from models.course import Course

class AIService:
    """AI服务 - 课程学习助手"""

    def __init__(self):
        self.course_contexts = {}  # 缓存课程上下文

    def chat(self, message, course_id=None, conversation_history=None):
        """
        课程问答 - 模拟AI回答
        基于关键词匹配和课程资料生成回答
        """
        # 获取课程相关资料作为上下文
        references = []
        context_docs = []

        if course_id:
            docs = Document.find_by_course(course_id)
            context_docs = docs[:3]  # 取前3个相关文档

            # 搜索相关内容
            keyword = self._extract_keyword(message)
            if keyword:
                # 获取课程所属用户的ID
                course = Course.find_by_id(course_id)
                user_id = course['user_id'] if course else 0
                search_results = Document.search(
                    user_id=user_id,
                    keyword=keyword,
                    course_id=course_id
                )
                if search_results:
                    context_docs = search_results[:3]

        # 构建参考资料
        for doc in context_docs:
            references.append({
                'doc_id': doc['id'],
                'doc_name': doc['original_name'],
                'category': doc['category'],
                'snippet': (doc['content_text'] or '')[:200] + '...'
            })

        # 生成回答
        response = self._generate_response(message, context_docs, course_id)

        return {
            'response': response,
            'references': references
        }

    def _extract_keyword(self, text):
        """从文本中提取关键词"""
        # 简单的关键词提取 - 去掉常见停用词
        stop_words = {'什么', '怎么', '如何', '为什么', '请问', '能', '可以', '吗', '呢', '的', '了', '是', '在', '和', '与'}
        words = re.findall(r'[一-龥a-zA-Z]+', text)
        keywords = [w for w in words if w not in stop_words and len(w) > 1]
        return keywords[0] if keywords else None

    def _generate_response(self, message, context_docs, course_id):
        """生成回答"""
        # 根据关键词和上下文生成模拟回答
        keyword = self._extract_keyword(message)

        if '概念' in message or '定义' in message:
            response = self._generate_concept_answer(message, context_docs)
        elif '怎么' in message or '如何' in message:
            response = self._generate_howto_answer(message, context_docs)
        elif '总结' in message or '复习' in message:
            response = self._generate_summary_answer(context_docs)
        elif context_docs:
            response = self._generate_context_answer(message, context_docs)
        else:
            response = self._generate_general_answer(message)

        return response

    def _generate_concept_answer(self, message, context_docs):
        """生成概念解释类回答"""
        doc_info = ""
        if context_docs:
            doc_info = f"\n\n根据课程资料《{context_docs[0]['original_name']}》中的相关内容：\n{context_docs[0].get('content_text', '')[:300]}..."

        return f"根据课程知识点，这个概念可以从以下几个方面理解：\n\n1. **基本定义**：这是课程中的核心概念之一\n2. **关键特征**：具有特定的属性和规律\n3. **应用场景**：在实际问题中有广泛应用{doc_info}\n\n建议结合课件和笔记进一步理解。"

    def _generate_howto_answer(self, message, context_docs):
        """生成方法指导类回答"""
        doc_info = ""
        if context_docs:
            doc_info = f"\n\n参考《{context_docs[0]['original_name']}》中的方法步骤：\n{context_docs[0].get('content_text', '')[:300]}..."

        return f"这个问题可以按以下步骤解决：\n\n1. **分析问题**：明确问题的已知条件和求解目标\n2. **选择方法**：根据问题类型选择合适的解题方法\n3. **执行计算**：按照步骤逐步求解\n4. **验证结果**：检查答案的合理性{doc_info}\n\n建议多做练习题巩固方法。"

    def _generate_summary_answer(self, context_docs):
        """生成总结类回答"""
        summary = "**课程要点总结**\n\n"
        for i, doc in enumerate(context_docs[:3], 1):
            summary += f"{i}. **{doc['original_name']}**：{doc.get('content_text', '')[:100]}...\n\n"

        summary += "\n建议按照以上知识点进行系统复习，重点掌握核心概念和方法。"
        return summary

    def _generate_context_answer(self, message, context_docs):
        """基于上下文生成回答"""
        response = "根据课程资料，我来为您解答：\n\n"

        for i, doc in enumerate(context_docs[:2], 1):
            response += f"**参考资料{i}** - 《{doc['original_name']}》：\n"
            content = doc.get('content_text', '')[:200]
            response += f"{content}...\n\n"

        response += "希望以上信息对您有帮助！如有疑问，请继续提问。"
        return response

    def _generate_general_answer(self, message):
        """生成通用回答"""
        return f"您的问题很好！作为课程学习助手，我建议您：\n\n1. 查阅相关课程课件和资料\n2. 结合课堂笔记理解重点\n3. 如有疑问可以上传相关资料，我可以帮您分析\n4. 制定学习计划，系统性地掌握知识\n\n请问您想深入了解哪个方面？"

    def summarize_text(self, text):
        """文本摘要"""
        if not text or len(text) < 50:
            return "文本内容较短，无需摘要。"

        # 简单摘要 - 取前几句
        sentences = re.split(r'[。！？\n]', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) <= 3:
            return text

        summary = "。".join(sentences[:3]) + "。"
        return f"**文本摘要**：{summary}"

    def extract_knowledge_points(self, text):
        """提取知识点"""
        if not text:
            return []

        # 简单的知识点提取
        points = []
        sentences = re.split(r'[。！？\n]', text)

        for i, sentence in enumerate(sentences[:10], 1):
            sentence = sentence.strip()
            if sentence and len(sentence) > 10:
                points.append({
                    'id': i,
                    'content': sentence,
                    'importance': '中'
                })

        return points

    def generate_study_plan(self, course_name, goal, exam_date, daily_hours):
        """生成学习计划"""
        from datetime import datetime, timedelta

        # 计算距离考试的天数
        if exam_date:
            exam = datetime.strptime(exam_date, '%Y-%m-%d')
            days_left = (exam - datetime.now()).days
        else:
            days_left = 30  # 默认30天

        # 生成计划
        plan = {
            'course': course_name,
            'goal': goal,
            'total_days': days_left,
            'daily_hours': daily_hours,
            'phases': []
        }

        # 分阶段
        if days_left >= 30:
            phases = [
                {'name': '基础阶段', 'days': days_left // 3, 'focus': '系统学习基础知识'},
                {'name': '提高阶段', 'days': days_left // 3, 'focus': '重点难点突破'},
                {'name': '冲刺阶段', 'days': days_left - 2 * (days_left // 3), 'focus': '模拟练习与复习'}
            ]
        else:
            phases = [
                {'name': '学习阶段', 'days': days_left * 2 // 3, 'focus': '核心知识点学习'},
                {'name': '复习阶段', 'days': days_left - days_left * 2 // 3, 'focus': '综合复习'}
            ]

        plan['phases'] = phases

        # 生成每日计划
        daily_plan = []
        current_date = datetime.now()

        for i in range(min(days_left, 7)):  # 只生成前7天的详细计划
            date = current_date + timedelta(days=i)
            daily_plan.append({
                'date': date.strftime('%Y-%m-%d'),
                'weekday': ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][date.weekday()],
                'tasks': [
                    f'复习笔记 {daily_hours/2:.1f}小时',
                    f'做题练习 {daily_hours/2:.1f}小时'
                ]
            })

        plan['daily_schedule'] = daily_plan
        return plan

    def decompose_task(self, task_title, description='', total_days=7, ai_config=None, daily_hours=None, user_id=None):
        """任务分解 - 增强版：支持自然语言智能拆解，含多课程编排 + 知识库优先"""
        from datetime import datetime, timedelta

        full_text = f"{task_title} {description}".strip()
        parsed = self._parse_nl_task(full_text)

        if parsed and parsed.get('total_days'):
            total_days = parsed['total_days']

        # 优先使用显式传入的 daily_hours，否则用自然语言解析的结果
        effective_daily_hours = daily_hours if daily_hours and daily_hours > 0 else parsed.get('daily_hours', 2.0) if parsed else 2.0

        # 知识库查询：用户是否有对应课程的资料
        kb_context = {}
        if parsed and parsed.get('course_names') and user_id:
            kb_context = self._query_user_knowledge_base(parsed['course_names'], user_id)

        # 多课程编排：按日课表生成
        if parsed and parsed.get('is_multi_course') and total_days >= 3:
            return self._generate_multi_course_smart_subtasks(
                parsed['course_names'],
                parsed.get('goal_type', '复习'),
                total_days,
                effective_daily_hours,
                ai_config=ai_config,
                kb_context=kb_context,
            )

        # 单课程智能拆解
        if parsed and parsed.get('course_names') and total_days >= 3:
            return self._generate_smart_subtasks(
                parsed['course_names'][0],
                parsed.get('goal_type', '复习'),
                total_days,
                effective_daily_hours,
                ai_config=ai_config,
                match_source=parsed.get('_match_source'),
                kb_context=kb_context.get(parsed['course_names'][0], ''),
            )

        # 有课程名但天数不足3天 → 也尝试 LLM 生成
        if parsed and parsed.get('course_names'):
            return self._generate_smart_subtasks(
                parsed['course_names'][0],
                parsed.get('goal_type', '复习'),
                max(total_days, 3),
                effective_daily_hours,
                ai_config=ai_config,
                match_source=parsed.get('_match_source'),
                kb_context=kb_context.get(parsed['course_names'][0], ''),
            )

        # 完全未识别课程名 → 用原始文本问 LLM
        if total_days >= 3:
            llm_plan = self._llm_generate_from_raw_text(full_text, total_days, ai_config=ai_config)
            if llm_plan:
                return self._build_subtasks_from_plan(llm_plan)

        # 最终兜底 —— 分阶段通用模板
        return self._mock_generate_subtasks(task_title, '学习', max(total_days, 3), effective_daily_hours)

    def _parse_nl_task(self, text):
        """
        解析自然语言任务描述，支持单课程和多课程
        单课程: "两周复习完高等数学期末考试"
        多课程: "两周内复习完高等数学和大学英语" / "30天学完Python和数据结构"
        返回: {course_names:[...], total_days, goal_type, daily_hours, is_multi_course}
        """
        import re

        result = {}

        # 1. 提取时长
        cn_num = {'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
        duration_patterns = [
            (r'(\d+)\s*周', lambda x: int(x) * 7),
            (r'(\d+)\s*天', lambda x: int(x)),
            (r'半年', lambda x: 180),
            (r'半\s*个?\s*月', lambda x: 15),
            (r'([一两二三四五六七八九十\d]+)\s*个?\s*月', lambda x: (cn_num.get(x, int(x)) if x.isdigit() else cn_num.get(x, 1)) * 30),
            (r'两\s*周', lambda x: 14),
            (r'一\s*周', lambda x: 7),
            (r'三\s*周', lambda x: 21),
            (r'([一两二三四五六七八九十])\s*天', lambda x: cn_num.get(x, 7)),
        ]
        for pattern, converter in duration_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    result['total_days'] = converter(match.group(1))
                except:
                    result['total_days'] = converter(None)
                break

        # 2. 提取目标类型
        if '期末' in text or '考试' in text:
            result['goal_type'] = '期末考试'
        elif '复习' in text:
            result['goal_type'] = '复习'
        elif '作业' in text:
            result['goal_type'] = '作业'
        elif '预习' in text:
            result['goal_type'] = '预习'
        elif '实验' in text:
            result['goal_type'] = '实验'
        elif '项目' in text:
            result['goal_type'] = '项目'
        elif '学完' in text or '学习' in text or '学' in text:
            result['goal_type'] = '学习'
        else:
            result['goal_type'] = '学习'

        # 3. 提取课程名称（支持多课程）
        # 课程关键词库 — 覆盖常见课程，用于兜底匹配
        course_keywords = [
            '高等数学', '线性代数', '概率论', '大学英语', '英语',
            'Python', 'C语言', 'Java', '数据结构', '算法',
            '计算机网络', '操作系统', '数据库', '机器学习', '深度学习',
            '大学物理', '电路分析', '信号与系统',
            '微观经济学', '宏观经济学', '管理学',
            '马克思主义', '毛概', '思修', '近代史',
        ]

        # 课程简称→全称映射表
        course_aliases = {
            '高数': '高等数学',
            '大英': '大学英语',
            '线代': '线性代数',
            '大物': '大学物理',
            '计网': '计算机网络',
            'OS': '操作系统',
            'DB': '数据库',
            'ML': '机器学习',
            'DL': '深度学习',
            'DS': '数据结构',
            '马原': '马克思主义',
        }

        known_courses = self._get_known_course_names()

        found_courses = []
        remaining_text = text
        # 去除常见的动作/时长/虚词，避免被当成课程名
        _clean_patterns = ['两周', '三周', '一周', '一个月', '半个月',
            '三个月', '两个月', '四个月', '五个月', '六个月', '个月',
            '半年', '三年', '四年',
            '三天', '五天', '七天', '十天', '天内', '天之内', '每天', '我要', '学完',
            '学好', '学会', '掌握', '复习', '学习', '搞定', '搞懂',
            '学期', '之内', '如何', '怎么', '需要', '帮忙', '帮我',
            '开始', '准备', '预习', '完成', '今天', '明天', '几个月',
        ]
        for _cp in _clean_patterns:
            remaining_text = remaining_text.replace(_cp, ' ')
        # 正则兜底：清除 \(\d+天(之?内)?\) 及其同义变体
        remaining_text = re.sub(r'(?:在|的|这|那|余下|剩下)?\d+\s*天(?:\s*之?\s*内)?', ' ', remaining_text)
        remaining_text = re.sub(r'[天日]内\b', ' ', remaining_text)
        match_source = None  # 记录课程匹配来源

        # 第一步：DB已有课程精确匹配
        sorted_known = sorted(known_courses, key=len, reverse=True)
        for cname in sorted_known:
            if cname in remaining_text:
                found_courses.append(cname)
                remaining_text = remaining_text.replace(cname, '', 1)
                match_source = 'db'

        # 第二步：简称映射 → 优先DB已有，否则用全称
        if not found_courses:
            for alias, full_name in sorted(course_aliases.items(), key=lambda x: -len(x[0])):
                if alias in remaining_text:
                    target = full_name if full_name in known_courses else full_name
                    found_courses.append(target)
                    remaining_text = remaining_text.replace(alias, '', 1)
                    match_source = 'alias'

        # 第三步：预置关键词库匹配（如"数据库"等课程名）
        if not found_courses:
            for kw in sorted(course_keywords, key=len, reverse=True):
                if kw in remaining_text:
                    found_courses.append(kw)
                    remaining_text = remaining_text.replace(kw, '', 1)
                    match_source = 'keyword'

        # 第四步：用文本片段模糊匹配DB已有课程（如"数"→"高等数学"）
        if not found_courses:
            candidates = re.findall(r'[\u4e00-\u9fff]{2,6}|[a-zA-Z]{2,10}', remaining_text)
            for cand in candidates:
                # 先找DB中匹配的
                for cname in known_courses:
                    if cand in cname or cname in cand:
                        found_courses.append(cname)
                        match_source = 'fuzzy_db'
                        break
                if found_courses:
                    break
                # 再找关键词库中匹配的
                for kw in course_keywords:
                    if cand == kw or cand in kw or kw in cand:
                        found_courses.append(kw)
                        match_source = 'fuzzy_kw'
                        break
                if found_courses:
                    break

        # 第五步：以上都失败，但文本中有2-4字中文词 → 直接作为课程名使用（未知课程）
        if not found_courses:
            candidates = re.findall(r'[\u4e00-\u9fff]{2,4}', remaining_text)
            # 排除常见非课程词
            skip_words = {'我要', '两周', '一周', '三天', '七天', '每天', '小时', '复习', '学完', '考试',
                          '准备', '预习', '学习', '今天', '明天', '开始', '完成', '怎么', '如何',
                          '好好', '帮忙', '帮我', '需要', '一个', '这个', '那个', '什么', '或者',
                          '还有', '以及', '是否', '可以', '应该', '能够', '不能', '已经', '没有',
                          '计划', '任务', '时间', '分钟', '之内', '期末', '期中', '之内',
                          '我想', '想学', '学点', '东西', '知道', '学什', '但不', '不知',
                          '个月', '三个月', '两个月', '几个月', '内学', '完', '天内', '天之内'}
            for cc in cn_candidates:
                if cand not in skip_words and len(cand) >= 2:
                    found_courses.append(cand)
                    match_source = 'guess'
                    break

        # 多课程：如果有连接词，在剩余文本中继续搜课程名
        if re.search(r'[和、与,，]', text):
            # 先尝试关键词库
            for kw in sorted(course_keywords, key=len, reverse=True):
                if kw in remaining_text and kw not in found_courses:
                    found_courses.append(kw)
                    remaining_text = remaining_text.replace(kw, '', 1)
            # 再尝试英文课程名（Python, Java, C语言等）
            en_candidates = re.findall(r'[a-zA-Z][a-zA-Z0-9+#]*', remaining_text)
            for ec in en_candidates:
                ec_clean = ec.strip().lower()
                if ec_clean in ('python', 'java', 'c', 'cpp', 'c++', 'go', 'rust', 'sql',
                                'html', 'css', 'javascript', 'js', 'php', 'ruby', 'swift',
                                'kotlin', 'r', 'matlab', 'scala', 'perl', 'typescript', 'ts'):
                    # 规范化常见写法
                    canon = {'cpp': 'C++', 'js': 'JavaScript', 'ts': 'TypeScript'}.get(ec_clean, ec.title())
                    if canon not in found_courses:
                        found_courses.append(canon)
                        remaining_text = remaining_text.replace(ec, '', 1)
            # 最后尝试剩余中文词：先剥离连接词和干扰词再提取
            clean_for_cn = re.sub(r'[和与、,，]+', ' ', remaining_text)
            cn_candidates = re.findall(r'[\u4e00-\u9fff]{2,5}', clean_for_cn)
            skip_words2 = {'我要', '两周', '一周', '三天', '七天', '每天', '小时', '复习', '学完', '考试',
                          '准备', '预习', '学习', '今天', '明天', '开始', '完成', '怎么', '如何',
                          '好好', '帮忙', '帮我', '需要', '一个', '这个', '那个', '什么', '或者',
                          '还有', '以及', '是否', '可以', '应该', '能够', '不能', '已经', '没有',
                          '计划', '任务', '时间', '分钟', '之内', '期末', '期中', '之内',
                          '我想', '想学', '学点', '东西', '知道', '学什', '但不', '不知',
                          '个月', '三个月', '两个月', '几个月', '内学', '完', '天内', '天之内'}
            _skip_pref = {'学','用','做','写','看','读','上','去','来','在','要','给','把','被','从','让','天','个','月','日','时','分'}
            for cc in cn_candidates:
                if cc in skip_words2: continue
                if any(cc.startswith(p) for p in _skip_pref): continue
                if not found_courses: break
                # 尝试将短词映射到已知关键词（如 "网络" → "计算机网络"）
                matched = False
                for kw in course_keywords:
                    if cc in kw and kw not in found_courses:
                        found_courses.append(kw)
                        remaining_text = remaining_text.replace(cc, '', 1)
                        matched = True
                        break
                if not matched and cc not in found_courses:
                    found_courses.append(cc)
                    remaining_text = remaining_text.replace(cc, '', 1)

        # 去重
        seen = set()
        found_courses = [c for c in found_courses if not (c in seen or seen.add(c))]

        if found_courses:
            result['course_names'] = found_courses
            result['is_multi_course'] = len(found_courses) > 1
            result['_match_source'] = match_source
        elif not result.get('total_days'):
            return None

        # 4. 提取时长和标记有效性
        if result.get('total_days') and result.get('course_names'):
            hours_match = re.search(r'每天\s*(\d+)\s*小时', text)
            if hours_match:
                result['daily_hours'] = float(hours_match.group(1))
            elif result['total_days'] <= 7:
                result['daily_hours'] = 3.0
            elif result['total_days'] <= 14:
                result['daily_hours'] = 2.5
            else:
                result['daily_hours'] = 2.0

            return result

        # 课程匹配成功但未识别天数 → 仍返回部分结果
        if result.get('course_names'):
            result['daily_hours'] = 2.0
            return result

        return None

    def _get_known_course_names(self):
        """从已上传的课程资料中提取已知课程名"""
        try:
            from models.course import Course as CourseModel
            from database import db
            courses = db.fetch_all("SELECT DISTINCT name FROM courses")
            return [c['name'] for c in courses] if courses else []
        except Exception:
            return []

    def _query_user_knowledge_base(self, course_names, user_id):
        """查询用户知识库中对应课程的内容，返回 {course_name: knowledge_text}
        
        用于将用户上传的课程资料作为 LLM 任务拆解的上下文。
        有知识库 → 返回内容，LLM 基于真实教材/课件生成任务。
        无知识库 → 返回空字符串，LLM 用自己的知识生成。
        """
        kb_context = {}
        if not user_id:
            return kb_context

        try:
            from database import db
            from models.course import Course as CourseModel

            for cn in course_names:
                courses = db.fetch_all(
                    "SELECT id, name FROM courses WHERE name LIKE ? AND user_id = ?",
                    (f'%{cn}%', user_id)
                )
                if not courses:
                    courses = db.fetch_all(
                        "SELECT id, name FROM courses WHERE name LIKE ? AND user_id = ?",
                        (f'%{cn[:2]}%', user_id)
                    )
                
                context_parts = []
                for course in courses:
                    cid = course['id']
                    # 从 document_chunks 表获取知识点片段
                    chunks = db.fetch_all(
                        "SELECT content FROM document_chunks WHERE course_id = ? ORDER BY chunk_index LIMIT 20",
                        (cid,)
                    )
                    if chunks:
                        for ch in chunks:
                            content = (ch.get('content') or '').strip()
                            if len(content) > 20:
                                context_parts.append(content)
                    else:
                        # 从 documents 的 content_text 获取
                        docs = db.fetch_all(
                            "SELECT content_text FROM documents WHERE course_id = ? AND content_text != '' LIMIT 3",
                            (cid,)
                        )
                        for doc in docs:
                            text = (doc.get('content_text') or '')
                            if text and len(text) > 30:
                                context_parts.append(text[:800])

                if context_parts:
                    kb_context[cn] = '\n'.join(context_parts[:15])
                    print(f"[KB] 为课程 '{cn}' 找到 {len(context_parts[:15])} 条知识库内容")
                else:
                    kb_context[cn] = ''
                    print(f"[KB] 课程 '{cn}' 无知识库，将使用 LLM 通用知识")

        except Exception as e:
            print(f"[KB] 知识库查询异常: {e}")

        return kb_context

    def _generate_smart_subtasks(self, course_name, goal_type, total_days, daily_hours=2.0, ai_config=None, match_source=None, kb_context=''):
        """生成智能阶段+每日任务拆解 - LLM优先，Mock兜底"""
        from datetime import datetime, timedelta

        llm_plan = self._llm_generate_task_plan(course_name, goal_type, total_days, daily_hours, ai_config=ai_config, match_source=match_source, kb_context=kb_context)
        if llm_plan:
            return self._build_subtasks_from_plan(llm_plan)

        return self._mock_generate_subtasks(course_name, goal_type, total_days, daily_hours)

    def _build_subtasks_from_plan(self, llm_plan):
        """将 LLM 规划结果转为 subtask 列表"""
        from datetime import datetime, timedelta
        subtasks = []
        current_date = datetime.now()
        order = 0
        total_days = sum(p.get('end_day', 0) - p.get('start_day', 0) + 1 for p in llm_plan.get('phases', []))

        for phase in llm_plan.get('phases', []):
            order += 1
            phase_start = phase.get('start_day', 1)
            phase_end = phase.get('end_day', total_days)
            phase_name = phase.get('phase_name', '')

            subtasks.append({
                'title': f'📋 {phase_name}（第{phase_start}-{phase_end}天）',
                'description': phase.get('focus', ''),
                'due_date': (current_date + timedelta(days=phase_end - 1)).strftime('%Y-%m-%d'),
                'order': order,
                'phase': phase_name,
                'is_phase_header': True,
            })

            for dt in phase.get('daily_tasks', []):
                order += 1
                day_num = dt.get('day', 1)
                date = current_date + timedelta(days=day_num - 1)
                task_title = dt.get('title', f'第{day_num}天学习任务')
                task_desc = dt.get('description', '')
                task_hours = dt.get('suggested_hours', 2.0)

                subtasks.append({
                    'title': f'第{day_num}天：{task_title} · ⏱{task_hours}h',
                    'description': f'{task_desc}\n建议学习时长：{task_hours}小时',
                    'due_date': date.strftime('%Y-%m-%d'),
                    'order': order,
                    'phase': phase_name,
                    'day': day_num,
                    'is_daily_task': True,
                    'estimated_hours': task_hours,
                })

        return subtasks

    def _mock_generate_subtasks(self, course_name, goal_type, total_days, daily_hours=2.0):
        """Mock 模式生成任务（原有逻辑）"""

        from datetime import datetime, timedelta

        subtasks = []
        current_date = datetime.now()
        order = 0

        # 获取课程相关的知识点
        knowledge = self._get_course_knowledge(course_name)

        # 分阶段
        if total_days >= 21:
            phases = [
                {'name': '基础夯实阶段', 'start': 1, 'end': total_days * 3 // 10, 'focus': '系统梳理知识体系，掌握基本概念和核心公式'},
                {'name': '强化提升阶段', 'start': total_days * 3 // 10 + 1, 'end': total_days * 6 // 10, 'focus': '重点难点突破，大量练习巩固'},
                {'name': '综合冲刺阶段', 'start': total_days * 6 // 10 + 1, 'end': total_days * 8 // 10, 'focus': '真题模拟，综合运用'},
                {'name': '查漏补缺阶段', 'start': total_days * 8 // 10 + 1, 'end': total_days, 'focus': '回顾错题，强化薄弱环节，考前调整心态'},
            ]
        elif total_days >= 10:
            phases = [
                {'name': '基础学习阶段', 'start': 1, 'end': total_days // 2, 'focus': '系统学习核心知识点，理解基本概念'},
                {'name': '强化训练阶段', 'start': total_days // 2 + 1, 'end': total_days * 3 // 4, 'focus': '重点突破，练习典型题目'},
                {'name': '冲刺复习阶段', 'start': total_days * 3 // 4 + 1, 'end': total_days, 'focus': '模拟测试，查漏补缺'},
            ]
        else:
            phases = [
                {'name': '集中学习阶段', 'start': 1, 'end': total_days * 2 // 3, 'focus': '聚焦核心知识点，高效学习'},
                {'name': '复习巩固阶段', 'start': total_days * 2 // 3 + 1, 'end': total_days, 'focus': '回顾总结，练习巩固'},
            ]

        # 为每个阶段生成阶段标记任务
        for phase in phases:
            order += 1
            phase_task = {
                'title': f'📋 {phase["name"]}（第{phase["start"]}-{phase["end"]}天）',
                'description': phase['focus'],
                'due_date': (current_date + timedelta(days=phase['end'])).strftime('%Y-%m-%d'),
                'order': order,
                'phase': phase['name'],
                'is_phase_header': True,
            }
            subtasks.append(phase_task)

        # 生成每日任务
        day = 1
        knowledge_index = 0
        for phase in phases:
            for day_in_phase in range(phase['end'] - phase['start'] + 1):
                order += 1
                date = current_date + timedelta(days=day - 1)

                # 根据阶段和日期生成具体的每日任务
                task_title = self._generate_daily_task_title(
                    course_name, goal_type, phase['name'], day_in_phase + 1,
                    knowledge, knowledge_index
                )

                # 根据阶段、天数和知识点位置估算难度级别（差异化）
                phase_days = phase['end'] - phase['start'] + 1
                progress_ratio = (day_in_phase + 1) / max(phase_days, 1)

                if '基础' in phase['name']:
                    base = daily_hours * 0.7
                elif '强化' in phase['name']:
                    base = daily_hours * 0.9
                elif '冲刺' in phase['name']:
                    base = daily_hours * 1.0
                elif '综合' in phase['name']:
                    base = daily_hours * 1.1
                else:
                    base = daily_hours

                variation = 0.3 + progress_ratio * 0.5
                if knowledge_index % 3 == 0:
                    variation += 0.2
                elif knowledge_index % 5 == 0:
                    variation -= 0.3
                task_hours = max(0.5, min(4.0, round(base * variation, 1)))

                day_task = {
                    'title': f'第{day}天：{task_title} · ⏱{task_hours}h',
                    'description': f'今日重点：{task_title}。按照教学进度系统学习，结合笔记与练习题巩固所学内容，预计 {task_hours} 小时。',
                    'due_date': date.strftime('%Y-%m-%d'),
                    'order': order,
                    'phase': phase['name'],
                    'day': day,
                    'is_daily_task': True,
                    'estimated_hours': task_hours,
                }
                subtasks.append(day_task)

                knowledge_index = (knowledge_index + 1) % max(len(knowledge), 1)
                day += 1

        return subtasks

    def _get_course_knowledge(self, course_name):
        """从已上传的资料中获取课程知识点——预设知识点优先"""
        # 先检查是否有预设知识点
        preset = self._get_default_knowledge(course_name)
        is_preset = not preset[0].startswith(course_name + '核心') if preset else False

        if is_preset:
            return preset

        knowledge_points = []
        try:
            from models.document import Document
            from models.course import Course as CourseModel
            from database import db

            courses = db.fetch_all(
                "SELECT id FROM courses WHERE name LIKE ?",
                (f'%{course_name}%',)
            )
            if courses:
                for course in courses:
                    docs = Document.find_by_course(course['id'])
                    for doc in docs:
                        text = doc.get('content_text', '')
                        if text:
                            sentences = re.split(r'[。！？\n]', text)
                            for s in sentences:
                                s = s.strip()
                                if len(s) > 8 and len(s) < 60:
                                    knowledge_points.append(s)
                            break

            if not knowledge_points:
                knowledge_points = preset
        except Exception:
            knowledge_points = preset

        return knowledge_points or [f'{course_name}核心知识点学习']

    def _get_default_knowledge(self, course_name):
        """根据课程名返回默认知识点"""
        defaults = {
            '高等数学': [
                '函数的概念与性质', '极限的定义与计算', '极限运算法则',
                '导数的概念与几何意义', '求导法则', '函数的单调性与极值',
                '不定积分', '定积分的定义与性质', '定积分的应用',
                '微分方程基础', '线性代数基础', '向量空间与线性变换',
            ],
            '线性代数': [
                '矩阵的定义与基本运算', '行列式的计算', '矩阵的逆',
                '向量组的线性相关性', '线性方程组的解法', '特征值与特征向量',
                '二次型', '线性空间与线性变换',
            ],
            '概率论': [
                '随机事件与概率', '条件概率与独立性', '随机变量及其分布',
                '多维随机变量', '数字特征', '大数定律与中心极限定理',
            ],
            'Python': ['变量与数据类型', '条件判断与循环', '函数定义与调用',
                '列表与字典操作', '文件读写', '面向对象编程基础',
                '异常处理机制', '模块与包管理',
            ],
            'C语言': ['数据类型与运算符', '流程控制语句', '函数与递归',
                '数组与字符串', '指针与内存管理', '结构体与联合体',
                '文件操作', '动态内存分配',
            ],
            'Java': ['面向对象基础', '类与对象', '继承与多态',
                '接口与抽象类', '集合框架', '异常处理', 'IO流', '多线程编程',
            ],
            '数据结构': ['线性表', '栈与队列', '树与二叉树',
                '图结构', '查找算法', '排序算法', '哈希表',
            ],
            '算法': ['算法复杂度分析', '分治算法', '动态规划',
                '贪心算法', '回溯算法', '图论算法', '字符串匹配',
            ],
            '计算机网络': ['网络体系结构', '物理层与数据链路层', '网络层',
                '传输层TCP/UDP', '应用层协议', '网络安全基础',
            ],
            '操作系统': ['进程管理', '线程与并发', '内存管理',
                '文件系统', '设备管理', '死锁处理', '进程调度算法',
            ],
            '数据库': ['关系模型', 'SQL语法', '数据库设计',
                '事务与并发控制', '索引与查询优化', 'NoSQL入门',
            ],
            '机器学习': ['监督学习', '线性回归', '逻辑回归',
                '决策树', '支持向量机', '集成学习', '聚类算法', '神经网络基础',
            ],
            '深度学习': ['神经网络基础', 'CNN卷积网络', 'RNN与LSTM',
                'Transformer架构', '生成对抗网络', '迁移学习',
                '模型训练技巧', 'PyTorch入门',
            ],
            '编译原理': [
                '编译器概述与结构', '词法分析与正则表达式', '有限自动机',
                '上下文无关文法', '自顶向下语法分析', '自底向上语法分析',
                '语法制导翻译', '中间代码生成', '运行时环境',
                '代码优化技术', '目标代码生成',
            ],
            '离散数学': [
                '命题逻辑', '谓词逻辑', '集合论', '关系与函数',
                '代数系统', '图论基础', '树与生成树路径', '组合计数',
            ],
            '计算机组成': [
                '计算机系统概述', '数据表示', '运算方法',
                '指令系统', '中央处理器', '存储层次结构', '输入输出系统',
            ],
            '大学物理': [
                '质点运动学', '牛顿运动定律', '动量与能量',
                '刚体转动', '静电场', '磁场', '电磁感应', '热力学基础',
            ],
            '电路分析': [
                '电路基本定律', '电阻电路分析', '动态电路时域分析',
                '正弦稳态分析', '互感与变压器', '频率响应',
            ],
            '信号与系统': [
                '信号的基本概念', '线性时不变系统', '傅里叶级数',
                '傅里叶变换', '拉普拉斯变换', 'Z变换', '采样定理',
            ],
            '模电': [
                '半导体基础', '二极管及其电路', '三极管放大电路',
                '场效应管', '集成运算放大器', '反馈放大电路', '信号处理电路',
            ],
            '数电': [
                '逻辑代数基础', '组合逻辑电路', '时序逻辑电路',
                '触发器', '计数器', '555定时器', 'ADC/DAC转换',
            ],
            '大学英语': [
                '词汇积累方法', '长难句分析', '阅读技巧',
                '写作模板', '翻译技巧', '听力训练',
            ],
            '微观经济学': [
                '供需理论', '弹性理论', '消费者选择',
                '生产与成本', '市场结构', '博弈论基础',
            ],
            '宏观经济学': [
                'GDP核算', 'IS-LM模型', 'AD-AS模型',
                '失业与通货膨胀', '财政政策', '货币政策',
            ],
            '毛概': [
                '毛泽东思想', '新民主主义革命', '社会主义改造',
                '社会主义建设', '邓小平理论', '三个代表', '科学发展观',
            ],
            '马克思主义': [
                '哲学基本问题', '唯物辩证法', '实践与认识',
                '社会基本矛盾', '资本主义分析', '社会主义理论',
            ],
            '思修': [
                '人生观与价值观', '理想信念', '中国精神',
                '社会主义核心价值观', '法治思维', '道德规范',
            ],
            '近代史': [
                '鸦片战争', '太平天国', '洋务运动',
                '戊戌变法', '辛亥革命', '五四运动',
                '抗日战争', '解放战争',
            ],
        }

        for key, value in defaults.items():
            if key in course_name or course_name in key:
                return value

        return [
            f'{course_name}核心概念掌握', f'{course_name}基础知识点梳理',
            f'{course_name}典型题型练习', f'{course_name}重点难点突破',
            f'{course_name}综合应用能力', f'{course_name}常见问题与解决方法',
        ]

    def _generate_daily_task_title(self, course_name, goal_type, phase_name, day_in_phase, knowledge, knowledge_index):
        """根据阶段和知识点生成每日任务标题——有具体知识点时返回章节式标题"""
        import re

        # 获取当前知识点
        kp = knowledge[knowledge_index] if knowledge and knowledge_index < len(knowledge) else ''

        # 判断知识点是否是"公式化兜底"（如 "编译原理核心概念掌握"）——不含课程名则算真实知识点
        is_real_kp = kp and course_name not in kp and '核心概念' not in kp and '基础知识点' not in kp and '综合应用' not in kp and '重点难点' not in kp and '常见问题' not in kp and '典型题型' not in kp

        match_suffix = {
            '基础': '概念理解与笔记整理',
            '学习': '概念理解与笔记整理',
            '强化': '题型练习与解题训练',
            '提升': '题型练习与解题训练',
            '冲刺': '真题演练与查漏补缺',
            '查漏': '薄弱点回顾与巩固',
            '复习': '知识点回顾与总结',
            '巩固': '知识点回顾与总结',
            '集中': '核心内容学习',
        }

        suffix = '学习与练习'
        for key, val in match_suffix.items():
            if key in phase_name:
                suffix = val
                break

        # 有真实章节知识点 → 直接用
        if is_real_kp:
            # 每隔一天轮换"学习"和"练习"模式
            action = '理论精讲' if day_in_phase % 2 == 1 else '练习与巩固'
            return f'{kp} — {action}'

        # 兜底：用课程名+阶段生成公式化但合理的标题
        day_actions = {
            1: f'{course_name}课程框架梳理与学习目标制定',
            2: f'{course_name}基础概念与核心术语学习',
        }
        if day_in_phase in day_actions:
            return day_actions[day_in_phase]

        if knowledge and knowledge_index < len(knowledge):
            return f'{knowledge[knowledge_index]} — {suffix}'
        else:
            return f'{course_name} — {suffix}（第{day_in_phase}天）'

    def _llm_generate_task_plan(self, course_name, goal_type, total_days, daily_hours, ai_config=None, match_source=None, kb_context=''):
        """调用大模型生成详细任务规划，失败返回 None"""
        cfg = ai_config or {}
        use_real_llm = cfg.get('use_real_llm', Config.USE_REAL_LLM)
        if not use_real_llm:
            return None

        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')

        knowledge = self._get_course_knowledge(course_name)
        knowledge_text = '\n'.join([f'- {k}' for k in knowledge[:15]]) if knowledge else '无现有资料'

        # 知识库上下文：用户上传的真实教材/课件内容
        has_kb = bool(kb_context and kb_context.strip())
        kb_section = ''
        if has_kb:
            kb_section = f"""
【用户已上传的知识库内容 — 请严格基于此内容规划】
{kb_context[:3000]}

基于以上知识库内容，按章节顺序拆分每日任务。"""
        else:
            kb_section = '（用户尚未上传该课程的知识库资料，请基于你的通用知识进行规划）'

        # 未知课程：让 LLM 先识别课程结构再规划
        is_unknown = match_source in ('guess', 'fuzzy_kw', None)

        if is_unknown:
            user_prompt = f"""请为此课程制定极度详细的学习计划。

用户请求：学习"{course_name}"
目标：{goal_type}
总天数：{total_days}天，用户每天可投入约{daily_hours}小时
开始日期：{today}
{kb_section}

重要：你比用户更了解这门课程。请先根据你的知识，列出"{course_name}"的典型章节和知识点体系，然后按照章节顺序制定每日计划。

务必做到：
1. 每天任务 title 必须带章节号（如"第一章§1.1 编译器概述"）
2. description 按步骤写：学习具体知识点→练习/实操→总结，每步标注分钟数
3. suggested_hours 逐天不同，按难度分级（简单概念0.5-1.0h，中等练习1.0-2.0h，困难章节2.0-3.0h，综合复习2.5-4.0h），同一阶段内高低交错
4. 阶段递进（基础→进阶→综合），最后1-2天安排总复习
5. 输出纯JSON，不要任何额外文字"""
        else:
            user_prompt = f"""请制定极度详细的学习任务计划：

课程：{course_name}
目标：{goal_type}
总天数：{total_days}天，用户每天可投入约{daily_hours}小时
开始日期：{today}
现有资料知识点：{knowledge_text}
{kb_section}

务必做到：
1. 每天任务 title 必须带章节号（如"第二章§2.1 导数的概念与几何意义"）
2. description 按步骤写：阅读教材哪几页→看哪一讲课件→做哪些习题（标注题号），每步标注分钟数
3. suggested_hours 逐天不同，按任务难度分级：
   - 简单概念入门课 = 0.5-1.0h
   - 一般知识点+少量练习 = 1.0-1.5h
   - 中等知识点+标准习题 = 1.5-2.0h
   - 较难章节+大量练习 = 2.0-2.5h
   - 高难度综合/模拟测试 = 2.5-4.0h
   整个计划中至少出现 4 种不同的时长值，同一阶段内高低交错
4. 输出纯JSON，不要任何额外文字"""

        messages = [
            {
                'role': 'system',
                'content': self._get_task_planning_system_prompt()
            },
            {
                'role': 'user',
                'content': user_prompt
            }
        ]

        response = self._call_llm(messages, temperature=0.3, max_tokens=4096, ai_config=ai_config)
        if not response:
            return None

        return self._parse_llm_task_plan(response)

    def _llm_generate_from_raw_text(self, raw_text, total_days, ai_config=None):
        """完全未识别课程名时，用原始文本直接问 LLM 生成计划"""
        cfg = ai_config or {}
        use_real_llm = cfg.get('use_real_llm', Config.USE_REAL_LLM)
        if not use_real_llm:
            return None

        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')

        messages = [
            {
                'role': 'system',
                'content': self._get_task_planning_system_prompt()
            },
            {
                'role': 'user',
                'content': f"""用户提出了以下学习任务，请为其制定极度详细的学习计划：

任务描述：{raw_text}
总天数：{total_days}天
开始日期：{today}

请先分析这个任务涉及什么课程/技能，列出典型的章节或学习模块，然后制定每日详细计划。
每天任务 title 带章节号/模块名，description 步骤化并标注时间。
suggested_hours 按任务难度逐天不同，0.5-4.0h范围，至少出现4种不同值。
输出纯JSON，不要任何额外文字。"""
            }
        ]

        response = self._call_llm(messages, temperature=0.3, max_tokens=2048, ai_config=ai_config)
        if not response:
            return None

        return self._parse_llm_task_plan(response)

    def _get_task_planning_system_prompt(self):
        return """你是专业学习规划师。为课程制定极度详细、可执行的学习计划。

核心输出要求（逐条执行）：
1. 按章节和知识点拆分：title 必须包含章节号、知识点名称。如"第一章§1.1 函数的概念与性质"
2. description 必须极度详细：指定具体阅读教材哪几页、做哪些课后习题（题号）、看哪些课件、预计每小步耗时几分钟
3. 阶段划分：2-4个阶段（基础→强化→冲刺→查缺补漏），最后一天安排"考前回顾与心态调整"
4. suggested_hours 必须根据任务难度逐天不同，不能全部一样：
   - 简单概念/入门课 = 0.5-1.0h
   - 一般知识点+少量练习 = 1.0-1.5h
   - 中等知识点+标准练习 = 1.5-2.0h
   - 较难章节+大量练习 = 2.0-2.5h
   - 高难度综合/模拟测试 = 2.5-3.5h
   整个计划中至少出现 4 种不同的时长值
5. 优先基于"已有知识点资料"来细化，资料中没有的章节也要合理规划进去

输出纯JSON，不要任何解释文字：

```json
{
  "plan_summary": "一句话概括",
  "phases": [{
    "phase_name": "基础夯实阶段",
    "start_day": 1,
    "end_day": 7,
    "focus": "一句话",
    "daily_tasks": [{
      "day": 1,
      "title": "第X章§X.X 知识点名称",
      "description": "1.阅读教材PXX-PXX(XX分钟)→2.观看课件第X讲(XX分钟)→3.完成习题X.X-X.X(XX分钟)",
      "suggested_hours": 1.0
    }]
  }]
}
```"""

    def _call_llm(self, messages, temperature=0.7, max_tokens=4096, ai_config=None):
        """调用 DeepSeek API"""
        cfg = ai_config or {}
        api_url = cfg.get('ai_api_url') or Config.AI_API_URL
        api_key = cfg.get('ai_api_key') or Config.AI_API_KEY
        model = cfg.get('ai_model') or Config.AI_MODEL

        try:
            resp = requests.post(
                f"{api_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                },
                timeout=90
            )
            if resp.status_code == 200:
                data = resp.json()
                return data['choices'][0]['message']['content']
            else:
                print(f"[LLM] API error {resp.status_code}: {resp.text[:300]}")
                return None
        except requests.exceptions.Timeout:
            print("[LLM] Request timeout")
            return None
        except Exception as e:
            print(f"[LLM] Request failed: {e}")
            return None

    def _verify_llm_available(self, ai_config=None):
        """验证 LLM API 是否可用，返回 (ok, error_message_for_user)"""
        cfg = ai_config or {}
        use_real_llm = cfg.get('use_real_llm', Config.USE_REAL_LLM)
        if not use_real_llm:
            return True, ''

        api_url = cfg.get('ai_api_url') or Config.AI_API_URL
        api_key = cfg.get('ai_api_key') or Config.AI_API_KEY
        model = cfg.get('ai_model') or Config.AI_MODEL

        if not api_key:
            return False, '未配置大模型 API Key，请在「AI 配置」页面填写 API 密钥后再试'

        try:
            resp = requests.post(
                f"{api_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                    "temperature": 0
                },
                timeout=15
            )
            if resp.status_code == 200:
                return True, ''
            elif resp.status_code == 401 or resp.status_code == 403:
                return False, '大模型 API 认证失败，请检查「AI 配置」中的 API Key 是否正确'
            elif resp.status_code == 404:
                return False, f'模型 {model} 不可用，请检查「AI 配置」中的模型名称或 API 地址'
            else:
                return False, f'大模型 API 返回异常（{resp.status_code}），请检查「AI 配置」后重试'
        except requests.exceptions.Timeout:
            return False, '大模型 API 连接超时，请检查网络或「AI 配置」中的 API 地址'
        except requests.exceptions.ConnectionError:
            return False, '无法连接到大模型 API，请检查网络或「AI 配置」中的 API 地址'
        except Exception as e:
            return False, f'大模型 API 连接异常：{str(e)[:60]}，请检查「AI 配置」后重试'

    def _validate_is_course(self, text, ai_config=None):
        """向 LLM 验证输入是否为有效课程名，返回 (is_valid, feedback_message)"""
        cfg = ai_config or {}
        use_real_llm = cfg.get('use_real_llm', Config.USE_REAL_LLM)
        if not use_real_llm:
            return True, ''

        messages = [
            {"role": "system", "content": "你是课程名称识别助手。只回答 JSON。"},
            {"role": "user", "content": (
                '判断以下用户输入是否在表达"学习某门课程"的意图。\n'
                '\n'
                f'用户输入："{text}"\n'
                '\n'
                '分析规则：\n'
                '1. 如果输入中包含大学/中学常见课程名（如高等数学、操作系统、Python、数据结构、计算机网络等），返回 true\n'
                '2. 如果输入是日常闲聊、无关话题，返回 false\n'
                '3. 如果输入模糊但看起来想学某个技能/知识，返回 true\n'
                '\n'
                '返回纯JSON：\n'
                '{"is_course": true/false, "reason": "简短说明，如果无效请给用户友好的提示"}'
            )}
        ]

        try:
            response = self._call_llm(messages, temperature=0, max_tokens=200, ai_config=ai_config)
            if not response:
                return True, ''  # LLM 不可用时放过

            import json as _json
            data = _json.loads(response.strip())
            is_valid = data.get('is_course', True)
            reason = data.get('reason', '')
            if is_valid:
                return True, ''
            else:
                return False, reason or '输入不像是课程名，请输入你想学习的课程，例如「两周内复习完高等数学」'
        except Exception:
            return True, ''  # 解析失败时放过，不阻塞用户

    def _parse_llm_task_plan(self, response):
        """解析 LLM 返回的任务规划 JSON"""
        try:
            text = response.strip()

            # 尝试提取 ```json ... ``` 代码块
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
            if json_match:
                text = json_match.group(1).strip()

            # 尝试找到 JSON 对象的起止位置
            if not text.startswith('{'):
                start = text.find('{')
                end = text.rfind('}')
                if start != -1 and end != -1:
                    text = text[start:end + 1]

            plan = json.loads(text)

            # 基本校验
            if 'phases' not in plan or not isinstance(plan['phases'], list):
                print("[LLM] Invalid plan format: missing phases")
                return None

            total_tasks = sum(len(p.get('daily_tasks', [])) for p in plan['phases'])
            if total_tasks == 0:
                print("[LLM] Empty task list")
                return None

            # 校验和修正 day 字段
            global_day = 1
            for phase in plan['phases']:
                for task in phase.get('daily_tasks', []):
                    if 'day' not in task or not isinstance(task['day'], int):
                        task['day'] = global_day
                    global_day = task['day'] + 1

            print(f"[LLM] Successfully generated plan: {len(plan['phases'])} phases, {total_tasks} daily tasks")
            return plan

        except json.JSONDecodeError as e:
            print(f"[LLM] JSON parse error: {e}")
            print(f"[LLM] Raw response (first 500 chars): {response[:500]}")
            return None
        except Exception as e:
            print(f"[LLM] Parse error: {e}")
            return None

    def _generate_multi_course_smart_subtasks(self, course_names, goal_type, total_days, daily_hours=2.0, ai_config=None, kb_context=None):
        """多课程智能编排 - LLM优先，Mock兜底，按日课表输出"""
        from datetime import datetime, timedelta

        llm_plan = self._llm_generate_multi_course_plan(course_names, goal_type, total_days, daily_hours, ai_config=ai_config, kb_context=kb_context)
        if llm_plan:
            subtasks = []
            current_date = datetime.now()
            order = 0

            # 阶段头 + 每日任务展开
            phases_map = {}

            for day_entry in llm_plan.get('daily_schedule', []):
                day_num = day_entry.get('day', 1)
                date = current_date + timedelta(days=day_num - 1)

                for slot in day_entry.get('time_slots', []):
                    order += 1
                    course_label = slot.get('course', '')
                    time_label = slot.get('time', '')
                    title = slot.get('title', '')
                    desc = slot.get('description', '')
                    hours = slot.get('suggested_hours', daily_hours)
                    phase = slot.get('phase_tag', '')

                    course_prefix = f'【{course_label}】' if course_label else ''

                    subtasks.append({
                        'title': f'第{day_num}天 | {course_prefix}{title} · ⏱{hours}h',
                        'description': f'{desc}\n建议时长：{hours}小时',
                        'due_date': date.strftime('%Y-%m-%d'),
                        'order': order,
                        'phase': phase or '综合复习',
                        'day': day_num,
                        'course': course_label,
                        'is_daily_task': True,
                        'estimated_hours': hours,
                    })

                    if phase and phase not in phases_map:
                        phases_map[phase] = {'min_day': day_num, 'max_day': day_num}
                    elif phase:
                        phases_map[phase]['min_day'] = min(phases_map[phase]['min_day'], day_num)
                        phases_map[phase]['max_day'] = max(phases_map[phase]['max_day'], day_num)

            # 将阶段头任务插入到 subtasks 开头
            phase_headers = []
            for phase_name, day_range in phases_map.items():
                phase_headers.append({
                    'title': f'📋 {phase_name}（第{day_range["min_day"]}-{day_range["max_day"]}天）',
                    'description': f'多课程并行学习阶段',
                    'due_date': (current_date + timedelta(days=day_range['max_day'] - 1)).strftime('%Y-%m-%d'),
                    'order': 0,
                    'phase': phase_name,
                    'is_phase_header': True,
                })

            # 合并：阶段头 + 按天排序的每日任务
            result = phase_headers + sorted(subtasks, key=lambda x: (x.get('day', 0), x.get('order', 0)))
            # 重新编排 order
            for i, t in enumerate(result):
                t['order'] = i + 1

            return result

        return self._mock_generate_multi_course_subtasks(course_names, goal_type, total_days, daily_hours)

    def _mock_generate_multi_course_subtasks(self, course_names, goal_type, total_days, daily_hours=2.0):
        """Mock 多课程编排：轮询分配每日时段"""
        from datetime import datetime, timedelta

        n_courses = len(course_names)
        subtasks = []
        current_date = datetime.now()
        order = 0

        hours_per_course = daily_hours / n_courses
        # 支持 >3 门课程：轮换使用 上午/下午/晚上
        all_time_slots = ['上午', '下午', '晚上']
        time_slots = [all_time_slots[i % 3] for i in range(n_courses)]
        if n_courses == 2:
            course_time_map = {
                course_names[0]: {'time': '上午', 'hours': daily_hours * 0.55},
                course_names[1]: {'time': '下午', 'hours': daily_hours * 0.45},
            }
        else:
            course_time_map = {}
            for i, cn in enumerate(course_names):
                course_time_map[cn] = {'time': time_slots[i], 'hours': hours_per_course}

        for day in range(1, total_days + 1):
            date = current_date + timedelta(days=day - 1)
            progress_ratio = day / max(total_days, 1)
            for ci, cn in enumerate(course_names):
                order += 1
                slot_info = course_time_map.get(cn, {'time': '', 'hours': daily_hours})
                knowledge = self._get_course_knowledge(cn)
                k_idx = (day - 1) % max(len(knowledge), 1)
                kp = knowledge[k_idx] if knowledge else f'{cn}学习'

                base_hours = slot_info['hours']
                variation = 0.5 + (progress_ratio * 0.6) + (ci % 3) * 0.1
                if k_idx % 4 == 0:
                    variation += 0.25
                elif k_idx % 7 == 0:
                    variation -= 0.2
                task_hours = max(0.3, min(daily_hours, round(base_hours * variation, 1)))

                subtasks.append({
                    'title': f'第{day}天 | 【{cn}】{kp} · ⏱{task_hours:.1f}h',
                    'description': f'{cn} {goal_type} - 第{day}天，建议时长 {task_hours:.1f} 小时',
                    'due_date': date.strftime('%Y-%m-%d'),
                    'order': order,
                    'phase': '多课程并行学习',
                    'day': day,
                    'course': cn,
                    'is_daily_task': True,
                    'estimated_hours': task_hours,
                })

        # 添加阶段头
        subtasks.insert(0, {
            'title': f'📋 多课程并行学习（第1-{total_days}天）',
            'description': f'{", ".join(course_names)} 同步推进，每日轮换时段',
            'due_date': (current_date + timedelta(days=total_days - 1)).strftime('%Y-%m-%d'),
            'order': 0,
            'phase': '多课程并行学习',
            'is_phase_header': True,
        })

        for i, t in enumerate(subtasks):
            t['order'] = i + 1
        return subtasks

    def _llm_generate_multi_course_plan(self, course_names, goal_type, total_days, daily_hours, ai_config=None, kb_context=None):
        """调用 LLM 生成多课程日课表，失败返回 None"""
        cfg = ai_config or {}
        use_real_llm = cfg.get('use_real_llm', Config.USE_REAL_LLM)
        if not use_real_llm:
            return None

        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')

        courses_text = ', '.join(course_names)

        # 知识库上下文
        kb_section = ''
        if kb_context:
            kb_parts = []
            for cn in course_names:
                ctx = kb_context.get(cn, '')
                if ctx:
                    kb_parts.append(f'【{cn}知识库】\n{ctx[:1500]}')
            if kb_parts:
                kb_section = '\n\n'.join(kb_parts)

        knowledge_summary = ''
        for cn in course_names:
            kp = self._get_course_knowledge(cn)
            knowledge_summary += f'\n{cn}知识点：' + '；'.join(kp[:8]) if kp else ''

        messages = [
            {'role': 'system', 'content': self._get_multi_course_planning_system_prompt()},
            {'role': 'user', 'content': f"""请制定多课程并行日课表：

课程：{courses_text}
目标：{goal_type}
天数：{total_days}天，每天约{daily_hours}小时
开始：{today}
现有资料：{knowledge_summary[:2000]}
{kb_section}

要求：
1. 每门课每天1-2个时段，每时段1-2小时，交错安排
2. title 带章节号（如"§2.1 导数概念"），description 步骤化+时间标注
3. 各时段 suggested_hours 之和≈{daily_hours}
4. suggested_hours 按难度设置：简单=0.5-1h，中等=1-2h，困难=2-3h
5. 阶段递进，最后2天综合冲刺
6. 输出纯JSON{'' if not kb_section else '。如知识库已提供，请严格基于知识库内容规划'}
"""},
        ]

        response = self._call_llm(messages, temperature=0.3, max_tokens=4096, ai_config=ai_config)
        if not response:
            return None

        return self._parse_llm_multi_course_plan(response)

    def _get_multi_course_planning_system_prompt(self):
        return """你是教务排课专家。为多门课程制定极度详细的并行日课表。

要求：
1. title 必须包含章节号+知识点名称（如"§2.1 导数概念与几何意义"）
2. description 必须步骤化：每步标注具体教材页数/课件讲次/习题题号+耗时分钟数
3. 每天不同课程交错排列，同一门课连续≤2个任务
4. 阶段递进：基础→强化→冲刺，最后2天综合+查漏补缺
5. suggested_hours 按任务难度逐天不同（0.5-3h），至少4种不同值，同一阶段内高低交错

输出纯JSON，不要任何额外文字：

```json
{
  "plan_summary": "一句话",
  "daily_schedule": [{
    "day": 1,
    "time_slots": [{
      "course": "高等数学",
      "phase_tag": "基础夯实",
      "title": "§2.1 导数的概念与几何意义",
      "description": "1.阅读教材P45-P52(30分钟)→2.做习题2.1第1-5题(40分钟)→3.整理导数公式笔记(20分钟)",
      "suggested_hours": 1.5
    }]
  }]
}
```"""

    def _parse_llm_multi_course_plan(self, response):
        """解析 LLM 返回的多课程日课表 JSON"""
        try:
            text = response.strip()
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
            if json_match:
                text = json_match.group(1).strip()
            if not text.startswith('{'):
                start = text.find('{')
                end = text.rfind('}')
                if start != -1 and end != -1:
                    text = text[start:end + 1]

            plan = json.loads(text)

            if 'daily_schedule' not in plan:
                print("[LLM] Multi-course: missing daily_schedule")
                return None

            total_slots = sum(len(d.get('time_slots', [])) for d in plan['daily_schedule'])
            if total_slots == 0:
                print("[LLM] Multi-course: empty schedule")
                return None

            print(f"[LLM] Multi-course plan: {len(plan['daily_schedule'])} days, {total_slots} time slots")
            return plan
        except json.JSONDecodeError as e:
            print(f"[LLM] Multi-course JSON parse error: {e}")
            return None
        except Exception as e:
            print(f"[LLM] Multi-course parse error: {e}")
            return None

    # ==================================================================
    # [已删除] 对话引擎相关方法（chat_rag 及其辅助方法）
    #
    # 删除原因: chat.html 的对话功能已迁移至 chat_engine.py，
    # 本文件中的 chat_rag() / _build_multimodal_user_message() /
    # _build_fallback_messages() / _attach_images_to_messages() /
    # _strip_images_from_messages() / _build_citation_markdown()
    # 已全部被 chat_engine.py 取代，属于死代码。
    #
    # ⚠ 合并分支注意：
    # 如果其他分支修改了本区域的方法，合并时直接采用 chat_engine.py
    # 的对应实现即可，不要复活本区域的代码。本区域的任何修改都应
    # 视为对历史代码的改动，合并到 chat_engine.py 对应位置。
    # ==================================================================


# 创建全局AI服务实例
ai_service = AIService()
