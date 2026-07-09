# -*- coding: utf-8 -*-
"""
数据库迁移脚本 — 一键执行数据库结构更新

用法：
    python migrations.py          # 在 backend 目录下运行
    python backend/migrations.py  # 在项目根目录下运行

功能：
    1. 为 documents 表添加处理相关字段（幂等）
    2. 创建 document_chunks、document_processing_log、temp_file_sessions 表
    3. 创建 chroma_data/ 和 bm25_indexes/ 目录
"""
import os
import sys

# 确保在 backend 目录下运行
backend_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

from config import Config
from database import db


def run_migrations():
    """执行所有迁移"""
    config = Config()
    print("=" * 60)
    print("课程学习助手Agent平台 — 数据库迁移")
    print("=" * 60)

    # 1. 数据库迁移（表结构）
    print("\n[1/3] 执行数据库表结构迁移...")
    try:
        # database.py 的 _init_db() 已包含迁移逻辑
        # 重新调用 _init_db() 确保新表和字段存在
        db._init_db()
        print("  [OK] 数据库表结构迁移完成")
    except Exception as e:
        print(f"  [FAIL] 数据库迁移失败: {e}")
        return False

    # 2. 创建 ChromaDB 向量存储目录
    print(f"\n[2/3] 创建数据目录...")
    for path, label in [
        (config.CHROMA_DATA_PATH, "ChromaDB 向量存储"),
        (config.BM25_INDEX_PATH, "BM25 索引"),
    ]:
        os.makedirs(path, exist_ok=True)
        print(f"  [OK] {label}: {path}")

    # 3. 验证
    print(f"\n[3/3] 验证迁移结果...")
    conn = db.get_connection()
    cursor = conn.cursor()

    # 检查 documents 表新列
    cursor.execute("PRAGMA table_info(documents)")
    doc_columns = {row[1] for row in cursor.fetchall()}
    expected = {'processing_status', 'processing_progress', 'processing_error',
                'structured_content', 'toc_tree', 'page_count', 'chunk_count', 'metadata_json'}
    missing = expected - doc_columns
    if missing:
        print(f"  [FAIL] documents 表缺少列: {missing}")
    else:
        print(f"  [OK] documents 表包含所有新列 ({len(expected)} 个)")

    # 检查新表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    new_tables = {'document_chunks', 'document_processing_log', 'temp_file_sessions'}
    missing_tables = new_tables - tables
    if missing_tables:
        print(f"  [FAIL] 缺少新表: {missing_tables}")
    else:
        print(f"  [OK] 所有新表已创建 ({len(new_tables)} 个)")

    cursor.close()

    print("\n" + "=" * 60)
    print("迁移完成！")
    print("=" * 60)
    return True


if __name__ == '__main__':
    success = run_migrations()
    sys.exit(0 if success else 1)
