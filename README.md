# Legal Document Analyzer — AI Legal Document Intelligence

A full-stack, RAG-based (Retrieval-Augmented Generation) legal document intelligence platform. Upload legal documents, ask questions in natural language, and receive precise, source-cited answers powered by AI.

## ✨ Features

- **Multi-Document RAG** — Query across multiple PDF, DOCX, and TXT documents simultaneously
- **Semantic Search** — AI-powered vector similarity search using FAISS
- **Source Citations** — Every answer is grounded with document name, page number, and relevance score
- **Dual LLM Support** — Primary: Groq API (fast cloud inference) / Fallback: Ollama (local/offline)
- **Local Embeddings** — Uses Ollama nomic-embed-text for privacy-preserving local embedding generation
- **Session Memory** — Conversational context persists across questions within a session
- **Document Preview** — View extracted text from uploaded documents
- **Chat Export** — Download conversation history as Markdown
- **Response Modes** — Strict (document-only) or Hybrid (document + general knowledge)

## 🏗 Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Frontend   │────▶│  FastAPI      │────▶│  Groq API       │
│   (SPA)      │◀────│  Backend      │────▶│  (Primary LLM)  │
│              │     │              │     └─────────────────┘
│  HTML/CSS/JS │     │  - Document  │     ┌─────────────────┐
│  Dark Theme  │     │    Routes    │────▶│  Ollama          │
│  Three-Panel │     │  - Query     │     │  (Fallback LLM   │
│              │     │    Routes    │     │   + Embeddings)  │
└─────────────┘     │  - Session   │     └─────────────────┘
                    │    Routes    │
                    │  - Export    │     ┌─────────────────┐
                    │    Routes    │────▶│  FAISS Vector    │
                    │              │     │  Store           │
                    │  - RAG       │     └─────────────────┘
                    │    Engine    │
                    │              │     ┌─────────────────┐
                    └──────────────┘────▶│  SQLite DB       │
                                        │  (Sessions,      │
                                        │   Documents)     │
                                        └─────────────────┘
```

## 📋 Prerequisites

- **Python 3.10+**
- **Groq API Key** (required for LLM) — Get one free at [console.groq.com](https://console.groq.com)
- **Ollama** (required for embeddings) — Install from [ollama.ai](https://ollama.ai)

## 🚀 Installation & Setup

### 1. Clone the repository

```bash
cd "Legal Document Analyzer"
```

### 2. Create a virtual environment

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

Edit the `.env` file with your API key:

```env
# Required
GROQ_API_KEY=your_groq_api_key_here

# Optional — only needed if using Ollama as fallback
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text
FALLBACK_LLM_MODEL=llama3.2

# Groq LLM Model
LLM_MODEL=llama-3.1-70b-versatile
```

### 5. Setup Ollama for embeddings

```bash
# Install Ollama from https://ollama.ai
ollama serve
ollama pull nomic-embed-text    # Embedding model
ollama pull llama3.2            # Optional fallback LLM model
```

### 6. Run the application

```bash
python app.py
```

Open **http://localhost:8000** in your browser.

## 📖 Usage Guide

1. **Upload Documents** — Click the documents panel (right sidebar) and drag & drop or browse for PDF, DOCX, or TXT files
2. **Wait for Processing** — Documents are extracted, chunked, embedded, and indexed automatically
3. **Ask Questions** — Type your question in the chat input and press Enter
4. **Review Sources** — Each AI answer includes source citations with document name and page number
5. **Filter Documents** — Use the filter chips above the input to restrict queries to specific documents
6. **Export Conversations** — Click the download icon in the chat header to export as Markdown
7. **Switch Modes** — Toggle between Strict (document-only) and Hybrid (document + general knowledge) modes

## 📁 Project Structure

```
Legal Document Analyzer/
├── app.py                          # FastAPI entry point
├── config.py                       # Centralized configuration
├── requirements.txt                # Python dependencies
├── .env                            # Environment variables (API keys)
├── templates/
│   └── index.html                  # SPA frontend
├── static/
│   ├── css/style.css               # Premium dark theme (1500+ lines)
│   └── js/
│       ├── app.js                  # Global state, health checks, UI
│       ├── chat.js                 # Chat rendering, markdown, typing
│       ├── sessions.js             # Session CRUD, export
│       └── documents.js            # Upload, listing, preview, deletion
├── backend/
│   ├── models/
│   │   └── database.py             # SQLite schema & CRUD operations
│   ├── routes/
│   │   ├── document_routes.py      # Document upload, list, delete, preview
│   │   ├── query_routes.py         # RAG queries & health checks
│   │   ├── session_routes.py       # Session management
│   │   └── export_routes.py        # Chat export as Markdown
│   ├── services/
│   │   ├── document_processor.py   # PDF/DOCX/TXT text extraction
│   │   ├── embedding_service.py    # Groq + Ollama embeddings
│   │   ├── llm_service.py          # Groq + Ollama LLM inference
│   │   ├── rag_engine.py           # Full RAG pipeline orchestration
│   │   ├── session_manager.py      # Session & message management
│   │   └── vector_store.py         # FAISS vector storage & retrieval
│   └── utils/
│       └── helpers.py              # ID generation, sanitization
├── uploads/                        # Uploaded document files
├── vector_db/                      # FAISS index persistence
└── data/                           # SQLite database
```

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/documents/upload` | Upload one or more documents |
| `GET` | `/api/documents` | List all documents |
| `GET` | `/api/documents/stats` | Get document & vector statistics |
| `GET` | `/api/documents/{id}` | Get document details |
| `GET` | `/api/documents/{id}/preview` | Preview extracted text |
| `DELETE` | `/api/documents/{id}` | Delete a document |
| `POST` | `/api/query` | Submit a RAG query |
| `GET` | `/api/health` | System health check |
| `POST` | `/api/sessions` | Create a new session |
| `GET` | `/api/sessions` | List all sessions |
| `GET` | `/api/sessions/{id}` | Get session with messages |
| `DELETE` | `/api/sessions/{id}` | Delete a session |
| `GET` | `/api/sessions/{id}/export` | Export session as Markdown |

## ⚙️ Configuration

All settings are managed via `.env` and `config.py`:

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | (required) | Your Groq API key |
| `LLM_MODEL` | `llama-3.1-70b-versatile` | Groq LLM model name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Ollama embedding model |
| `FALLBACK_LLM_MODEL` | `llama3.2` | Ollama fallback LLM model |
| `UPLOAD_DIR` | `uploads` | Directory for uploaded files |
| `VECTOR_DB_DIR` | `vector_db` | FAISS index storage directory |
| `SQLITE_DB_PATH` | `data/legal_docs.db` | SQLite database path |
| `CORS_ORIGINS` | localhost only | Comma-separated allowed CORS origins (`*` disables credentials) |
| `API_AUTH_KEY` | (empty/disabled) | When set, API routes require the `X-API-Key` header |
| `MAX_UPLOAD_SIZE_MB` | `50` | Maximum size per uploaded file in MB |
| `MAX_FILES_PER_UPLOAD` | `10` | Maximum files accepted in a single upload request |

> When `API_AUTH_KEY` is set, browser clients can store the key via `localStorage.setItem('apiAuthKey', '<key>')`; the SPA sends it automatically. Direct API clients should send `X-API-Key: <key>`.

## 🛡 Tech Stack

- **Backend**: FastAPI, Python 3.10+
- **Frontend**: Vanilla HTML/CSS/JS (SPA, dark theme)
- **Vector DB**: FAISS (Facebook AI Similarity Search)
- **LLM**: Groq API (primary) + Ollama (optional fallback)
- **Embeddings**: Ollama nomic-embed-text (local, privacy-preserving)
- **Database**: SQLite with WAL mode
- **Document Processing**: PyMuPDF, python-docx, LangChain text splitters

## 📄 License

This project is for educational and research purposes.
