"""
多模态视觉模型服务

使用视觉语言模型（VLM）API 替代本地 OCR 进行图片理解：
- 图片 → VLM API → 文本描述（含文字提取、结构分析、图表描述）
- 降级链：Vision API 失败 → 返回错误信息

支持的 API（OpenAI 兼容格式）：
- Qwen-VL (DashScope) — 默认，中文优化
- GPT-4V / GPT-4o (OpenAI)
- 任何 OpenAI-compatible 视觉端点
"""
import base64
import io
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import Config

logger = logging.getLogger(__name__)


# ========== 视觉分析提示词 ==========

VISION_SYSTEM_PROMPT = """你是一个专业的文档分析与OCR助手。请仔细分析这张图片，并完成以下任务：

1. **文字识别**：准确提取图片中所有可见的文字内容，保持原文顺序和格式。
2. **结构分析**：识别标题、段落、列表、表格等文档结构层次。
3. **视觉元素描述**：如果有图表、公式、示意图等非文字元素，用文字描述其内容和含义。
4. **格式保留**：如有表格，用Markdown表格格式输出；如有列表，保留编号或项目符号。

要求：
- 使用中文输出（如果原文是英文，保留英文并附加中文说明）
- 输出纯文本，不要包含"我看到"、"这张图片显示"等元描述
- 文字内容要逐字准确，不要概括或总结
- 如果图片中没有文字，请明确说明"（此图片无可识别的文字内容）"
- 不要添加任何与图片内容无关的评论或建议"""


class VisionService:
    """
    多模态视觉模型服务（单例）

    对外接口：
    - recognize(image_path, ai_config=None) -> str
    - describe_images(image_paths, ai_config=None) -> list[str]
    """

    def __init__(self):
        self._clients = {}  # (api_url, api_key) → OpenAI client
        self._active_engine = 'vision_api'

    def _resolve(self, key, ai_config):
        """从用户配置或系统默认中获取值"""
        cfg = ai_config or {}
        user_val = cfg.get(key, '')
        if isinstance(user_val, str) and user_val.strip():
            return user_val.strip()
        if isinstance(user_val, bool):
            return user_val
        return getattr(Config, key.upper(), '')

    # ==================== 公开接口 ====================

    def recognize(self, image_path, ai_config=None):
        """
        识别/理解图片内容

        Args:
            image_path: 图片文件路径
            ai_config: 用户AI配置 dict（可选）

        Returns:
            str: 图片内容描述文字
        """
        vision_enabled = self._resolve('vision_enabled', ai_config)
        if isinstance(vision_enabled, str):
            vision_enabled = vision_enabled.lower() in ('true', '1', 'yes')
        if not vision_enabled:
            self._active_engine = 'none'
            return '[视觉识别未启用]'

        vision_api_key = self._resolve('vision_api_key', ai_config)
        if not vision_api_key:
            self._active_engine = 'none'
            return '[视觉识别未配置 API Key]'

        try:
            image_bytes = self._preprocess_image(image_path)
            image_data_uri = self._encode_base64(image_bytes)
            result = self._call_vision_api(image_data_uri, ai_config)
            if result and len(result.strip()) > 10:
                self._active_engine = 'vision_api'
                return result
            else:
                char_count = len(result) if result else 0
                logger.warning(f"[Vision] API 返回内容过短 ({char_count} 字符)")
                self._active_engine = 'none'
                return '[视觉识别失败：API 返回内容为空]'
        except Exception as e:
            logger.error(f"[Vision] API 调用失败: {e}")
            self._active_engine = 'none'
            return f'[视觉识别失败: {e}]'

    def recognize_bytes(self, image_bytes, mime_type='image/jpeg', ai_config=None):
        """
        识别/理解图片内容（直接接收图片字节，避免写磁盘）

        Args:
            image_bytes: 图片原始字节数据
            mime_type: 图片 MIME 类型（如 image/jpeg, image/png）
            ai_config: 用户AI配置 dict（可选）

        Returns:
            str: 图片内容描述文字
        """
        vision_enabled = self._resolve('vision_enabled', ai_config)
        if isinstance(vision_enabled, str):
            vision_enabled = vision_enabled.lower() in ('true', '1', 'yes')
        if not vision_enabled:
            self._active_engine = 'none'
            return '[视觉识别未启用]'

        vision_api_key = self._resolve('vision_api_key', ai_config)
        if not vision_api_key:
            self._active_engine = 'none'
            return '[视觉识别未配置 API Key]'

        try:
            processed = self._preprocess_image_bytes(image_bytes)
            image_data_uri = self._encode_base64(processed)
            result = self._call_vision_api(image_data_uri, ai_config)
            if result and len(result.strip()) > 10:
                self._active_engine = 'vision_api'
                return result
            else:
                char_count = len(result) if result else 0
                logger.warning(f"[Vision] API 返回内容过短 ({char_count} 字符)")
                self._active_engine = 'none'
                return '[视觉识别失败：API 返回内容为空]'
        except Exception as e:
            logger.error(f"[Vision] API 调用失败: {e}")
            self._active_engine = 'none'
            return f'[视觉识别失败: {e}]'

    def describe_images(self, image_paths, ai_config=None):
        """
        批量处理多张图片（并发调用 Vision API）

        Args:
            image_paths: 图片路径列表
            ai_config: 用户AI配置 dict（可选）

        Returns:
            list[str]: 每张图片的描述文字
        """
        if not image_paths:
            return []

        results = [None] * len(image_paths)

        def _process_one(idx, path):
            results[idx] = self.recognize(path, ai_config=ai_config)

        concurrency = int(self._resolve('vision_concurrency', ai_config) or Config.VISION_CONCURRENCY)
        workers = max(1, min(concurrency, len(image_paths)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_process_one, i, p) for i, p in enumerate(image_paths)]
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception as e:
                    logger.error(f"[Vision] 批量处理子任务异常: {e}")

        return results

    def get_active_engine_name(self):
        """返回当前活动的识别引擎名称"""
        return self._active_engine

    def is_available(self, ai_config=None):
        """检查 Vision API 是否可用"""
        vision_enabled = self._resolve('vision_enabled', ai_config)
        if isinstance(vision_enabled, str):
            vision_enabled = vision_enabled.lower() in ('true', '1', 'yes')
        return bool(vision_enabled and self._resolve('vision_api_key', ai_config))

    # ==================== 图片预处理 ====================

    def _preprocess_image(self, image_path):
        """图片预处理：缩放 + 格式统一（从文件读取）"""
        from PIL import Image

        img = Image.open(image_path)
        return self._pil_to_jpeg_bytes(img)

    def _preprocess_image_bytes(self, image_bytes):
        """图片预处理：缩放 + 格式统一（从字节读取）"""
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(image_bytes))
        return self._pil_to_jpeg_bytes(img)

    def _pil_to_jpeg_bytes(self, img):
        """PIL Image → 预处理后的 JPEG 字节"""
        from PIL import Image
        import io

        if img.mode == 'RGBA':
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        elif img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')

        w, h = img.size
        max_dim = max(w, h)
        max_size = Config.VISION_MAX_IMAGE_SIZE
        if max_dim > max_size:
            ratio = max_size / max_dim
            new_w, new_h = int(w * ratio), int(h * ratio)
            img = img.resize((new_w, new_h), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=85)
        return buf.getvalue()

    def _encode_base64(self, image_bytes):
        """Base64 编码 + data URI 前缀"""
        b64 = base64.b64encode(image_bytes).decode('utf-8')
        return f'data:image/jpeg;base64,{b64}'

    # ==================== Vision API 调用 ====================

    def _build_vision_messages(self, image_data_uri):
        """构建 OpenAI multimodal content 格式的消息列表"""
        return [
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'image_url',
                        'image_url': {'url': image_data_uri, 'detail': 'high'},
                    },
                    {'type': 'text', 'text': VISION_SYSTEM_PROMPT},
                ],
            }
        ]

    def _call_vision_api(self, image_data_uri, ai_config=None):
        """调用多模态 Vision API"""
        try:
            from openai import OpenAI

            api_url = self._resolve('vision_api_url', ai_config)
            api_key = self._resolve('vision_api_key', ai_config)
            model = self._resolve('vision_model', ai_config)

            cache_key = (api_url, api_key)
            if cache_key not in self._clients:
                self._clients[cache_key] = OpenAI(
                    base_url=api_url,
                    api_key=api_key,
                    timeout=120.0,
                )
                logger.info(f"[Vision] 客户端已初始化: {api_url} model={model}")

            client = self._clients[cache_key]
            messages = self._build_vision_messages(image_data_uri)

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=4096,
                temperature=0.1,
            )

            content = response.choices[0].message.content
            logger.info(f"[Vision] API 调用成功, 输出 {len(content)} 字符")
            return content

        except Exception as e:
            logger.error(f"[Vision] API 调用异常 ({type(e).__name__}): {e}")
            return None


# 全局单例
vision_service = VisionService()
