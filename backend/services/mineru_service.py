"""
MinerU 文档转 Markdown 服务

支持两种后端：
- REST API 模式：调用自建 MinerU API 服务（doc_api_url 有值时）
- Cloud SDK 模式：调用 MinerU 云端 API（仅 doc_api_key 有值时）

转换结果保存为 .md 文件 + images/ 子目录
"""
import os
import re
import io
import zipfile
import logging
import time

logger = logging.getLogger(__name__)


class MinerUService:
    """MinerU 文档转 Markdown 服务"""

    # 支持转换的文件类型
    SUPPORTED_TYPES = {'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'png', 'jpg', 'jpeg'}

    # REST API 轮询超时（秒）
    POLL_TIMEOUT = 600  # 10 分钟
    POLL_INTERVAL = 3   # 3 秒

    def is_available(self, ai_config):
        """检查 MinerU 是否可用（doc_api_url 或 doc_api_key 非空）"""
        if not ai_config:
            return False
        doc_url = (ai_config.get('doc_api_url') or '').strip()
        doc_key = (ai_config.get('doc_api_key') or '').strip()
        return bool(doc_url or doc_key)

    def convert(self, file_path, file_type, ai_config, output_dir, doc_name=None):
        """
        将文档转换为 Markdown

        Args:
            file_path: 原始文件路径
            file_type: 文件类型（扩展名）
            ai_config: 用户 AI 配置（含 doc_api_url, doc_api_key, doc_model）
            output_dir: .md 输出目录（如 backend/uploads/课程名/）
            doc_name: 文档名（不含扩展名），用于生成 .md 文件名

        Returns:
            {
                'markdown_text': str,
                'md_file_path': str,
                'image_count': int,
                'image_dir': str,
                'metadata': {'page_count': int}
            }

        Raises:
            Exception: 转换失败时抛出，调用方捕获后降级到本地解析器
        """
        if not self.is_available(ai_config):
            raise ValueError('MinerU 未配置')

        if file_type.lower() not in self.SUPPORTED_TYPES:
            raise ValueError(f'不支持的文件类型: {file_type}')

        if not os.path.exists(file_path):
            raise FileNotFoundError(f'文件不存在: {file_path}')

        doc_url = (ai_config.get('doc_api_url') or '').strip()
        doc_key = (ai_config.get('doc_api_key') or '').strip()
        doc_model = (ai_config.get('doc_model') or 'vlm').strip()

        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)

        # 选择后端
        # 官方地址(https://mineru.net / https://mineru.com.cn) 不走 REST，
        # 它们不是 API 端点，需要走 SDK 模式
        OFFICIAL_SITES = {'https://mineru.net', 'https://mineru.com.cn'}
        base_clean = doc_url.rstrip('/')
        is_official_site = base_clean in OFFICIAL_SITES

        if doc_url and not is_official_site and doc_key:
            # 自定义自建服务 → REST 模式
            result = self._convert_via_rest(file_path, doc_url, doc_key, output_dir, doc_name)
        elif doc_key:
            # 有 API Key → SDK 模式（官方推荐）
            result = self._convert_via_sdk(file_path, doc_key, doc_model, output_dir, doc_name)
        elif doc_url and not is_official_site:
            # 仅有自定义 URL（无 Key）→ 尝试 REST
            result = self._convert_via_rest(file_path, doc_url, doc_key, output_dir, doc_name)
        else:
            raise ValueError('请配置 MinerU API Key（SDK 模式）或自建服务地址（REST 模式）')

        return result

    def _convert_via_rest(self, file_path, api_url, api_key, output_dir, doc_name=None):
        """通过 REST API 调用 MinerU"""
        import requests

        base_url = api_url.rstrip('/')
        headers = {}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'

        # 上传文件并解析
        logger.info(f"[MinerU] REST 模式: 上传 {os.path.basename(file_path)} 到 {base_url}")

        with open(file_path, 'rb') as f:
            files = {'files': (os.path.basename(file_path), f)}
            data = {
                'return_md': 'true',
                'response_format_zip': 'true',
            }
            try:
                resp = requests.post(
                    f'{base_url}/file_parse',
                    files=files,
                    data=data,
                    headers=headers,
                    timeout=300,
                )
            except requests.exceptions.Timeout:
                raise TimeoutError('MinerU REST API 请求超时（5分钟）')
            except requests.exceptions.ConnectionError:
                raise ConnectionError(f'无法连接 MinerU 服务: {base_url}')

        if resp.status_code == 200:
            # 直接返回结果（同步模式）
            content_type = resp.headers.get('content-type', '')
            if 'zip' in content_type or 'octet-stream' in content_type:
                return self._extract_zip_result(resp.content, output_dir, doc_name)
            elif 'json' in content_type:
                # JSON 响应，可能包含 task_id（异步模式）
                result_json = resp.json()
                if 'task_id' in result_json:
                    return self._poll_task_result(base_url, api_key, result_json['task_id'], output_dir, doc_name)
                elif 'markdown' in result_json:
                    return self._save_markdown_result(result_json['markdown'], output_dir, doc_name)
                else:
                    raise ValueError(f'未知的 API 响应格式: {list(result_json.keys())}')
            else:
                # 尝试当作纯文本 markdown
                text = resp.text
                if text and len(text) > 100:
                    return self._save_markdown_result(text, output_dir, doc_name)
                raise ValueError(f'API 返回非预期内容类型: {content_type}')

        elif resp.status_code == 202:
            # 异步任务已接受
            result_json = resp.json()
            task_id = result_json.get('task_id') or result_json.get('id')
            if not task_id:
                raise ValueError('异步响应缺少 task_id')
            return self._poll_task_result(base_url, api_key, task_id, output_dir, doc_name)
        else:
            raise RuntimeError(f'MinerU API 错误: HTTP {resp.status_code} - {resp.text[:200]}')

    def _poll_task_result(self, base_url, api_key, task_id, output_dir, doc_name):
        """轮询异步任务结果"""
        import requests

        headers = {}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'

        logger.info(f"[MinerU] 轮询任务: {task_id}")
        start_time = time.time()

        while time.time() - start_time < self.POLL_TIMEOUT:
            try:
                resp = requests.get(
                    f'{base_url}/api/v4/extract/task/{task_id}',
                    headers=headers,
                    timeout=30,
                )
            except requests.exceptions.RequestException as e:
                logger.warning(f"[MinerU] 轮询请求失败: {e}")
                time.sleep(self.POLL_INTERVAL)
                continue

            if resp.status_code == 200:
                result = resp.json()
                status = result.get('status', '')
                if status in ('completed', 'success', 'done'):
                    # 获取结果
                    md_content = result.get('markdown', '') or result.get('md_content', '')
                    if md_content:
                        return self._save_markdown_result(md_content, output_dir, doc_name)
                    # 如果有结果下载链接
                    result_url = result.get('result_url') or result.get('download_url')
                    if result_url:
                        dl_resp = requests.get(result_url, timeout=120)
                        if dl_resp.status_code == 200:
                            return self._extract_zip_result(dl_resp.content, output_dir, doc_name)
                    raise ValueError('任务完成但无法获取 Markdown 内容')
                elif status in ('failed', 'error'):
                    raise RuntimeError(f'MinerU 任务失败: {result.get("error", "unknown")}')
                # 仍在处理中
            elif resp.status_code == 404:
                # 尝试其他端点格式
                try:
                    resp2 = requests.get(
                        f'{base_url}/tasks/{task_id}',
                        headers=headers,
                        timeout=30,
                    )
                    if resp2.status_code == 200:
                        result = resp2.json()
                        if result.get('status') in ('completed', 'success', 'done'):
                            md_content = result.get('markdown', '') or result.get('md_content', '')
                            if md_content:
                                return self._save_markdown_result(md_content, output_dir, doc_name)
                except Exception:
                    pass

            time.sleep(self.POLL_INTERVAL)

        raise TimeoutError(f'MinerU 任务超时（{self.POLL_TIMEOUT}秒）: {task_id}')

    def _convert_via_sdk(self, file_path, api_key, model, output_dir, doc_name=None):
        """通过 MinerU Cloud SDK 调用"""
        try:
            from mineru import MinerU as MinerUClient
        except ImportError:
            raise ImportError(
                'MinerU Cloud SDK 未安装。请运行: pip install mineru-open-sdk\n'
                '或者配置 doc_api_url 使用 REST API 模式'
            )

        logger.info(f"[MinerU] SDK 模式: 转换 {os.path.basename(file_path)}, model={model}")

        client = MinerUClient(api_key) if api_key else MinerUClient()

        # 根据模型选择调用不同方法
        if model == 'pipeline':
            # pipeline 模式使用 flash_extract（无需 API key 也可用）
            result = client.flash_extract(file_path)
        else:
            # vlm 或 MinerU-HTML 使用 precision extract
            extract_model = 'html' if model == 'MinerU-HTML' else model
            result = client.extract(
                file_path,
                model=extract_model,
                ocr=True,
                formula=True,
                table=True,
                timeout=self.POLL_TIMEOUT,
            )

        markdown_text = result.markdown if hasattr(result, 'markdown') else str(result)

        # 保存图片和 markdown
        if hasattr(result, 'save_all'):
            result.save_all(output_dir)

        return self._save_markdown_result(markdown_text, output_dir, doc_name)

    def _save_markdown_result(self, markdown_text, output_dir, doc_name=None):
        """保存 Markdown 文本到文件"""
        if not markdown_text or not markdown_text.strip():
            raise ValueError('MinerU 返回空 Markdown')

        # 生成文件名
        safe_name = self._safe_filename(doc_name or 'document')
        md_path = os.path.join(output_dir, f'{safe_name}.md')

        # 处理重名
        if os.path.exists(md_path):
            md_path = os.path.join(output_dir, f'{safe_name}_{int(time.time())}.md')

        # 如果模型返回 HTML（MinerU-HTML），转为 Markdown
        if self._looks_like_html(markdown_text):
            markdown_text = self._html_to_markdown(markdown_text)

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(markdown_text)

        # 统计图片引用
        image_count = len(re.findall(r'!\[.*?\]\(.*?\)', markdown_text))

        logger.info(f"[MinerU] 已保存: {md_path} ({len(markdown_text)} 字符, {image_count} 张图片引用)")

        return {
            'markdown_text': markdown_text,
            'md_file_path': md_path,
            'image_count': image_count,
            'image_dir': os.path.join(output_dir, 'images'),
            'metadata': {
                'page_count': markdown_text.count('\n---\n') + 1 or 1,
            },
        }

    def _extract_zip_result(self, zip_bytes, output_dir, doc_name=None):
        """解压 MinerU 返回的 ZIP 结果"""
        safe_name = self._safe_filename(doc_name or 'document')
        images_dir = os.path.join(output_dir, 'images')
        os.makedirs(images_dir, exist_ok=True)

        markdown_text = ''
        image_count = 0

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for info in zf.infolist():
                if info.filename.endswith('.md'):
                    # 读取 Markdown 文件
                    with zf.open(info) as f:
                        markdown_text = f.read().decode('utf-8', errors='replace')
                elif any(info.filename.lower().endswith(ext) for ext in
                         ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp')):
                    # 提取图片到 images/ 目录
                    img_name = os.path.basename(info.filename)
                    img_path = os.path.join(images_dir, img_name)
                    with zf.open(info) as f:
                        with open(img_path, 'wb') as out:
                            out.write(f.read())
                    image_count += 1

        if not markdown_text:
            raise ValueError('ZIP 中未找到 .md 文件')

        # 修复图片路径为相对路径
        markdown_text = self._fix_image_paths(markdown_text, images_dir)

        # 保存 Markdown 文件
        md_path = os.path.join(output_dir, f'{safe_name}.md')
        if os.path.exists(md_path):
            md_path = os.path.join(output_dir, f'{safe_name}_{int(time.time())}.md')

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(markdown_text)

        logger.info(f"[MinerU] ZIP 解压完成: {md_path} ({len(markdown_text)} 字符, {image_count} 张图片)")

        return {
            'markdown_text': markdown_text,
            'md_file_path': md_path,
            'image_count': image_count,
            'image_dir': images_dir,
            'metadata': {
                'page_count': markdown_text.count('\n---\n') + 1 or 1,
            },
        }

    def _fix_image_paths(self, markdown_text, images_dir):
        """修复 Markdown 中的图片路径为相对路径"""
        def replace_path(match):
            alt = match.group(1)
            old_path = match.group(2)
            filename = os.path.basename(old_path)
            return f'![{alt}](images/{filename})'

        return re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', replace_path, markdown_text)

    def _safe_filename(self, name):
        """将文件名转为安全字符（去除 Windows 非法字符）"""
        # 去除扩展名
        if '.' in name:
            name = name.rsplit('.', 1)[0]
        # 替换非法字符
        safe = re.sub(r'[\\/:*?"<>|]', '_', name).strip()
        # 去除首尾空格和点
        safe = safe.strip('. ')
        return safe if safe else 'document'

    def _looks_like_html(self, text):
        """检测文本是否看起来像 HTML"""
        stripped = text.strip()[:500].lower()
        return stripped.startswith('<!doctype') or stripped.startswith('<html') or '<div' in stripped[:200]

    def _html_to_markdown(self, html_text):
        """将 HTML 转为 Markdown（简易转换）"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_text, 'lxml')

            lines = []
            for elem in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'pre', 'table', 'blockquote']):
                tag = elem.name
                text = elem.get_text(strip=True)
                if not text:
                    continue
                if tag.startswith('h'):
                    level = int(tag[1])
                    lines.append(f'{"#" * level} {text}\n')
                elif tag == 'li':
                    lines.append(f'- {text}')
                elif tag == 'pre':
                    lines.append(f'```\n{text}\n```\n')
                elif tag == 'blockquote':
                    lines.append(f'> {text}\n')
                elif tag == 'table':
                    # 简易表格转换
                    rows = elem.find_all('tr')
                    for i, row in enumerate(rows):
                        cells = [c.get_text(strip=True) for c in row.find_all(['td', 'th'])]
                        lines.append('| ' + ' | '.join(cells) + ' |')
                        if i == 0:
                            lines.append('| ' + ' | '.join(['---'] * len(cells)) + ' |')
                    lines.append('')
                else:
                    lines.append(text + '\n')

            return '\n'.join(lines) if lines else html_text
        except Exception as e:
            logger.warning(f"[MinerU] HTML→Markdown 转换失败，保留原始 HTML: {e}")
            return html_text


# 模块级单例
mineru_service = MinerUService()
