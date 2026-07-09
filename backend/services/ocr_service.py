"""
OCR 服务抽象层

双引擎策略：
- PaddleOCR (主): 中文印刷体95-98%，手写体~82%，自带版面分析
- EasyOCR (降级): 纯pip安装，CPU友好，PaddleOCR失败时自动切换

首次调用时懒加载模型，避免启动阻塞。
"""
import logging
from config import Config

logger = logging.getLogger(__name__)


class _BaseOCREngine:
    """OCR 引擎基类"""
    def recognize(self, image_path):
        raise NotImplementedError


class PaddleOCREngine(_BaseOCREngine):
    """PaddleOCR 引擎封装"""

    def __init__(self):
        self._ocr = None
        self._init_failed = False

    def _lazy_init(self):
        if self._ocr is not None:
            return
        if self._init_failed:
            return  # 已失败过，不再重试

        print("[OCR] 正在加载 PaddleOCR 模型（首次加载约需下载 200MB 权重）...")
        try:
            from paddleocr import PaddleOCR
            self._ocr = PaddleOCR(
                lang='ch',
                use_angle_cls=True,
                use_gpu=False,
                show_log=False,
            )
            print("[OCR] PaddleOCR 模型加载完成")
        except ImportError as e:
            print(f"[OCR] PaddleOCR 未安装: {e}")
            self._init_failed = True
        except Exception as e:
            print(f"[OCR] PaddleOCR 初始化失败: {e}")
            self._init_failed = True

    def recognize(self, image_path):
        self._lazy_init()
        try:
            result = self._ocr.ocr(image_path, cls=True)
            if not result or not result[0]:
                return ''
            texts = []
            for line in result[0]:
                if line and len(line) >= 2:
                    text = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                    texts.append(text)
            return '\n'.join(texts)
        except Exception as e:
            logger.warning(f"PaddleOCR 识别失败: {e}")
            return ''


class EasyOCREngine(_BaseOCREngine):
    """EasyOCR 引擎封装 —— PaddleOCR 的降级方案"""

    def __init__(self):
        self._reader = None

    def _lazy_init(self):
        if self._reader is None:
            print("[OCR] 正在加载 EasyOCR 模型（首次加载约需下载 120MB 权重）...")
            import easyocr
            self._reader = easyocr.Reader(
                ['ch_sim', 'en'],
                gpu=False,
                verbose=False,
            )
            print("[OCR] EasyOCR 模型加载完成")

    def recognize(self, image_path):
        self._lazy_init()
        try:
            result = self._reader.readtext(image_path)
            if not result:
                return ''
            texts = [item[1] for item in result]
            return '\n'.join(texts)
        except Exception as e:
            logger.warning(f"EasyOCR 识别失败: {e}")
            return ''


class OCRService:
    """
    OCR 服务单例

    自动选择最优引擎：
    1. 优先尝试 PaddleOCR
    2. 如果 PaddleOCR 不可用，自动降级到 EasyOCR
    3. 如果两者都不可用，返回空结果
    """

    def __init__(self):
        self._engine = None
        self._engine_name = None
        self._init_engine()

    def _init_engine(self):
        """初始化 OCR 引擎，自动降级（真正导入测试，不依赖懒加载）"""
        preferred = Config.OCR_ENGINE

        # 尝试 PaddleOCR
        if preferred == 'paddleocr':
            try:
                # 真正测试导入，而不是仅创建实例
                from paddleocr import PaddleOCR
                self._engine = PaddleOCREngine()
                self._engine_name = 'paddleocr'
                print("[OCR] 已选择 PaddleOCR 引擎")
                return
            except ImportError:
                print("[OCR] PaddleOCR 未安装，自动降级到 EasyOCR...")
            except Exception as e:
                print(f"[OCR] PaddleOCR 初始化失败: {e}")
                print("[OCR] 自动降级到 EasyOCR...")

        # 尝试 EasyOCR
        try:
            import easyocr
            self._engine = EasyOCREngine()
            self._engine_name = 'easyocr'
            print("[OCR] 已选择 EasyOCR 引擎")
            return
        except ImportError:
            print("[OCR] EasyOCR 未安装")
        except Exception as e:
            print(f"[OCR] EasyOCR 初始化也失败: {e}")

        # 两者都不可用
        self._engine = None
        self._engine_name = 'none'
        print("[OCR] 警告：无可用的 OCR 引擎！图片识别将不可用。")

    def recognize(self, image_path):
        """
        识别图片中的文字

        Args:
            image_path: 图片文件路径

        Returns:
            str: 识别出的文字，引擎不可用时返回空字符串
        """
        if self._engine is None:
            print("[OCR] 无可用 OCR 引擎，跳过识别")
            return ''
        return self._engine.recognize(image_path)

    def get_active_engine_name(self):
        """返回当前使用的 OCR 引擎名称"""
        return self._engine_name

    def is_available(self):
        """检查 OCR 是否可用"""
        return self._engine is not None


# 全局单例
ocr_service = OCRService()
