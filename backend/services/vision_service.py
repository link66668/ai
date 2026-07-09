"""
多模态视觉模型服务

使用视觉语言模型（VLM）API 替代本地 OCR 进行图片理解：
- 图片 → VLM API → 文本描述（含文字提取、结构分析、图表描述）
- 降级链：Vision API 失败 → 本地 OCR → 返回空

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
# 输出直接作为 content_text 存入 RAG 管线

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

    对外接口与 OCRService 一致：
    - recognize(image_path) -> str
    - get_active_engine_name() -> str

    内部自动处理：图片预处理 → base64编码 → API调用 → 降级
    """

    def __init__(self):
        self._client = None
        self._init_failed = False
        self._active_engine = 'vision_api'  # 'vision_api' | 'none'

    # ==================== 公开接口 ====================

    def recognize(self, image_path):
        """
        识别/理解图片内容（主入口 — 纯 API，无本地 OCR）

        Args:
            image_path: 图片文件路径

        Returns:
            str: 图片内容描述文字，失败返回错误信息
        """
        # Gate 1: Vision API 是否可用
        if not Config.VISION_ENABLED:
            self._active_engine = 'none'
            return '[视觉识别未启用]'

        if not Config.VISION_API_KEY:
            self._active_engine = 'none'
            return '[视觉识别未配置 API Key]'

        # Gate 2: 尝试 Vision API
        try:
            image_bytes = self._preprocess_image(image_path)
            image_data_uri = self._encode_base64(image_bytes)
            result = self._call_vision_api(image_data_uri)
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

    def describe_images(self, image_paths):
        """
        批量处理多张图片（并发调用 Vision API）

        Args:
            image_paths: 图片路径列表

        Returns:
            list[str]: 每张图片的描述文字，失败项为 OCR 回退结果
        """
        if not image_paths:
            return []

        results = [None] * len(image_paths)

        def _process_one(idx, path):
            results[idx] = self.recognize(path)

        workers = max(1, min(Config.VISION_CONCURRENCY, len(image_paths)))
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

    def is_available(self):
        """检查 Vision API 是否可用"""
        return (
            Config.VISION_ENABLED
            and bool(Config.VISION_API_KEY)
            and not self._init_failed
        )

    # ==================== 图片预处理 ====================

    def _preprocess_image(self, image_path):
        """
        图片预处理：缩放 + 格式统一

        - 最长边超过 VISION_MAX_IMAGE_SIZE 时等比缩放
        - RGBA → RGB（贴白色背景）
        - 输出 JPEG bytes（质量 85）

        Returns:
            bytes: 处理后的图片字节
        """
        from PIL import Image

        img = Image.open(image_path)

        # RGBA → RGB
        if img.mode == 'RGBA':
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        elif img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')

        # 缩放
        w, h = img.size
        max_dim = max(w, h)
        if max_dim > Config.VISION_MAX_IMAGE_SIZE:
            ratio = Config.VISION_MAX_IMAGE_SIZE / max_dim
            new_w, new_h = int(w * ratio), int(h * ratio)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            logger.debug(f"[Vision] 图片缩放: {w}x{h} → {new_w}x{new_h}")

        # 输出 JPEG
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=85)
        return buf.getvalue()

    def _encode_base64(self, image_bytes):
        """
        Base64 编码 + data URI 前缀

        Returns:
            str: data:image/jpeg;base64,...
        """
        b64 = base64.b64encode(image_bytes).decode('utf-8')
        return f'data:image/jpeg;base64,{b64}'

    # ==================== Vision API 调用 ====================

    def _build_vision_messages(self, image_data_uri):
        """
        构建 OpenAI multimodal content 格式的消息列表

        Args:
            image_data_uri: Base64 data URI

        Returns:
            list[dict]: 消息列表
        """
        return [
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'image_url',
                        'image_url': {
                            'url': image_data_uri,
                            'detail': 'high',
                        },
                    },
                    {
                        'type': 'text',
                        'text': VISION_SYSTEM_PROMPT,
                    },
                ],
            }
        ]

    def _call_vision_api(self, image_data_uri):
        """
        调用多模态 Vision API

        Returns:
            str: 模型输出文字，失败返回 None
        """
        if self._init_failed:
            return None

        try:
            from openai import OpenAI

            if self._client is None:
                self._client = OpenAI(
                    base_url=Config.VISION_API_URL,
                    api_key=Config.VISION_API_KEY,
                    timeout=120.0,  # 图片理解可能需要较长时间
                )
                logger.info(
                    f"[Vision] 客户端已初始化: {Config.VISION_API_URL} "
                    f"model={Config.VISION_MODEL}"
                )

            messages = self._build_vision_messages(image_data_uri)

            response = self._client.chat.completions.create(
                model=Config.VISION_MODEL,
                messages=messages,
                max_tokens=4096,
                temperature=0.1,  # 低温度确保文字识别准确
            )

            content = response.choices[0].message.content
            logger.info(f"[Vision] API 调用成功, 输出 {len(content)} 字符")
            return content

        except ImportError:
            logger.error("[Vision] openai 包未安装")
            self._init_failed = True
            return None
        except Exception as e:
            error_type = type(e).__name__
            # 判断错误类型决定是否标记为初始化失败
            if 'AuthenticationError' in error_type or 'PermissionDeniedError' in error_type:
                logger.error(f"[Vision] API 认证失败: {e}")
                self._init_failed = True
            elif 'RateLimitError' in error_type:
                logger.warning(f"[Vision] API 频率限制: {e}")
            elif 'APITimeoutError' in error_type or 'Timeout' in error_type:
                logger.warning(f"[Vision] API 超时: {e}")
            elif 'BadRequestError' in error_type:
                logger.error(f"[Vision] 请求格式错误（可能是模型不支持多模态）: {e}")
                self._init_failed = True
            else:
                logger.error(f"[Vision] API 调用异常 ({error_type}): {e}")
            return None

# 全局单例
vision_service = VisionService()
