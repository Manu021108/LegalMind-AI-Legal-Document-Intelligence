# Potential Issues — Legal Document Analyzer

Review date: 2026-11-02

Severity legend: **CRITICAL** / **HIGH** / **MEDIUM** / **LOW**

---

## Security

### 1. GROQ API key committed in `.env` — CRITICAL (RESOLVED)
The real `GROQ_API_KEY` was present in `.env`. The value has been replaced with the placeholder `your_groq_api_key_here`, and no other copy exists in the project.

Remaining manual step: the old key was exposed/valid, so **rotate it** at https://console.groq.com and put the new value in `.env`. The project is not a git repository, so no history purge is required.

### 2. CORS wildcard with credentials — HIGH (RESOLVED)
CORS now uses `CORS_ORIGINS` from config. Wildcard origins disable credentials and restrict methods/headers; explicit origins keep credentials enabled. Default allows only localhost.

### 3. Optional auth can be bypassed — HIGH (RESOLVED)
- Explicit public paths only: `/`, `/api/health`, `/openapi.json`, `/favicon.ico`, plus `/static`, `/docs`, `/redoc` prefixes.
- CORS preflight (`OPTIONS`) is exempt so browsers can negotiate headers.
- Key comparison uses `secrets.compare_digest` (constant time).
- The frontend now sends `X-API-Key` from `localStorage("apiAuthKey")` and reports 401s clearly.

### 4. No upload size or content limits — HIGH (RESOLVED)
- Uploads are streamed to disk in 1 MB chunks and aborted once `MAX_UPLOAD_SIZE_MB` (default 50) is exceeded.
- `MAX_FILES_PER_UPLOAD` (default 10) caps batch size.
- Content is validated against the declared extension: PDF magic bytes, DOCX zip structure, and TXT binary/null-byte checks.
- Rejected/partial files are removed from disk.
- Note: processing still runs inside the request; a background queue remains a future improvement.

### 5. Internal error details leaked to clients — MEDIUM (RESOLVED)
Upload, query, and preview failures now return generic client-safe messages, while full details are written to the server log. Upload validation errors still return their safe, user-facing reason (e.g., "File does not appear to be a valid PDF.").

### 6. Dynamic SQL column interpolation — MEDIUM (RESOLVED)
`update_document` now validates every key against `UPDATABLE_DOCUMENT_COLUMNS` and raises `ValueError` for anything else before executing SQL.

### 7. File deletion based on stored DB path — MEDIUM (RESOLVED)
Delete and preview endpoints now verify the stored path resolves inside `UPLOAD_DIR` via `is_path_within()` and refuse otherwise.

---

## Backend / Logic

### 8. Blocking synchronous calls inside async routes — HIGH
- `llm_service.py:106-112` constructs the sync `Groq` client and calls `chat.completions.create` inside an `async` function, blocking the event loop.
- `llm_service.py:171-172` `client.models.list()` is also blocking.
- File I/O in `document_routes.py` is synchronous.
Wrap in `run_in_threadpool`/`asyncio.to_thread` or use an async client.

### 9. Not thread/process safe — MEDIUM
`backend/services/vector_store.py` uses module-level globals (`_index`, `_metadata`, `_documents`, `_ids`, `_dimension`). Concurrent uploads/queries/deletes can corrupt state. Multiple uvicorn workers each hold a separate copy and overwrite the same files.

### 10. Vector store dimension change silently discards data — MEDIUM
`vector_store.py:81-87` `_ensure_index()` replaces the index whenever the embedding dimension differs, orphaning previously stored chunks while old metadata remains in the JSON. Example: switching embedding models mixes incompatible vectors.

### 11. Inefficient delete / possible failure — MEDIUM
`vector_store.py:206-218` reconstructs every kept vector (`_index.reconstruct(i)`) and rebuilds the index on each delete. Slow for large stores. Also if `_dimension` is `None` and the last doc is deleted, `_index` becomes `None` while metadata handling is inconsistent.

### 12. Orphaned/orphan upload files — LOW
`document_routes.py:74-85` marks a document as `error` when no text is extracted but leaves the file on disk and the DB row behind. No cleanup job exists for stale `processing`/`error` rows.

### 13. Sequential batch embedding — MEDIUM
`embedding_service.py:104-129` embeds chunks one at a time. Large documents (hundreds of chunks) upload very slowly. Consider concurrency or a batch endpoint.

### 14. Ollama embeddings API compatibility — MEDIUM
`embedding_service.py:73-77` posts to `/api/embeddings` with `"prompt"` (legacy). Newer Ollama versions favor `/api/embed` with `"input"`. Could break after Ollama upgrades.

### 15. History retrieval inconsistency — LOW
`session_manager.py:58-69` requests `limit=100` from the DB then slices the last `MAX_HISTORY_MESSAGES`; `get_session_messages` itself defaults to 50. Multiple limits are confusing and can silently drop history.

### 16. No-result path skips auto-title — LOW
`rag_engine.py:51-62` saves messages when retrieval is empty but does not call `auto_title_session`, unlike the normal path. First-question sessions can stay titled "New Chat".

### 17. Deprecated UTC usage — LOW
`helpers.py:16-18` and `database.py:155` use `datetime.utcnow()`, deprecated in Python 3.12+. Use `datetime.now(timezone.utc)`.

### 18. Provider health check does a real API call — LOW
`llm_service.py:166-175` calls `client.models.list()` on every health poll `app.js` runs every 30s. Adds latency/quota use; cache the result.

### 19. `on_event` startup deprecated — LOW
`app.py:98` uses `@app.on_event("startup")`, deprecated in favor of lifespan handlers.

### 20. Duplicate rate limiter instances — LOW
`app.py:35` and `query_routes.py:22` each create a separate `Limiter`. The route-level limiter is attached through `app.state.limiter`, but the duplication is error-prone and only `/api/query` is limited.

### 21. Only query endpoint rate limited — MEDIUM
Upload, delete, export, and session endpoints have no limits; `/api/query` relies on `get_remote_address`, which is spoofable behind an untrusted proxy.

### 22. DOCX page metadata lost — LOW
`document_processor.py:63-88` treats every DOCX as a single page; citations will always show "Page 1".

### 23. Page mapping heuristic is unreliable — LOW
`document_processor.py:144-164` maps chunks to pages via first-100-char match or word-set overlap, which can misattribute pages for repeated/similar text.

### 24. Port/host messages hardcoded — LOW
`app.py:106` logs `http://localhost:8000/docs` regardless of the actual bind host/port.

---

## Frontend

### 25. No API key support in client — HIGH (if auth enabled)
`static/js/app.js:19-39` `apiRequest()` never adds `X-API-Key`. Enabling `API_AUTH_KEY` breaks every UI request. Export uses raw `fetch` too (`sessions.js:134`).

### 26. Health polling every 30s — LOW
`app.js:215` polls `/api/health` continuously, which triggers provider API calls (see issue 18).

### 27. Inline event handlers — LOW
`documents.js` and `sessions.js` embed IDs/names directly in `onclick` strings. IDs are UUIDs (safe), but `escapeHtml` does not escape quotes for the JS context, so a crafted document name could break out of the attribute.

### 28. Timestamp parsing assumes UTC suffix — LOW
`documents.js:55` and `sessions.js:192` append `'Z'` to timestamps. Works only because `get_timestamp()` is naive UTC; breaks if the backend later returns timezone-aware strings.

---

## Configuration / Deployment

### 29. Docker health check downloads/executes inline Python — LOW
`Dockerfile:24-25` uses an inline `python -c` with `httpx`. Fine but brittle; a dedicated health script is cleaner.

### 30. `depends_on` does not wait for readiness — MEDIUM
`docker-compose.yml:14-15` starts the app before Ollama is ready; first uploads/queries fail until models are pulled. Add a healthcheck on the Ollama service and `condition: service_healthy`.

### 31. Ollama models not pulled automatically — MEDIUM
`docker-compose.yml:25-27` comments instruct manual `ollama pull`. A fresh `docker compose up` yields a degraded app.

### 32. Deprecated Compose version key — LOW
`docker-compose.yml:1` `version: "3.8"` is obsolete.

### 33. Runtime side effects in config import — LOW
`config.py:43-46` creates directories at import time. Harmless but makes the module non-pure and can fail in read-only containers.

### 34. Persistent artifacts in working tree — LOW (RESOLVED)
Unused `chroma_db/` has been removed. Runtime artifacts remain gitignored and are expected in local/dev environments.

---

## Tests

### 35. Test path bootstrap bug — MEDIUM
`tests/test_api_routes.py:13` inserts `Path(__file__).parent` (the `tests/` dir) instead of the project root (`parent.parent`). It only works because pytest runs from the project root.

### 36. Fragile global-state reset — MEDIUM
`tests/test_vector_store.py:17-28` monkeypatches module globals directly. Tests are not safe under `pytest-xdist` parallel execution.

### 37. Missing coverage — LOW
No tests for: auth middleware, upload validation/limits, export content, error paths, or provider fallback logic.

### 38. Tests hit live services — LOW
`test_api_routes.py:30` `/api/health` and any query tests depend on running Ollama/Groq, making CI non-deterministic.

---

## Naming / Consistency

### 39. Mixed product naming — LOW
UI, README, and export text use "LegalMind" while the app title is "Legal Document Analyzer" (`export_routes.py:29`, `app.js:203`).

### 40. Multi-worker deployment unsafe — HIGH
See issue 9: running `uvicorn --workers N` or multiple replicas corrupts the shared FAISS/JSON state. The app is effectively single-process only, which the README/Dockerfile do not document.

---

## Recommended Priority Order

1. Rotate and remove the Groq key from `.env` and git history.
2. Fix CORS config and make authentication coherent (client header support).
3. Add upload size limits and content validation.
4. Move blocking Groq/file operations off the event loop.
5. Guard FAISS global state or document single-worker constraint.
6. Add rate limiting to write endpoints.
7. Fix test bootstrap and add missing coverage.
