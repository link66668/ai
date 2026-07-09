"""
临时文件管理服务

对话中上传的临时文件管理：
- Fernet 加密存储于内存
- 轻量解析提取文本
- 会话绑定生命周期
- 不写磁盘、不入库、不进向量索引
"""
import uuid
import logging
from datetime import datetime, timedelta
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class TempFileManager:
    """
    临时文件管理器（单例）

    特性：
    - 进程级 Fernet 密钥（重启后失效）
    - 文件内容加密存储在内存 dict
    - 元数据（仅文件名/大小/类型）写入数据库
    - 会话结束或超时自动销毁
    """

    SESSION_TTL_HOURS = 2  # 会话超时时间

    def __init__(self):
        self._fernet = Fernet(Fernet.generate_key())
        self._sessions = {}      # session_id -> {conversation_id, files: [...], created_at}
        self._file_contents = {} # file_id -> encrypted bytes
        self._file_texts = {}    # file_id -> parsed plain text (for LLM context)
        self._file_status = {}   # file_id -> 'processing' | 'done' | 'error'
        print("[TempFile] 临时文件管理器已初始化（内存加密存储 + 异步处理）")

    def create_session(self, conversation_id):
        """
        创建临时文件会话

        Args:
            conversation_id: 对话 ID

        Returns:
            str: session_id
        """
        session_id = uuid.uuid4().hex
        self._sessions[session_id] = {
            'conversation_id': conversation_id,
            'files': [],
            'created_at': datetime.now(),
        }
        return session_id

    def get_or_create_session(self, conversation_id):
        """获取或创建会话"""
        for sid, session in self._sessions.items():
            if session['conversation_id'] == conversation_id:
                # 检查是否过期
                if datetime.now() - session['created_at'] > timedelta(hours=self.SESSION_TTL_HOURS):
                    self.destroy_session(sid)
                    break
                return sid
        return self.create_session(conversation_id)

    def add_file(self, session_id, file_obj, filename, file_type='', ai_config=None):
        """
        添加临时文件到会话（异步处理，立即返回）

        Args:
            session_id: 会话 ID
            file_obj: Flask FileStorage 对象
            filename: 原始文件名
            file_type: 文件类型（扩展名）

        Returns:
            dict: {file_id, filename, file_type, file_size, preview, status}
        """
        if session_id not in self._sessions:
            raise ValueError(f"会话不存在: {session_id}")

        # 读取文件内容
        file_data = file_obj.read()
        file_size = len(file_data)

        # 加密存储
        file_id = uuid.uuid4().hex
        encrypted = self._fernet.encrypt(file_data)
        self._file_contents[file_id] = encrypted

        # 标记为处理中（异步解析）
        self._file_texts[file_id] = ''
        self._file_status[file_id] = 'processing'

        # 记录元数据
        file_meta = {
            'file_id': file_id,
            'filename': filename,
            'file_type': file_type,
            'file_size': file_size,
            'added_at': datetime.now().isoformat(),
        }
        self._sessions[session_id]['files'].append(file_meta)

        # 记录元数据到数据库（不含内容）
        self._log_to_db(session_id, filename, file_type, file_size)

        # 后台线程异步解析（避免阻塞 HTTP 请求，防止切页打断处理）
        import threading
        def parse_worker():
            try:
                preview_text = self._parse_file(file_data, filename, file_type, ai_config=ai_config)
                self._file_texts[file_id] = preview_text
                self._file_status[file_id] = 'done'
                print(f"[TempFile] 文件 {filename} 异步处理完成 ({len(preview_text)} 字符)")
            except Exception as e:
                logger.warning(f"临时文件解析失败: {e}")
                self._file_texts[file_id] = f"[文件解析失败: {filename}]"
                self._file_status[file_id] = 'error'
                print(f"[TempFile] 文件 {filename} 处理失败: {e}")

        threading.Thread(target=parse_worker, daemon=True).start()

        return {
            'file_id': file_id,
            'filename': filename,
            'file_type': file_type,
            'file_size': file_size,
            'preview': '',
            'status': 'processing',
        }

    def _parse_file(self, file_data, filename, file_type, ai_config=None):
        """轻量解析文件内容"""
        import os
        import tempfile
        from services.document_parser import LightweightParser

        # 写入临时文件供解析器使用
        suffix = f'.{file_type}' if file_type else ''
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=suffix
            ) as tmp:
                tmp.write(file_data)
                tmp_path = tmp.name

            parser = LightweightParser()
            text = parser.parse(tmp_path, file_type, ai_config=ai_config)
            return text
        except Exception as e:
            logger.warning(f"临时文件解析失败: {e}")
            return f"[文件解析失败: {filename}]"
        finally:
            # 立即删除临时文件
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    def get_context(self, session_id, wait_timeout=30):
        """
        获取会话中所有已完成文件的文本内容（用于LLM上下文）

        Args:
            session_id: 会话 ID
            wait_timeout: 等待处理中的文件完成的超时秒数（0=不等待）

        跳过仍在处理中的文件，避免传入空内容。
        如果 wait_timeout > 0，会等待处理中的文件完成（最多 wait_timeout 秒）。
        """
        if session_id not in self._sessions:
            return ''

        session = self._sessions[session_id]

        # 等待处理中的文件完成
        if wait_timeout > 0:
            import time
            deadline = time.time() + wait_timeout
            for fmeta in session['files']:
                fid = fmeta['file_id']
                while self._file_status.get(fid) == 'processing':
                    if time.time() > deadline:
                        break
                    time.sleep(0.5)

        parts = []
        for fmeta in session['files']:
            fid = fmeta['file_id']
            status = self._file_status.get(fid, 'done')
            if status != 'done':
                # 仍在处理中 → 添加占位提示
                if status == 'processing':
                    parts.append(f'[临时文件: {fmeta["filename"]}]\n（文件仍在处理中，内容暂不可用。请稍后再试。）')
                elif status == 'error':
                    parts.append(f'[临时文件: {fmeta["filename"]}]\n（文件处理失败，无法识别内容）')
                continue
            text = self._file_texts.get(fid, '')
            if text:
                parts.append(f'[临时文件: {fmeta["filename"]}]\n{text}')
        return '\n\n'.join(parts)

    def get_image_data(self, session_id):
        """
        获取会话中所有图片文件的原始字节数据（用于多模态消息构建）

        Returns:
            list[dict]: [{filename, file_type, image_bytes, mime_type}]
        """
        if session_id not in self._sessions:
            return []

        session = self._sessions[session_id]
        images = []
        image_types = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}

        for fmeta in session['files']:
            fid = fmeta['file_id']
            file_type = fmeta.get('file_type', '').lower()

            if file_type not in image_types:
                continue

            # 只处理已完成的文件
            status = self._file_status.get(fid, 'done')
            if status != 'done':
                continue

            encrypted = self._file_contents.get(fid)
            if not encrypted:
                continue

            try:
                image_bytes = self._fernet.decrypt(encrypted)
                mime_map = {
                    'png': 'image/png', 'jpg': 'image/jpeg',
                    'jpeg': 'image/jpeg', 'gif': 'image/gif',
                    'bmp': 'image/bmp', 'webp': 'image/webp',
                }
                images.append({
                    'filename': fmeta['filename'],
                    'file_type': file_type,
                    'image_bytes': image_bytes,
                    'mime_type': mime_map.get(file_type, 'image/jpeg'),
                })
            except Exception as e:
                logger.warning(f"解密图片数据失败: {fmeta['filename']}: {e}")

        return images

    def get_file_list(self, session_id):
        """获取会话文件列表（不含内容）"""
        if session_id not in self._sessions:
            return []
        files = self._sessions[session_id]['files']
        # 附加处理状态
        result = []
        for f in files:
            fid = f['file_id']
            status = self._file_status.get(fid, 'done')
            preview = ''
            if status == 'done':
                preview = self._file_texts.get(fid, '')[:500]
            result.append({**f, 'status': status, 'preview': preview})
        return result

    def get_file_status(self, session_id, file_id):
        """
        查询单个文件处理状态

        Returns:
            dict: {status: 'processing'|'done'|'error', preview: str}
        """
        if session_id not in self._sessions:
            return {'status': 'not_found', 'preview': ''}
        # 验证 file_id 属于该会话
        session = self._sessions[session_id]
        if not any(f['file_id'] == file_id for f in session['files']):
            return {'status': 'not_found', 'preview': ''}
        status = self._file_status.get(file_id, 'done')
        preview = ''
        if status == 'done':
            preview = self._file_texts.get(file_id, '')[:500]
        return {'status': status, 'preview': preview}

    def remove_file(self, session_id, file_id):
        """删除单个临时文件"""
        self._file_contents.pop(file_id, None)
        self._file_texts.pop(file_id, None)
        if session_id in self._sessions:
            self._sessions[session_id]['files'] = [
                f for f in self._sessions[session_id]['files']
                if f['file_id'] != file_id
            ]

    def destroy_session(self, session_id):
        """
        销毁会话及所有临时文件

        所有加密内容和解析文本从内存中清除
        """
        if session_id not in self._sessions:
            return

        session = self._sessions[session_id]
        for fmeta in session['files']:
            fid = fmeta['file_id']
            self._file_contents.pop(fid, None)
            self._file_texts.pop(fid, None)
            self._file_status.pop(fid, None)

        del self._sessions[session_id]

        # 更新数据库记录
        self._mark_destroyed(session_id)

        print(f"[TempFile] 会话 {session_id[:8]}... 已销毁")

    def cleanup_expired(self):
        """清理过期会话"""
        now = datetime.now()
        expired = []
        for sid, session in self._sessions.items():
            if now - session['created_at'] > timedelta(hours=self.SESSION_TTL_HOURS):
                expired.append(sid)

        for sid in expired:
            self.destroy_session(sid)

        if expired:
            print(f"[TempFile] 清理了 {len(expired)} 个过期会话")

    def _log_to_db(self, session_id, filename, file_type, file_size):
        """记录临时文件元数据到数据库"""
        try:
            from database import db
            conversation_id = None
            if session_id in self._sessions:
                conversation_id = self._sessions[session_id].get('conversation_id')

            db.insert(
                """INSERT INTO temp_file_sessions
                   (session_id, conversation_id, file_name, file_type, file_size)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, conversation_id, filename, file_type, file_size)
            )
        except Exception as e:
            logger.warning(f"记录临时文件元数据失败: {e}")

    def _mark_destroyed(self, session_id):
        """标记数据库记录为已销毁"""
        try:
            from database import db
            db.update(
                "UPDATE temp_file_sessions SET destroyed_at = ? WHERE session_id = ?",
                (datetime.now().isoformat(), session_id)
            )
        except Exception as e:
            logger.warning(f"标记销毁失败: {e}")

    def has_session(self, session_id):
        """检查会话是否存在"""
        return session_id in self._sessions


# 全局单例
temp_file_manager = TempFileManager()
