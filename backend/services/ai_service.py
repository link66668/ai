import json
import re
import requests
import base64
from config import Config
from models.document import Document
from models.course import Course

class AIService:
    """模拟AI服务 - 课程学习助手"""

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

    def decompose_task(self, task_title, description='', total_days=7, ai_config=None):
        """任务分解 - 增强版：支持自然语言智能拆解，含多课程编排"""
        from datetime import datetime, timedelta

        full_text = f"{task_title} {description}".strip()
        parsed = self._parse_nl_task(full_text)

        if parsed and parsed.get('total_days'):
            total_days = parsed['total_days']

        # 多课程编排：按日课表生成
        if parsed and parsed.get('is_multi_course') and total_days >= 3:
            return self._generate_multi_course_smart_subtasks(
                parsed['course_names'],
                parsed.get('goal_type', '复习'),
                total_days,
                parsed.get('daily_hours', 2.0),
                ai_config=ai_config,
            )

        # 单课程智能拆解
        if parsed and parsed.get('course_names') and total_days >= 3:
            return self._generate_smart_subtasks(
                parsed['course_names'][0],
                parsed.get('goal_type', '复习'),
                total_days,
                parsed.get('daily_hours', 2.0),
                ai_config=ai_config,
            )

        subtasks = []
        current_date = datetime.now()

        if '复习' in task_title or '考试' in task_title:
            task_templates = [
                '整理课程笔记和知识点',
                '回顾重点概念和公式',
                '完成课后习题',
                '做历年真题',
                '查漏补缺，强化薄弱环节'
            ]
        elif '实验' in task_title or '作业' in task_title:
            task_templates = [
                '分析任务要求和目标',
                '查阅相关资料',
                '制定实施方案',
                '执行具体操作',
                '总结并撰写报告'
            ]
        else:
            task_templates = [
                '明确任务目标',
                '收集所需资料',
                '制定详细计划',
                '执行任务内容',
                '检查和完善成果'
            ]

        days_per_task = max(1, total_days // len(task_templates))

        for i, template in enumerate(task_templates):
            due_date = current_date + timedelta(days=days_per_task * (i + 1))
            subtasks.append({
                'title': template,
                'due_date': due_date.strftime('%Y-%m-%d'),
                'order': i + 1
            })

        return subtasks

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
        duration_patterns = [
            (r'(\d+)\s*周', lambda x: int(x) * 7),
            (r'(\d+)\s*天', lambda x: int(x)),
            (r'两\s*周', lambda x: 14),
            (r'一\s*周', lambda x: 7),
            (r'三\s*周', lambda x: 21),
            (r'半\s*个?\s*月', lambda x: 15),
            (r'一\s*个?\s*月', lambda x: 30),
        ]
        for pattern, converter in duration_patterns:
            match = re.search(pattern, text)
            if match:
                result['total_days'] = converter(match.group(1)) if match.lastindex else converter(None)
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
        else:
            result['goal_type'] = '学习'

        # 3. 提取课程名称（支持多课程）
        course_keywords = [
            '高等数学', '线性代数', '概率论', '大学英语', '英语',
            'Python', 'C语言', 'Java', '数据结构', '算法',
            '计算机网络', '操作系统', '数据库', '机器学习', '深度学习',
            '大学物理', '电路分析', '信号与系统',
            '微观经济学', '宏观经济学', '管理学',
            '马克思主义', '毛概', '思修', '近代史',
        ]

        known_courses = self._get_known_course_names()

        found_courses = []
        remaining_text = text

        # 先匹配已知课程（精确匹配，避免"英语"匹配到"大学英语"的重复）
        sorted_known = sorted(known_courses, key=len, reverse=True)
        for cname in sorted_known:
            if cname in remaining_text:
                found_courses.append(cname)
                remaining_text = remaining_text.replace(cname, '', 1)

        # 再从关键词库中匹配剩余
        if not found_courses:
            for kw in sorted(course_keywords, key=len, reverse=True):
                if kw in remaining_text:
                    found_courses.append(kw)
                    remaining_text = remaining_text.replace(kw, '', 1)

        # 如果有"和"、"、"、"与"等连接词但只找到1个课程，尝试在全文再搜一个
        if len(found_courses) == 1 and re.search(r'[和、与,，]', text):
            for kw in sorted(course_keywords, key=len, reverse=True):
                if kw in remaining_text and kw != found_courses[0]:
                    found_courses.append(kw)
                    break

        # 去重
        seen = set()
        found_courses = [c for c in found_courses if not (c in seen or seen.add(c))]

        if found_courses:
            result['course_names'] = found_courses
            result['is_multi_course'] = len(found_courses) > 1
        else:
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

    def _generate_smart_subtasks(self, course_name, goal_type, total_days, daily_hours=2.0, ai_config=None):
        """生成智能阶段+每日任务拆解 - LLM优先，Mock兜底"""
        from datetime import datetime, timedelta

        llm_plan = self._llm_generate_task_plan(course_name, goal_type, total_days, daily_hours, ai_config=ai_config)
        if llm_plan:
            subtasks = []
            current_date = datetime.now()
            order = 0

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
                    task_hours = dt.get('suggested_hours', daily_hours)

                    subtasks.append({
                        'title': f'第{day_num}天：{task_title}',
                        'description': f'{task_desc}\n建议学习时长：{task_hours}小时',
                        'due_date': date.strftime('%Y-%m-%d'),
                        'order': order,
                        'phase': phase_name,
                        'day': day_num,
                        'is_daily_task': True,
                    })

            return subtasks

        return self._mock_generate_subtasks(course_name, goal_type, total_days, daily_hours)

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
        for phase in phases:
            knowledge_index = 0
            for day_in_phase in range(phase['end'] - phase['start'] + 1):
                order += 1
                date = current_date + timedelta(days=day - 1)

                # 根据阶段和日期生成具体的每日任务
                task_title = self._generate_daily_task_title(
                    course_name, goal_type, phase['name'], day_in_phase + 1,
                    knowledge, knowledge_index
                )

                day_task = {
                    'title': f'第{day}天：{task_title}',
                    'description': f'{course_name} {goal_type} - {phase["name"]} 第{day_in_phase + 1}天，建议学习时长 {daily_hours} 小时',
                    'due_date': date.strftime('%Y-%m-%d'),
                    'order': order,
                    'phase': phase['name'],
                    'day': day,
                    'is_daily_task': True,
                }
                subtasks.append(day_task)

                knowledge_index = (knowledge_index + 1) % max(len(knowledge), 1)
                day += 1

        return subtasks

    def _get_course_knowledge(self, course_name):
        """从已上传的资料中获取课程知识点"""
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
                knowledge_points = self._get_default_knowledge(course_name)
        except Exception:
            knowledge_points = self._get_default_knowledge(course_name)

        return knowledge_points or [f'{course_name}核心知识点学习']

    def _get_default_knowledge(self, course_name):
        """根据课程名返回默认知识点"""
        defaults = {
            '高等数学': [
                '函数的概念与性质', '极限的定义与计算', '极限运算法则',
                '导数的概念与几何意义', '求导法则', '函数的单调性与极值',
                '不定积分', '定积分的定义与性质', '定积分的应用',
                '微分方程基础', '线性代数矩阵运算', '向量空间与线性变换',
            ],
            '线性代数': [
                '矩阵的定义与基本运算', '行列式的计算', '矩阵的逆',
                '向量组的线性相关性', '线性方程组的解法', '特征值与特征向量',
                '二次型', '线性空间与线性变换',
            ],
            'Python': [
                '变量与数据类型', '条件判断与循环', '函数定义与调用',
                '列表与字典操作', '文件读写', '面向对象编程基础',
                '异常处理机制', '模块与包管理',
            ],
            '大学英语': [
                '词汇积累与记忆', '阅读理解的技巧', '听力训练',
                '写作模板与范文', '语法重点复习', '翻译常见句式',
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
        """根据阶段和知识点生成每日任务标题"""
        import re

        if '基础' in phase_name or '学习' in phase_name:
            if day_in_phase == 1:
                return f'{course_name}课程大纲梳理与目标设定'
            elif knowledge and knowledge_index < len(knowledge):
                return f'学习并掌握：{knowledge[knowledge_index]}'
            else:
                return f'{course_name}基础知识学习'

        elif '强化' in phase_name or '提升' in phase_name:
            tasks = [
                f'{course_name}重点题型专项练习',
                f'{course_name}知识点串联与体系构建',
                f'{course_name}易错题整理与分析',
                f'{course_name}综合解题能力训练',
                f'{course_name}高频考点专项突破',
            ]
            return tasks[day_in_phase % len(tasks)]

        elif '冲刺' in phase_name:
            if day_in_phase == 1:
                return f'{course_name}历年真题模拟测试'
            elif day_in_phase <= 2:
                return f'{course_name}真题错题分析与订正'
            else:
                return f'{course_name}高频考点回顾与巩固'

        elif '查漏' in phase_name:
            tasks = [
                f'{course_name}薄弱知识点专项复习',
                f'{course_name}全真模拟考试练习',
                f'{course_name}易错知识点回顾',
                f'{course_name}考前心态调整与重点回顾',
            ]
            return tasks[day_in_phase % len(tasks)]

        elif '复习' in phase_name or '巩固' in phase_name:
            tasks = [
                f'{course_name}知识体系回顾总结',
                f'{course_name}错题重新练习',
                f'{course_name}核心概念与公式速记',
            ]
            return tasks[day_in_phase % len(tasks)]

        else:
            return f'{course_name}学习任务（第{day_in_phase}天）'

    def _llm_generate_task_plan(self, course_name, goal_type, total_days, daily_hours, ai_config=None):
        """调用大模型生成详细任务规划，失败返回 None"""
        cfg = ai_config or {}
        use_real_llm = cfg.get('use_real_llm', Config.USE_REAL_LLM)
        if not use_real_llm:
            return None

        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')

        knowledge = self._get_course_knowledge(course_name)
        knowledge_text = '\n'.join([f'- {k}' for k in knowledge[:15]]) if knowledge else '无现有资料'

        messages = [
            {
                'role': 'system',
                'content': self._get_task_planning_system_prompt()
            },
            {
                'role': 'user',
                'content': f"""请为以下学习目标制定详细的任务规划：

课程名称：{course_name}
目标类型：{goal_type}
总天数：{total_days} 天
每日学习时长：{daily_hours} 小时
开始日期：{today}
已有知识点资料：
{knowledge_text}

要求：
1. 根据总天数合理划分阶段（2-4个阶段）
2. 每个阶段生成每日具体任务，每天1-2个任务
3. 每个任务标题要具体可执行，描述要详细（包含具体行动指南）
4. 阶段安排要有渐进性，从基础到提升到冲刺
5. 最后一天安排"考前心态调整与最终回顾"

请严格按照JSON格式输出。"""
            }
        ]

        response = self._call_llm(messages, temperature=0.5, max_tokens=4096, ai_config=ai_config)
        if not response:
            return None

        return self._parse_llm_task_plan(response)

    def _get_task_planning_system_prompt(self):
        return """你是一个专业的学习规划师和教育专家。你的任务是为学生制定详细、可执行的学习任务计划。

制定计划时遵循以下原则：
1. **阶段性**：将学习周期划分为2-4个阶段（基础→强化→冲刺→查缺补漏）
2. **可执行性**：每个任务都要具体明确，学生看到就知道该做什么
3. **渐进性**：任务难度从基础概念逐步过渡到综合应用
4. **劳逸结合**：适当安排复习日和休息调整
5. **针对性**：针对考试类型（期末/期中/考研等）调整策略

输出严格的JSON格式，不要包含任何多余文字：

```json
{
  "plan_summary": "一句话概括整个计划",
  "phases": [
    {
      "phase_name": "阶段名称（如：基础夯实阶段）",
      "start_day": 1,
      "end_day": 7,
      "focus": "该阶段的重点目标和策略（一句话）",
      "daily_tasks": [
        {
          "day": 1,
          "title": "具体任务标题（简短有力，5-15字）",
          "description": "详细任务说明，包含具体要做什么、怎么做、注意事项（30-80字）",
          "suggested_hours": 2.0
        }
      ]
    }
  ]
}
```

注意：
- daily_tasks 数组必须覆盖从 start_day 到 end_day 的每一天
- 每个任务标题必须具体（如"极限定义的理解与ε-δ语言练习"而非"学习极限"）
- description 要给出操作指南（如"先阅读教材第二章，重点理解ε-δ定义，然后完成课后习题2.1-2.3"）
- suggested_hours 是建议学习时长，可为浮点数"""

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

    def _generate_multi_course_smart_subtasks(self, course_names, goal_type, total_days, daily_hours=2.0, ai_config=None):
        """多课程智能编排 - LLM优先，Mock兜底，按日课表输出"""
        from datetime import datetime, timedelta

        llm_plan = self._llm_generate_multi_course_plan(course_names, goal_type, total_days, daily_hours, ai_config=ai_config)
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
                    time_prefix = f'{time_label} | ' if time_label else ''

                    subtasks.append({
                        'title': f'第{day_num}天 {time_prefix}{course_prefix}{title}',
                        'description': f'{desc}\n建议时长：{hours}小时',
                        'due_date': date.strftime('%Y-%m-%d'),
                        'order': order,
                        'phase': phase or '综合复习',
                        'day': day_num,
                        'course': course_label,
                        'time_slot': time_label,
                        'is_daily_task': True,
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
        time_slots = ['上午', '下午', '晚上'][:n_courses]
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
            for cn in course_names:
                order += 1
                slot_info = course_time_map.get(cn, {'time': '', 'hours': daily_hours})
                knowledge = self._get_course_knowledge(cn)
                k_idx = (day - 1) % max(len(knowledge), 1)
                kp = knowledge[k_idx] if knowledge else f'{cn}学习'

                subtasks.append({
                    'title': f'第{day}天 {slot_info["time"]} | 【{cn}】{kp}',
                    'description': f'{cn} {goal_type} - 第{day}天，建议时长 {slot_info["hours"]:.1f} 小时',
                    'due_date': date.strftime('%Y-%m-%d'),
                    'order': order,
                    'phase': '多课程并行学习',
                    'day': day,
                    'course': cn,
                    'time_slot': slot_info['time'],
                    'is_daily_task': True,
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

    def _llm_generate_multi_course_plan(self, course_names, goal_type, total_days, daily_hours, ai_config=None):
        """调用 LLM 生成多课程日课表，失败返回 None"""
        cfg = ai_config or {}
        use_real_llm = cfg.get('use_real_llm', Config.USE_REAL_LLM)
        if not use_real_llm:
            return None

        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')

        courses_text = ', '.join(course_names)
        knowledge_summary = ''
        for cn in course_names:
            kp = self._get_course_knowledge(cn)
            knowledge_summary += f'\n{cn}知识点：' + '；'.join(kp[:8]) if kp else ''

        messages = [
            {'role': 'system', 'content': self._get_multi_course_planning_system_prompt()},
            {'role': 'user', 'content': f"""请为以下多课程学习目标制定详细的每日课表：

课程列表：{courses_text}
目标类型：{goal_type}
总天数：{total_days} 天
每日总学习时长：{daily_hours} 小时
开始日期：{today}
现有知识点：
{knowledge_summary[:2000]}

要求：
1. 每天安排 {daily_hours} 小时的学习，把总时长按1-2小时为单位切分为具体时段
2. 时段数量不固定：{daily_hours}小时可切为 {"1-2" if daily_hours <= 3 else "2-3" if daily_hours <= 6 else "3-4"} 个时段，每个时段标注精确起止时间
3. 不同课程的时段交错安排，避免同一门课连续超过2小时
4. 每项任务的 suggested_hours 要在0.5-2.5之间，各时段 suggested_hours 之和约等于 {daily_hours}
5. 每{max(3, total_days//4)}天安排一次综合回顾，重点复习薄弱环节
6. 最后2天作为综合模拟+查漏补缺

请严格按照JSON格式输出。"""},
        ]

        response = self._call_llm(messages, temperature=0.4, max_tokens=8192, ai_config=ai_config)
        if not response:
            return None

        return self._parse_llm_multi_course_plan(response)

    def _get_multi_course_planning_system_prompt(self):
        return """你是一个专业的教务排课专家和学习规划师。你的任务是为多门课程制定详细的每日学习课表。

核心原则：
1. **按小时灵活划分时段**：根据每天的总学习时长，将其切分为1-2小时为单位的时段，每个时段标注精确起止时间（如"8:00-9:30"、"14:00-16:00"）
2. **课程轮换**：不同课程交错安排，同一门课不宜连续超过2小时
3. **难度穿插**：将难度高的课程安排在精力充沛的时间段，相对轻松的安排在后续时段
4. **定期回顾**：每天最后安排15-30分钟回顾整理，每周安排综合回顾日
5. **阶段递进**：前期打基础，中期强化练习，后期模拟冲刺

每天时段数 = ceil(总小时数 / 1.5)，例如：
- 2小时/天 → 1-2个时段（如"8:00-9:30" + "9:30-10:00"回顾）
- 4小时/天 → 2-3个时段（如"8:00-9:30" + "10:00-11:30" + "14:00-15:00"）
- 6小时/天 → 3-4个时段
- 8小时/天 → 4-5个时段

输出严格的JSON格式，不要包含任何多余文字：

```json
{
  "plan_summary": "多课程并行学习计划总览",
  "daily_schedule": [
    {
      "day": 1,
      "time_slots": [
        {
          "time": "8:00-9:30",
          "course": "高等数学",
          "phase_tag": "基础夯实",
          "title": "极限定义与运算法则复习",
          "description": "先花30分钟回顾极限的ε-δ定义和运算法则，然后完成课后习题2.1-2.5，重点理解极限存在的充要条件",
          "suggested_hours": 1.5
        },
        {
          "time": "10:00-11:00",
          "course": "大学英语",
          "phase_tag": "基础夯实",
          "title": "词汇Unit1-3复习",
          "description": "先花20分钟快速过Unit1-3单词表，标记生词；然后用40分钟完成2篇阅读理解真题",
          "suggested_hours": 1.0
        },
        {
          "time": "21:00-21:30",
          "course": "综合",
          "phase_tag": "日常回顾",
          "title": "当日错题整理与知识点回顾",
          "description": "整理今天所有课程中的错题和难点，在错题本上记录错误原因和正确解法",
          "suggested_hours": 0.5
        }
      ]
    }
  ]
}
```

注意：
- daily_schedule 必须覆盖每一天（day 从 1 到 总天数）
- 每天所有 time_slots 的 suggested_hours 之和应等于每日总学习时长
- 每个 time_slot 必须包含 course（课程名）、title（具体任务）、description（详细操作指南）
- phase_tag 用于标记阶段：基础夯实、强化提升、冲刺模拟、综合回顾、查缺补漏
- time 字段只需写时间如"8:00-10:00"，不需要加"上午/下午/晚上"前缀"""

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
