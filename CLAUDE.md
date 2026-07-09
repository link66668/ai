# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered course learning assistant platform (课程学习助手Agent平台). Flask backend serving a vanilla HTML/CSS/JS frontend. Users manage courses, upload documents, chat with an AI agent powered by DeepSeek LLM, create/decompose tasks, and generate study plans. All UI is in Chinese.

- **Server:** `http://localhost:5000`
- **Demo account:** `demo / 123456`
- **Database:** SQLite (file: `backend/course_agent.db`, auto-created on first run)

## Commands

```bash
# Start (Windows one-click)
start.bat

# Start (manual)
cd ai/backend
pip install -r requirements.txt
python app.py

# No build step for frontend (vanilla HTML/CSS/JS served by Flask)
# No test suite exists
# No linter configured
```

Required environment variables (set in `backend/.env`, see `backend/.env.example`):
- `SECRET_KEY` — JWT signing key (required)
- `AI_API_KEY` — DeepSeek API key (required)
- `VISION_API_KEY`, `VISION_API_URL`, `VISION_MODEL` — multimodal vision model (optional)
- `EMBEDDING_API_KEY`, `EMBEDDING_API_URL`, `EMBEDDING_MODEL` — embedding model for RAG (optional)

## Architecture

### Three-Layer Backend (routes → models → services)

```
backend/
├── app.py              # Flask entry point, blueprint registration, demo data init
├── config.py           # All config via env vars / .env (Config class)
├── database.py         # Thread-safe SQLite singleton (thread-local connections)
├── migrations.py       # Schema migration helpers
├── routes/             # Flask blueprints (7 modules), JWT decorator in utils.py
├── models/             # Data access layer — raw SQL via database.py's db helper
├── services/           # Business logic (AI, RAG pipeline, document processing)
└── uploads/            # User-uploaded files (UUID-renamed)
```

**Key patterns:**
- All model methods are `@staticmethod` — no ORM, raw SQL via `db` helper
- `routes/utils.py` provides `@token_required` decorator (extracts JWT, passes `current_user` as first arg) and `success_response()`/`error_response()` helpers
- All API responses follow `{code: int, msg: str, data: ...}` format
- Flask serves both API and frontend: `static_folder='../frontend'`, non-API 404s fall back to `index.html`
- `services/__init__.py` uses lazy imports (`__getattr__`) to avoid circular dependencies and heavy startup cost
- Database operations use `db.fetch_one()`, `db.fetch_all()`, `db.insert()`, `db.update()`, `db.delete()` — all accept SQL + params tuple

### RAG Document Processing Pipeline

When a document is uploaded to a course, the async pipeline (`services/async_pipeline.py`) processes it:

**Parse → OCR → Layout Analysis → Table Extraction → Structure Extraction → Chunking → Embedding → Indexing**

Pipeline stages map to service modules:
| Stage | Service |
|---|---|
| Multi-format parsing | `document_parser.py` (PDF/Word/PPT/Excel/image/HTML/MD) |
| OCR | `ocr_service.py` (PaddleOCR primary, EasyOCR fallback) |
| Layout analysis | `layout_analyzer.py` |
| Table extraction | `table_extractor.py` |
| Structure extraction | `document_structure.py` |
| Semantic chunking | `chunking_service.py` (512 tokens, 128 overlap) |
| Embedding | `embedding_service.py` (API-based, OpenAI-compatible) |
| Vector store | `vector_store.py` (ChromaDB, per-course collections) |
| BM25 index | `bm25_manager.py` (per-course inverted index, pickled to `bm25_indexes/`) |

**Graceful degradation:** Many heavy dependencies (PaddleOCR, ChromaDB, tiktoken) may fail to install on Python 3.13/Windows. Each service has fallback logic:
- PaddleOCR → EasyOCR
- ChromaDB unavailable → pure BM25 retrieval
- tiktoken unavailable → character-level token estimation

### Chat & Streaming

- `streaming_service.py` — SSE streaming from DeepSeek API (`stream: true`), ~40 tokens/sec, supports user interrupt via `_interrupted_conversations` set
- `retrieval_service.py` — Hybrid search: vector + BM25 → RRF (Reciprocal Rank Fusion) fusion, with citation numbering
- `temp_file_service.py` — In-conversation file upload: parsed in-memory, Fernet-encrypted, never persisted to disk/DB/vector index
- `course_import_service.py` — CSV schedule import (北邮 format)
- `vision_service.py` — Multimodal image understanding via vision model API

### AI Service Dual Mode

`USE_REAL_LLM=true` in config calls DeepSeek API; `false` uses keyword-matching mock engine in `ai_service.py`. The mock is useful for development without API costs.

### Frontend

Vanilla HTML/CSS/JS, no framework or build tools:
- `js/api.js` — REST client (fetch + JWT auto-injection from localStorage)
- `js/utils.js` — Auth checks, toast notifications, Markdown rendering (custom regex-based, not a library)
- `css/style.css` — CSS custom properties design system
- Each page is a standalone HTML file loaded by Flask's static file server

## Database Schema

10 tables (7 original + 3 for RAG). Schema defined in `database.py`'s `_init_db()` with idempotent migrations in `_migrate_documents_table()`.

**Core tables:** `users`, `courses`, `documents`, `conversations`, `messages`, `tasks` (self-referencing `parent_task_id` for subtasks), `study_plans`

**RAG tables:** `document_chunks` (chunked document content with page ranges and heading paths), `document_processing_log` (pipeline stage tracking), `temp_file_sessions` (ephemeral file metadata only)

**Key:** Foreign keys with `ON DELETE CASCADE` (or `SET NULL` for optional references like `conversations.course_id`). SQLite foreign keys enabled per-connection via `PRAGMA foreign_keys = ON`.

## Adding New Features

| Task | Where |
|---|---|
| New API endpoint | Create/edit blueprint in `routes/`, register in `app.py`, use `@token_required` + `success_response()` |
| New database table | Add `CREATE TABLE` in `database.py` `_init_db()` |
| New DB column (migration) | Add to `_migrate_documents_table()` pattern or create new migration method |
| Modify AI behavior | `services/ai_service.py` (mock) or streaming/RAG pipeline in respective services |
| New frontend page | Create HTML in `frontend/`, add API calls in `js/api.js` |
| New service module | Add to `services/`, register lazy import in `services/__init__.py` |
