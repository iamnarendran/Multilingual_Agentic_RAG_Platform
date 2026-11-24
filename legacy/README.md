# Legacy: version 1 (January–March 2026)

Everything from the first version of this project, kept unchanged for reference. The current app is in the repository root (see [../README.md](../README.md)).

| Path | What it is |
| --- | --- |
| [`Streamlit/`](Streamlit/) | The single-file Streamlit demo (ChromaDB + OpenRouter) behind the original live demo. This is the only v1 code that runs. |
| [`backend/`](backend/), [`tests/`](tests/) | The v1 FastAPI + LangGraph backend scaffold and its test files. |
| `Dockerfile`, `docker-compose.yml`, `.dockerignore` | v1 container setup. |
| [`README_v1.md`](README_v1.md) | The v1 README. |
| `.env.example` | The v1 `.env` file (it only ever held placeholder values). |
| `data/test_queries.json` | v1 test data file. |

The v1 sample PDFs are still used by v2's tests, so they stay in [`../data/sample_docs/`](../data/sample_docs/).

## Known problems in the v1 backend

These are why v2 is a rewrite rather than a fix. The v1 backend does not start:

- `agents/orchestrator.py`, `api/routes/documents.py` and `core/document_processor.py` have indentation (syntax) errors.
- `core/vector_store` has no `.py` extension, so `from app.core.vector_store import ...` fails.
- `RetrieverAgent` asks for a `"retriever"` model config that `config.py` doesn't define.
- The Dockerfile copies `backend/requirements.txt` (the file is `requirments.txt`) and a `backend/.env` that doesn't exist.
- Hybrid/BM25 search and reranking were placeholders; the test files are empty.

## Running the v1 Streamlit demo

```bash
cd legacy/Streamlit
pip install -r requirements.txt
streamlit run streamlit.py
```

Enter an OpenRouter API key in the sidebar (or set `OPENROUTER_API_KEY` in Streamlit secrets). On Streamlit Community Cloud, the app's main file path is now `legacy/Streamlit/streamlit.py`.
