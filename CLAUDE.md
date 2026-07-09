# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered course learning assistant platform (课程学习助手Agent平台). Flask backend serving a vanilla HTML/CSS/JS frontend. Users manage courses, upload documents, chat with an AI agent powered by DeepSeek LLM, create/decompose tasks, and generate study plans. All UI and code comments are in Chinese.

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

# Run database migration (re-creates schema from _init_db, creates data dirs)
python backend/migrations.py

# No frontend build step (vanilla HTML/CSS/JS served by Flask)
# No test suite (课程项目，不写单元测试)
# No linter configured
```

Environment variables (set in `backend/.env`, all optional — missing vars log a warning but don't block startup):
- `SECRET_KEY` — JWT signing key
- `AI_API_KEY` — DeepSeek API key
- `USE_REAL_LLM` — `true` calls DeepSeek API; `false` uses keyword-matching mock (`ai_service.py`)
- `VISION_API_KEY`, `VISION_API_URL`, `VISION_MODEL` — multimodal vision model
- `EMBEDDING_API_KEY`, `EMBEDDING_API_URL`, `EMBEDDING_MODEL` — embedding model for RAG

## Architecture

### Three-Layer Backend (routes → models → services)

```
backend/
├── app.py              # Flask entry point, blueprint registration, demo data init
├── config.py           # All config via env vars / .env (Config class)
├── database.py         # Thread-safe SQLite singleton (thread-local connections), schema in _init_db()
├── migrations.py       # One-shot migration script
├── routes/             # 8 Flask blueprints: auth, course, document, chat, task, plan, agent, user_ai_config
├── models/             # Data access layer — raw SQL via database.py's db helper, all @staticmethod
├── services/           # Business logic (AI, RAG pipeline, document processing, streaming, vision)
├── uploads/            # User-uploaded files (UUID-renamed)
└── bm25_indexes/       # Pickled BM25 inverted indexes per course
```

**Key patterns:**
- `routes/utils.py` provides `@token_required` decorator (extracts JWT, passes `current_user` as first arg) and `success_response()`/`error_response()` helpers
- All API responses: `{code: int, msg: str, data: ...}`
- Flask serves both API and frontend: `static_folder='../frontend'`, non-API 404s fall back to `index.html`
- `services/__init__.py` uses lazy imports (`__getattr__`) to avoid circular dependencies
- Database operations: `db.fetch_one()`, `db.fetch_all()`, `db.insert()`, `db.update()`, `db.delete()` — all accept SQL + params tuple
- New blueprints must be exported in `routes/__init__.py` AND registered in `app.py`

### Per-User AI Config

All AI model parameters (chat/embedding/vision/document processing) are stored per-user in the `user_ai_config` table. Routes fetch config via `UserAIConfig.get_effective_config(user_id)` and pass as `ai_config` to services. Services never query the DB for user config directly. User custom config takes priority; unset fields fall back to system defaults (`config.py`/`.env`).

### RAG Document Processing Pipeline

When a document is uploaded, the async pipeline (`services/async_pipeline.py`) processes it:

**MinerU (if configured) → Parse → OCR → Layout → Table → Structure → Chunk → Embed → Index**

Stage 1 tries MinerU first: if `doc_api_url` or `doc_api_key` is set, `mineru_service.py` converts the document to Markdown (saved at `uploads/{课程名}/{资料名}.md`). On success, stages 2-4 (OCR/layout/structure) are skipped since MinerU already handles them. On failure, auto-fallback to local parsing.

| Stage | Service |
|---|---|
| MinerU conversion | `mineru_service.py` (REST API or Cloud SDK, optional) |
| Local parsing | `document_parser.py` (PDF/Word/PPT/Excel/image/HTML/MD) |
| OCR | `ocr_service.py` (PaddleOCR primary, EasyOCR fallback) |
| Layout analysis | `layout_analyzer.py` |
| Table extraction | `table_extractor.py` |
| Structure extraction | `document_structure.py` |
| Semantic chunking | `chunking_service.py` (512 tokens, 128 overlap) |
| Embedding | `embedding_service.py` (API-based, OpenAI-compatible) |
| Vector store | `vector_store.py` (ChromaDB, per-course collections) |
| BM25 index | `bm25_manager.py` (per-course inverted index, pickled to `bm25_indexes/`) |

**Graceful degradation:** Heavy dependencies may fail to install. Each service has fallbacks:
- PaddleOCR → EasyOCR
- ChromaDB unavailable → pure BM25 retrieval
- tiktoken unavailable → character-level token estimation

Background pipeline tasks fetch the owning user's AI config for embedding/OCR calls.

### Chat & Streaming

- `streaming_service.py` — SSE streaming from DeepSeek API, supports user interrupt via `_interrupted_conversations` set
- `retrieval_service.py` — Hybrid search: vector + BM25 → RRF fusion, with citation numbering
- `temp_file_service.py` — In-conversation file upload: parsed in-memory, Fernet-encrypted, never persisted
- `vision_service.py` — Multimodal image understanding via vision model API

### Frontend

Vanilla HTML/CSS/JS, no framework or build tools:
- `js/api.js` — REST client (`ApiClient` class, fetch + JWT auto-injection from localStorage)
- `js/utils.js` — Auth checks, toast notifications, Markdown rendering (custom regex-based)
- `css/style.css` — CSS custom properties design system
- Each page is a standalone HTML file; new pages must include the full sidebar navigation
- Sensitive fields (API keys) are masked in responses (first 4 + last 4 chars, middle `***`)

## Database Schema

11 tables. Schema defined in `database.py`'s `_init_db()`. To add tables or columns, edit the `CREATE TABLE` statements directly in `_init_db()` — no `ALTER TABLE` migrations, just delete and recreate the DB.

**Core:** `users`, `courses`, `documents` (includes `md_path` for MinerU output), `conversations`, `messages`, `tasks` (self-referencing `parent_task_id` for subtasks), `study_plans`, `user_ai_config`

**RAG:** `document_chunks`, `document_processing_log`, `temp_file_sessions`

Foreign keys use `ON DELETE CASCADE` (or `SET NULL` for optional refs). SQLite foreign keys enabled per-connection via `PRAGMA foreign_keys = ON`.

## Adding New Features

| Task | Where |
|---|---|
| New API endpoint | Create/edit blueprint in `routes/`, export in `routes/__init__.py`, register in `app.py`, use `@token_required` + `success_response()` |
| New database table/column | Edit `CREATE TABLE` in `database.py` `_init_db()` directly |
| New service module | Add to `services/`, register lazy import in `services/__init__.py` |
| Modify AI behavior | `services/ai_service.py` (mock) or streaming/RAG pipeline in respective services |
| New frontend page | Create HTML in `frontend/` with full sidebar, add API calls via `api.js` `ApiClient` |
