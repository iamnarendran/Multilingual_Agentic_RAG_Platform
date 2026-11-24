# Akshara (अक्षर): Multilingual Agentic RAG

Ask questions about your documents in English or any of 22 Indian languages and get answers that cite the exact page they came from. A team of AI agents plans the search, checks what it found, writes the answer in your language and verifies it against the sources, and you can watch each step happen live.

![Chat: the agent trace, a cited answer and its sources](docs/images/chat.jpg)

| Library: a Tamil PDF with broken fonts, read with OCR | Mobile, dark mode, asking in Tamil |
| --- | --- |
| ![Library panel](docs/images/library.jpg) | ![Mobile chat in Tamil](docs/images/mobile-tamil.jpg) |

<sub>Screenshots taken with the offline demo backend (see [Try it without API keys](#1-try-it-without-api-keys)), which quotes passages instead of calling a language model.</sub>

## What it does

- **Chat with your documents.** Upload PDF, Word, text, Markdown or CSV files, then ask. Answers stream in word by word with numbered citations; hover a citation to preview the passage, open a source to read it in full.
- **Any language in, same language out.** Ask in Hindi about an English report, or in English about a Tamil book. The answer comes back in the language you asked in.
- **Reads hard PDFs.** Many Indian-language PDFs use old fonts whose embedded text is garbage. Akshara detects that page by page and re-reads those pages (and scanned ones) with OCR.
- **Agents you can watch.** Every answer shows which agents ran, what they decided and how long they took.
- **Honest answers.** If your documents don't contain the answer, it says so rather than guessing. A validator flags statements the sources don't support.
- **A real app.** Accounts, private per-user libraries, saved conversations you can rename or delete, document scoping ("search only these files"), stop button, dark mode, mobile layout.

## How it works

### The agents (LangGraph)

```
question ─► Language ─► Router ──┬── small talk ────────────────────────────► Generator ─► done
                                 │
                                 └── documents ─► Planner ─► Retriever ─► Grader ─┬─► Generator ─► Validator ─► done
                                                    ▲                              │
                                                    └──── nothing relevant: retry ─┘
```

| Agent | Uses an LLM? | Job |
| --- | --- | --- |
| **Language** | no | Detects the question's language from its Unicode script (then `langdetect` to tell apart languages that share a script, like Hindi and Marathi). |
| **Router** | yes (fast model) | Decides if the message needs the documents, classifies it (factual, comparison, summary, ...) and rewrites follow-ups like "what did he write?" into a standalone question. |
| **Planner** | yes (fast model) | Writes up to 5 search queries, translated into the languages your documents are written in, so a Hindi question can find English text and vice versa. |
| **Retriever** | no | Runs every query as a hybrid search (meaning + keywords) in Qdrant and merges the results with Reciprocal Rank Fusion. |
| **Grader** | yes (fast model) | Keeps only passages that actually help. If none do, it sends feedback to the Planner for one more try (corrective RAG). |
| **Generator** | yes (main model) | Streams the answer in the question's language, citing sources as [1], [2], ... |
| **Validator** | yes (fast model) | Checks each claim against the cited sources and flags unsupported ones. |

Each agent reports progress through LangGraph's custom stream; the API forwards it to the browser as Server-Sent Events.

### Ingestion

```
upload ─► extract text ─► garbled or scanned page? ─► OCR (Tesseract) ─► strip running headers/footers
       ─► Indic-aware chunking ─► dense vectors (multilingual-e5-large) + BM25 sparse vectors ─► Qdrant
```

- **Garbled-text detection**: measures the share of control and private-use glyphs per page; legacy-font Tamil scores about 13%, clean text about 0%.
- **Chunking** splits on paragraphs, lines, then sentence ends including the Devanagari danda `।` and `॥`; chunks never cross pages so every citation has a page number.
- **Keyword search** uses a custom BM25 tokenizer that keeps Indic words whole. Standard tokenizers split words like `किताब` at their vowel signs.
- **Isolation**: every chunk carries its owner's id and every query filters on it.

## Tech stack

| Layer | Choice |
| --- | --- |
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, the [Anek](https://github.com/EkType/Anek) type family for all Indian scripts |
| API | FastAPI, Server-Sent Events, JWT auth (bcrypt passwords) |
| Agents | LangGraph; any OpenAI-compatible LLM API ([OpenRouter](https://openrouter.ai) by default: Claude, Gemini, GPT, Llama, ...) |
| Retrieval | Qdrant hybrid search (dense + sparse with IDF), RRF fusion |
| Embeddings | `intfloat/multilingual-e5-large` run locally with fastembed (ONNX, CPU, no PyTorch), or any embeddings API |
| Documents | PyMuPDF, python-docx, Tesseract OCR |
| Data | SQLite by default, PostgreSQL in production (SQLAlchemy 2, async) |

## Quick start

### 1. Try it without API keys

The demo backend runs the real app (auth, uploads, OCR, hybrid search, the agent graph, streaming) with a toy embedder and a scripted "LLM" that just quotes the passages it finds. Data lives in memory.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m scripts.demo_server                       # http://localhost:8000
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev                                         # http://localhost:3000
```

Create an account, upload `data/sample_docs/sample_en.pdf` and ask away.

### 2. Run it for real

You need Python 3.12, Node.js 20.9+ and an [OpenRouter API key](https://openrouter.ai/keys) (or any OpenAI-compatible endpoint).

```bash
cd backend
cp .env.example .env        # set LLM_API_KEY; pick models with LLM_MODEL / LLM_FAST_MODEL
uvicorn --factory app.main:create_app --reload
```

Then start the frontend as above. With no other setup the backend uses SQLite and an embedded Qdrant under `backend/data/`. The first upload downloads the embedding model (about 2 GB) into the local cache.

**OCR (optional but recommended for Indian-language PDFs)**: install Tesseract with the language packs you need.

```bash
sudo apt install tesseract-ocr tesseract-ocr-hin tesseract-ocr-tam tesseract-ocr-tel   # Debian/Ubuntu
brew install tesseract tesseract-lang                                                  # macOS
```

Without it, scanned and broken-font pages are skipped and the document shows a warning.

### 3. Docker Compose (full stack)

```bash
cp backend/.env.example backend/.env   # set LLM_API_KEY and JWT_SECRET (openssl rand -hex 32)
docker compose up --build
```

This starts the UI (port 3000), the API (8000, docs at `/api/docs`), PostgreSQL and a Qdrant server. The backend image includes Tesseract with OCR packs for 11 Indian languages and English. If the UI is served from another host, build it with `PUBLIC_API_URL=https://api.example.com` and set `CORS_ORIGINS` to match.

## Configuration

All settings are environment variables (see [`backend/.env.example`](backend/.env.example)). The important ones:

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_API_KEY` | (none) | Key for the LLM API. Required to answer questions. |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` | Any OpenAI-compatible endpoint. |
| `LLM_MODEL` | `openai/gpt-oss-120b` | Writes answers. |
| `LLM_FAST_MODEL` | `openai/gpt-oss-20b` | Router, Planner, Grader, Validator. |
| `ROUTER_MODEL` … `VALIDATOR_MODEL` | (unset) | Per-agent model overrides. |
| `JWT_SECRET` | dev value | Required (32+ characters) when `ENVIRONMENT=production`. |
| `DATABASE_URL` | SQLite in `data/` | e.g. `postgresql+asyncpg://user:pass@host/db` |
| `QDRANT_URL` | embedded | e.g. `http://localhost:6333` or a Qdrant Cloud URL (+ `QDRANT_API_KEY`). |
| `EMBEDDING_PROVIDER` | `fastembed` | `fastembed` (local) or `openai` (any embeddings API; also set `EMBEDDING_MODEL`, `EMBEDDING_DIM`). |
| `OCR_LANGUAGES` | 11 Indian languages + English | Tesseract languages to use when installed. |
| `MAX_UPLOAD_MB` | `25` | Upload size limit. |

## API

Interactive docs: `http://localhost:8000/api/docs`. All routes except register, login and health need `Authorization: Bearer <token>`.

| Method and path | Purpose |
| --- | --- |
| `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me` | Accounts |
| `POST /api/documents` (multipart `file`) | Upload; processing continues in the background |
| `GET /api/documents`, `GET /api/documents/{id}`, `DELETE /api/documents/{id}` | Library |
| `GET /api/conversations`, `GET`/`PATCH`/`DELETE /api/conversations/{id}` | Saved chats |
| `POST /api/chat` | Ask a question; streams Server-Sent Events |
| `GET /api/health` | Status of the LLM config, vector store and OCR |

`POST /api/chat` takes `{"message": "...", "conversation_id": "optional", "document_ids": ["optional"]}` and streams these events: `start`, `meta` (language, query type), `step` (each agent's progress), `sources`, `token`, `validation`, `error`, `done`. Stopping the request mid-answer saves the partial answer.

## Project structure

```
backend/
  app/
    main.py              app factory and startup
    config.py            settings (environment variables)
    db.py                users, conversations, messages, documents (SQLAlchemy)
    security.py          password hashing, JWT
    api/                 auth, documents, conversations, chat (SSE), health
    agents/
      graph.py           the LangGraph agent pipeline
      prompts.py         every agent's prompt
      llm.py             OpenAI-compatible client (JSON mode, streaming, friendly errors)
    rag/
      extraction.py      PDF/DOCX/TXT/CSV text, garbled-page detection, OCR, header stripping
      chunking.py        Indic-aware chunking
      language.py        script + langdetect language detection
      sparse.py          multilingual BM25 vectors
      embeddings.py      fastembed / API embeddings
      vector_store.py    Qdrant hybrid search
      ingestion.py       background upload pipeline
  scripts/demo_server.py offline demo (no API keys)
  tests/                 66 tests: agents, API, extraction (real sample PDFs), retrieval, LLM client
frontend/
  src/app/               routes: /login, /register, / and /c/[id]
  src/components/        workspace, sidebar, chat view, messages, agent trace, library, composer
  src/lib/               API client, SSE stream reader, auth, theme
data/sample_docs/        an English PDF and a legacy-font Tamil PDF used in tests
docker-compose.yml       UI + API + PostgreSQL + Qdrant
legacy/                  all of version 1, unchanged (FastAPI scaffold + Streamlit demo)
```

## Tests

```bash
cd backend && pytest -q          # runs offline: scripted LLM, toy embedder, in-memory Qdrant
cd frontend && npm run typecheck && npm run build
```

CI runs both on every push and pull request (`.github/workflows/ci.yml`).

## Known limitations

- No database migrations yet: tables are created on startup. Add Alembic before changing the schema of a deployed instance.
- No rate limiting; put the API behind a gateway or add one before exposing it publicly.
- The auth token is kept in the browser's `localStorage`. That's simple and works across origins, but an httpOnly cookie is safer against XSS.
- Language detection can't tell apart languages that share a script and are rare in `langdetect` (e.g. Maithili or Konkani are reported as Hindi). Answers still come back in the script you used.

## Version 1

The first version (January 2026) was a FastAPI scaffold plus a single-file Streamlit demo. Version 2 rebuilds the backend so it runs and is tested, adds real hybrid search, OCR, accounts and saved chats, and replaces Streamlit with the Next.js app. All of version 1 is kept unchanged in [`legacy/`](legacy/), including the Streamlit demo behind the original [live demo](https://multilingualagenticragplatform.streamlit.app/).

## License

MIT, see [LICENSE](LICENSE).

## Author

**Narendran Karthikeyan**: [GitHub](https://github.com/iamnarendran) · [LinkedIn](https://www.linkedin.com/in/narendran-karthikeyan%F0%9F%8C%B3-95862423b)
