"""
教务课表 CSV 导入服务
解析北邮教务系统导出的个人课表 CSV 文件，提取课程信息
"""
import csv
import io
import re


def parse_schedule_csv(file_content):
    """
    解析教务系统课表 CSV，返回课程列表

    参数:
        file_content: CSV 文件内容（字符串）

    返回:
        {
            'semester': '2025-2026-2',
            'courses': [
                {
                    'name': '课程名',
                    'teacher': '教师',
                    'semester': '学期',
                    'description': '课表信息（时间+地点+周次）'
                },
                ...
            ],
            'errors': []
        }
    """
    result = {
        'semester': '',
        'courses': [],
        'errors': [],
        'period_time_map': {}  # 节次→时间映射 {1: "08:00-08:45", 2: "08:50-09:35", ...}
    }

    try:
        # 处理 UTF-8 BOM
        if file_content.startswith('﻿'):
            file_content = file_content[1:]

        reader = csv.reader(io.StringIO(file_content))
        rows = list(reader)
    except Exception as e:
        result['errors'].append(f'CSV 解析失败: {str(e)}')
        return result

    if len(rows) < 4:
        result['errors'].append('文件内容过少，不是有效的课表文件')
        return result

    # --- 第1行：标题行，提取姓名（可选） ---
    # 格式: "北京邮电大学 林恩煌 学生个人课表"

    # --- 第2行：元信息，提取学期 ---
    meta_row = rows[1][0] if rows[1] else ''
    semester_match = re.search(r'学年学期[：:]\s*(\S+)', meta_row)
    if semester_match:
        result['semester'] = semester_match.group(1)
    else:
        result['errors'].append('未能识别学年学期信息，将使用默认值')

    # --- 第3行：列头，识别星期列位置 ---
    header_row = rows[2]
    day_columns = {}  # {列索引: 星期名}
    for i, cell in enumerate(header_row):
        cell = cell.strip()
        if cell in ('星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日'):
            day_columns[i] = cell

    if not day_columns:
        result['errors'].append('未能识别课表列头（星期一~星期日）')
        return result

    # --- 第4行起：课程数据行 ---
    # 用 dict 按课程名聚合：{课程名: {teacher, schedules: [{day, period, location, weeks}]}}
    courses_map = {}
    period_time_map = {}  # 全局节次-时间映射：{period_num: "HH:MM-HH:MM"}

    for row in rows[3:]:
        if not row or len(row) < 2:
            continue

        # 解析第1列：节次时间，格式如 "1\n08:00-08:45"
        time_cell = row[0].strip() if row[0] else ''
        # 提取节次编号（用于辅助判断是否为有效数据行）
        slot_match = re.match(r'(\d+)\s*\n', time_cell)
        if not slot_match:
            # 非课程数据行（如备注行），跳过
            continue

        period_num = int(slot_match.group(1))

        # 提取时间范围（如 "08:00-08:45"）
        time_match = re.search(r'(\d{1,2}:\d{2}-\d{1,2}:\d{2})', time_cell)
        time_range = time_match.group(1) if time_match else ''

        # 记录该节次的时间
        if period_num and time_range:
            period_time_map[period_num] = time_range

        # 遍历每个星期列
        for col_idx, day_name in day_columns.items():
            if col_idx >= len(row):
                continue

            cell_content = row[col_idx].strip()
            if not cell_content:
                continue

            # 拆分单元格内的多门课程
            # 每门课占5行：课程名、教师、周次、地点、节次
            lines = [l.strip() for l in cell_content.split('\n') if l.strip()]

            # 按5行一组拆分
            i = 0
            while i + 4 < len(lines):
                course_name = lines[i]
                teacher = lines[i + 1]
                weeks = lines[i + 2]
                location = lines[i + 3]
                period = lines[i + 4]

                # 基本校验：课程名不能太短，不能是备注
                if len(course_name) < 2 or course_name.startswith('备注'):
                    i += 5
                    continue

                # 校验周次格式（包含 [周]）
                if '[周]' not in weeks:
                    i += 5
                    continue

                # 聚合到 courses_map（按 day+period+location+weeks 去重）
                if course_name not in courses_map:
                    courses_map[course_name] = {
                        'name': course_name,
                        'teacher': teacher,
                        'schedules': [],
                        '_seen': set()
                    }

                schedule_key = (day_name, period, location, weeks)
                if schedule_key not in courses_map[course_name]['_seen']:
                    courses_map[course_name]['_seen'].add(schedule_key)
                    courses_map[course_name]['schedules'].append({
                        'day': day_name,
                        'period': period,
                        'location': location,
                        'weeks': weeks,
                        'time': time_range
                    })

                i += 5

    # --- 生成课程列表 ---
    semester = result['semester'] or '未识别学期'

    for name, info in courses_map.items():
        # 生成 description：课表时间地点信息（包含节次和时间）
        desc_lines = ['📅 上课时间：']
        for s in info['schedules']:
            time_str = f'({s["time"]})' if s.get('time') else ''
            desc_lines.append(f'  {s["day"]} {s["period"]}{time_str} | {s["location"]} | {s["weeks"]}')
        course_data = {
            'name': name,
            'teacher': info['teacher'],
            'semester': semester,
            'description': '\n'.join(desc_lines)
        }
        result['courses'].append(course_data)

    if not result['courses'] and not result['errors']:
        result['errors'].append('未在课表中找到有效课程信息')

    # 添加节次时间映射
    result['period_time_map'] = period_time_map

    return result
