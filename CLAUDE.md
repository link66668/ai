# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered course learning assistant platform (课程学习助手Agent平台). Two sub-projects:

1. **Main app** — Flask backend + vanilla HTML/CSS/JS frontend (Chinese UI/comments)
2. **chat-app/** — Independent React+TypeScript chat UI (standalone, Vite-based)

## Commands

### Main App (Flask)

```bash
# Start (Windows one-click)
start.bat

# Start (manual)
cd ai/backend
pip install -r requirements.txt
python app.py

# Run database migration (re-creates schema from _init_db, creates data dirs)
python backend/migrations.py
```

- **Server:** `http://localhost:5000`
- **Demo account:** `demo / 123456`
- **Database:** SQLite (`backend/course_agent.db`, auto-created on first run)
- **No tests** (课程项目，不写单元测试)
- **No linter** configured

### Chat App (React + TypeScript)

```bash
cd ai/chat-app

pnpm install          # Install dependencies (pnpm 11.8)
npm run dev           # Vite dev server on localhost:5173
npm run build         # TypeScript check + Vite build
npm run preview       # Preview production build
```

- Tests available via `npm run test:run` or `npm run test` (watch mode)
- TypeScript strict mode, ES2022 target

## Architecture

### Main App: Three-Layer Backend

```
backend/
├── app.py               # Flask entry, blueprint registration, demo data init
├── config.py            # Config via env vars / .env (all optional — missing vars log warnings only)
├── database.py          # Thread-safe SQLite singleton, schema in _init_db()
├── migrations.py        # One-shot migration script
├── routes/              # 8 Flask blueprints
│   ├── auth.py, course.py, document.py, chat.py, task.py, plan.py
│   ├── agent.py, user_ai_config.py
│   └── utils.py         # @token_required, success_response(), error_response()
├── models/              # Data access — raw SQL via db helper, all @staticmethod
├── services/            # Business logic (AI, RAG pipeline, streaming, vision)
├── uploads/             # User-uploaded files (UUID-renamed)
└── bm25_indexes/        # Pickled BM25 inverted indexes per course
```

**Key patterns:**
- `@token_required` decorator injects `current_user` as first arg; all API responses `{code, msg, data}`
- Flask serves both API and frontend: `static_folder='../frontend'`, non-API 404s → `index.html`
- `services/__init__.py` uses lazy imports (`__getattr__`) to avoid circular deps
- New blueprints: export in `routes/__init__.py` AND register in `app.py`

### Chat App: React + TypeScript

```
chat-app/src/
├── main.tsx              # React DOM mount
├── App.tsx               # Root component (ChatWindow)
├── components/           # React components (sidebar, messages, composer, etc.)
├── stores/               # Zustand 5 stores (persisted to localStorage)
├── services/             # API/LLM client wrappers
├── types/                # TypeScript type definitions
└── utils/                # Utility functions
```

Uses Radix UI primitives (Dialog, ScrollArea, Select, Tooltip), Tailwind CSS v4, lucide-react icons, Vercel AI SDK 6 (supports OpenAI, Anthropic, OpenAI-compatible providers).

### RAG Document Processing Pipeline

```
MinerU (optional) → Parse → OCR/Vision → Layout → Table → Structure → Chunk → Embed → Index
```

| Stage | Service | Fallback |
|---|---|---|
| MinerU | `mineru_service.py` (optional REST/Cloud) | Local parsing |
| Local parse | `document_parser.py` (PDF/Word/PPT/Excel/Image/HTML/MD) | — |
| OCR | `ocr_service.py` | PaddleOCR → EasyOCR |
| Vision | `vision_service.py` | — |
| Layout | `layout_analyzer.py` | — |
| Table | `table_extractor.py` | — |
| Structure | `document_structure.py` | — |
| Chunking | `chunking_service.py` (512 tokens, 128 overlap) | Char-level estimation |
| Embedding | `embedding_service.py` (OpenAI-compatible API) | Hash vector |
| Vector store | `vector_store.py` (ChromaDB, per-course) | Pure BM25 |
| BM25 index | `bm25_manager.py` (per-course, pickled) | Always available |

### Per-User AI Config

All AI params (chat/embedding/vision/doc processing) stored per-user in `user_ai_config` table. Routes fetch via `UserAIConfig.get_effective_config(user_id)` → pass as `ai_config` dict to services. Services never query DB directly. Background tasks (doc pipeline) use config from the document's owning user.

### Chat & Streaming

- `streaming_service.py` — SSE from DeepSeek API, user interrupt via `_interrupted_conversations` set
- `retrieval_service.py` — Hybrid search (vector + BM25 → RRF fusion) with citation numbering
- `temp_file_service.py` — In-conversation file upload (in-memory parse, Fernet-encrypted)
- `vision_service.py` — Multimodal image understanding via vision API
- `chat_engine.py` — Core orchestrator: context parsing → message building → streaming (RAG and non-RAG)

### Frontend (Vanilla)

- `js/api.js` — `ApiClient` class (fetch + JWT auto-injection from localStorage)
- `js/utils.js` — Auth checks, toast notifications, custom regex Markdown rendering
- `css/style.css` — CSS custom properties design system
- Each page is a standalone HTML file with full sidebar navigation
- Sensitive fields (API Keys) masked: first 4 + last 4 chars, middle `***`

## Database Schema

11 tables, schema defined inline in `database.py`'s `_init_db()`. No migration scripts — edit `CREATE TABLE` directly and recreate the DB.

**Core:** `users`, `courses`, `documents` (includes `md_path` for MinerU output), `conversations`, `messages`, `tasks` (self-referencing `parent_task_id`), `study_plans`, `user_ai_config`

**RAG:** `document_chunks`, `document_processing_log`, `temp_file_sessions`

Foreign keys use `ON DELETE CASCADE` / `SET NULL`. SQLite `PRAGMA foreign_keys = ON` per-connection.

## Environment Variables

Set in `backend/.env`, all optional (missing vars log warnings):

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | JWT signing key |
| `AI_API_KEY`, `AI_API_URL`, `AI_MODEL` | DeepSeek chat model |
| `USE_REAL_LLM` | `true` → DeepSeek API; `false` → keyword mock |
| `VISION_API_KEY`, `VISION_API_URL`, `VISION_MODEL` | Multimodal vision model |
| `EMBEDDING_API_KEY`, `EMBEDDING_API_URL`, `EMBEDDING_MODEL` | Embedding model for RAG |
| `EMBEDDING_BACKEND` | `api` (default) — always uses API mode |

## Adding New Features

| Task | Where |
|---|---|
| New API endpoint | Blueprint in `routes/`, export in `routes/__init__.py`, register in `app.py`, `@token_required` + `success_response()` |
| New DB table/column | Edit `CREATE TABLE` in `database.py` `_init_db()` directly |
| New service module | Add to `services/`, register lazy import in `services/__init__.py` |
| New frontend page | Create HTML in `frontend/` with full sidebar, `ApiClient` for API calls |
| Modify AI behavior | `ai_service.py` (mock) or streaming/RAG pipeline in respective services |
| New chat-app component | Add under `chat-app/src/components/`, use Zustand stores for state |

## Key Conventions

- Code comments and UI: **Chinese**
- No unit tests (课程项目)
- AI config flows: route → `UserAIConfig.get_effective_config()` → `ai_config` dict → service layer; services never query DB
- DB changes: edit `_init_db()` directly, no `ALTER TABLE`, no migration scripts
- API Keys in responses: mask as `sk-1234***5678`
