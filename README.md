# StudyMate

[![Backend CI](https://github.com/SahilIjaz/studymate/actions/workflows/backend-ci.yml/badge.svg)](https://github.com/SahilIjaz/studymate/actions/workflows/backend-ci.yml) [![Frontend CI](https://github.com/SahilIjaz/studymate/actions/workflows/frontend-ci.yml/badge.svg)](https://github.com/SahilIjaz/studymate/actions/workflows/frontend-ci.yml) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Ask questions about your own PDFs and get answers with page-level citations, streamed token by token.

StudyMate is a retrieval-augmented generation (RAG) app. PDFs are split into page-aware chunks, embedded, indexed in FAISS and BM25, and retrieved with reciprocal rank fusion. The model answers strictly from the retrieved passages and cites them inline, and the web client turns those citations into clickable chips that open the exact passage.

| Part | Stack | Docs |
| --- | --- | --- |
| [`study-mate-backend/`](study-mate-backend/) | FastAPI, FAISS + BM25 hybrid retrieval, SSE streaming, SQLite, Gemini (Claude optional) | [README](study-mate-backend/README.md) |
| [`studyMate-frontend/`](studyMate-frontend/) | Next.js 16, React 19, TypeScript, Tailwind CSS v4, Zustand, Vitest | [README](studyMate-frontend/README.md) |

## Run everything with Docker

```bash
docker compose up --build
# Web: http://localhost:3000   API docs: http://localhost:8000/docs
```

See [docker-compose.yml](docker-compose.yml) for the environment variables each service expects.

## Run the halves separately

```bash
# API
cd study-mate-backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # add your GEMINI_API_KEY
python run.py                   # http://localhost:8000

# Web
cd studyMate-frontend
npm install
cp .env.example .env.local      # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                     # http://localhost:3000
```

## Continuous integration

Each half has its own workflow in [.github/workflows](.github/workflows/), triggered only when files under that folder change: lint, type-check and tests for the frontend; ruff, pytest on Python 3.11 and 3.12, and a Docker build for the backend.

## Author

Sahil Ijaz
