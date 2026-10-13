# StudyMate API

Ask questions about your own PDFs and get answers with page-level citations, streamed token by token from Gemini or Claude.

StudyMate is a retrieval-augmented generation (RAG) service built with FastAPI. Documents are split into page-aware chunks, embedded locally, indexed in FAISS and BM25, and retrieved with reciprocal rank fusion. Claude answers strictly from the retrieved passages and cites them inline. Every workspace is isolated, every artefact is persisted, and the whole thing runs on a single small container.

Frontend: [studyMate-frontend](../studyMate-frontend/) (Next.js).

## What it does

- **Upload PDFs** (up to 20 MB, 300 pages). Text is extracted per page, cleaned, chunked by sentence with overlap, and embedded (Gemini's free embedding API by default, or a local ONNX model), so every chunk knows which pages it came from.
- **Hybrid retrieval.** Dense vectors (FAISS, cosine) catch paraphrases; BM25 catches exact terms and identifiers. Results are fused with reciprocal rank fusion and weak tails are cut, so an off-topic question yields no sources instead of five bad ones.
- **Grounded, cited answers.** The model (Gemini by default, Claude optional) is given numbered sources and instructed to cite them as `[1]`, `[2]`. The API returns the cited passages with filename and page range so the UI can show exactly where an answer came from.
- **Streaming.** Answers arrive over Server-Sent Events: sources first, then text deltas, then usage.
- **Conversations with memory.** Follow-ups ("explain that more simply") are rewritten into standalone search queries by a small model before retrieval, and the last few turns are sent to Claude.
- **Whole-document questions.** "Summarize this" is detected and answered from the leading chunks of every document instead of similarity search.
- **Workspace isolation.** Every request carries an opaque workspace id. Documents, indexes and conversations never cross workspaces.
- **Persistence.** SQLite for metadata and chunks, FAISS index files per workspace, uploads on disk. A restart loses nothing.
- **Operational hygiene.** Pinned dependencies, structured JSON logs with request ids, typed error responses, per-workspace rate limits, upload sniffing and size caps, health and readiness probes, Docker image, CI.

## Architecture

```
POST /documents                         POST /chat/stream
      │                                        │
      ▼                                        ▼
 sniff + size cap               rewrite follow-up (Claude Haiku)
 sha256 dedupe                                 │
 store PDF                                     ▼
      │                            ┌─ dense  (FAISS, cosine) ─┐
      ▼  (background)              │                          ├─ RRF fusion ─ cutoff ─ top-k
 pdfplumber per page               └─ sparse (BM25+)  ────────┘
 clean + sentence chunking                     │
 embed (Gemini / fastembed)                    ▼
 SQLite chunks + FAISS add         system prompt (cached) + numbered <sources> + history
                                               │
                                               ▼
                                   Claude (streamed) ──► SSE: meta, sources, delta…, done
                                               │
                                               ▼
                                   persist user + assistant messages with citations
```

```
app/
├── main.py              app factory, middleware (request id, CORS, optional API key), lifespan
├── config.py            pydantic-settings; every tunable is an env var
├── errors.py            typed errors → {"error": {code, message, request_id}}
├── logging_config.py    JSON logs with a request-id contextvar
├── schemas.py           public request/response models
├── api/
│   ├── deps.py          service container, workspace header, rate limiting
│   └── routes/          health, documents, chat (SSE)
├── core/                filename sanitising + PDF sniffing, token-bucket limiter, ids
├── services/
│   ├── pdf.py           per-page extraction and text repair
│   ├── chunking.py      sentence-aware chunks with overlap and page ranges
│   ├── embeddings.py    Embedder protocol: fastembed (local ONNX), Voyage, hashed
│   ├── index.py         per-workspace FAISS + BM25 index, persisted, idempotent adds
│   ├── retrieval.py     hybrid search, RRF, relative cutoff, overview mode
│   ├── prompts.py       system prompt and source formatting
│   ├── llm.py           LLM interface, Claude provider, dev mock
│   ├── gemini.py        Gemini provider with overload fallback
│   └── ingestion.py     accept → background index → delete
└── storage/db.py        SQLite repository (WAL, per-thread connections)
```

## Running locally

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # add your GEMINI_API_KEY (or ANTHROPIC_API_KEY)
python run.py                   # http://127.0.0.1:8000, docs at /docs
```

With a Gemini key, embeddings come from Gemini's API and nothing is downloaded. Set `EMBEDDING_PROVIDER=fastembed` to embed locally instead (the first request downloads a ~130 MB model into `DATA_DIR/models`), or `hashed` for a dependency-free run (lexical matching only).

No API key yet? Set `LLM_MOCK=true` and the service streams canned answers built from the retrieved passages, so the whole upload → retrieve → cite → stream path (and the frontend) can be exercised without spending credits. The mock is ignored whenever a real key is present.

With Docker:

```bash
docker build -t studymate-api .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... -v studymate-data:/data studymate-api
```

The image pre-downloads the embedding model so cold starts don't touch the network.

## API

All routes except `/health*` need an `X-Workspace-Id: <uuid>` header. The client mints the id and keeps it; it scopes every document and conversation.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Version, model, embedding provider, uptime |
| `GET` | `/health/ready` | Database reachable |
| `GET` | `/documents` | List documents in the workspace |
| `POST` | `/documents` | Upload a PDF (multipart `file`). Returns `202` with `status: processing` |
| `GET` | `/documents/{id}` | Poll status: `processing` → `ready` or `failed` (with reason) |
| `DELETE` | `/documents/{id}` | Remove the document, its chunks and its vectors |
| `GET` | `/documents/{id}/suggestions` | Four study questions generated from the opening pages |
| `GET` | `/conversations` | List conversations |
| `POST` | `/conversations` | Create one (optional `title`) |
| `GET` | `/conversations/{id}` | Conversation with messages, citations and usage |
| `DELETE` | `/conversations/{id}` | Delete it |
| `POST` | `/chat/stream` | Ask a question, answer streamed as SSE |
| `POST` | `/chat/ask` | Same pipeline, single JSON response |

### Asking a question

```json
POST /chat/stream
{ "question": "What happens during metaphase?", "conversation_id": "conv_…", "document_ids": ["doc_…"] }
```

`conversation_id` and `document_ids` are optional. Without a conversation id a new one is created and its id is sent in the first event. With `document_ids` retrieval is scoped to those files.

Event stream:

```
event: meta      data: {"conversation_id":"conv_…","user_message_id":"msg_…"}
event: status    data: {"stage":"retrieving"}
event: sources   data: {"sources":[{"n":1,"filename":"biology.pdf","page_start":3,"page_end":3,"score":1.0,"text":"…"}],"retrieval_query":"…"}
event: status    data: {"stage":"thinking"}
event: delta     data: {"text":"During **metaphase** the chromosomes align"}
event: delta     data: {"text":" along the equatorial plate [1]."}
event: done      data: {"message_id":"msg_…","usage":{"input_tokens":1840,"output_tokens":96,"cache_read_input_tokens":512},"model":"claude-opus-5-5"}
```

An `error` event replaces `done` when something fails mid-stream, with the same `{code, message}` shape as HTTP errors.

### Errors

```json
{ "error": { "code": "rate_limited", "message": "Too many questions. Try again in 4s.", "request_id": "3f9c…", "details": { "retry_after_seconds": 4 } } }
```

Codes you can branch on: `workspace_required`, `unsupported_file_type`, `invalid_pdf`, `payload_too_large`, `too_many_pages`, `no_text_layer`, `workspace_full`, `document_not_found`, `document_not_ready`, `conversation_not_found`, `rate_limited`, `llm_rate_limited`, `llm_not_configured`, `llm_model_unavailable`, `llm_refused`, `llm_timeout`, `llm_unreachable`.

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `auto` | `gemini`, `claude` or `mock`. `auto` picks Gemini when `GEMINI_API_KEY` is set, else Claude. |
| `GEMINI_API_KEY` | – | Free at aistudio.google.com/apikey. |
| `GEMINI_MODEL` / `GEMINI_FALLBACK_MODEL` / `GEMINI_FAST_MODEL` | `gemini-3.5-flash` / `gemini-flash-lite-latest` / `gemini-flash-lite-latest` | Answers / retry target when the primary is overloaded / side tasks. |
| `GEMINI_THINKING_LEVEL` | `low` | Thinking depth on Gemini 3.x. `low` keeps the first token under ~2 s; empty uses the model default. |
| `ANTHROPIC_API_KEY` | – | Needed only for the Claude provider. Without any key, uploads and retrieval still work. |
| `CLAUDE_MODEL` | `claude-opus-5-5` | Answering model. |
| `CLAUDE_FAST_MODEL` | `claude-haiku-5-5` | Query rewriting and question suggestions. |
| `CLAUDE_EFFORT` | `medium` | `low` … `max`; thinking depth. |
| `CLAUDE_MAX_TOKENS` | `8192` | Answer length cap (streaming, so timeouts aren't a concern). |
| `CLAUDE_SERVER_FALLBACKS` | `true` | Server-side refusal fallback (beta). Auto-disables if the org lacks it. |
| `EMBEDDING_PROVIDER` | `auto` | `gemini`, `fastembed`, `voyage`, `hashed`. `auto` = Voyage if keyed, else Gemini if keyed, else local fastembed. |
| `GEMINI_EMBEDDING_MODEL` / `GEMINI_EMBEDDING_DIM` | `gemini-embedding-001` / `768` | Gemini embeddings (free tier, no model download). |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Any fastembed model; dimension is read from its metadata. |
| `EMBEDDING_CACHE_DIR` | `DATA_DIR/models` | Where the model files are kept. |
| `VOYAGE_API_KEY` / `VOYAGE_MODEL` | – / `voyage-3.5-lite` | Hosted embeddings. |
| `CHUNK_SIZE_WORDS` / `CHUNK_OVERLAP_WORDS` | `300` / `60` | Chunking budget. |
| `TOP_K` / `CANDIDATE_POOL` | `6` / `24` | Sources sent to Claude / candidates per retriever. |
| `MIN_RELATIVE_SCORE` | `0.35` | Drop hits scoring below this fraction of the best. |
| `MIN_DENSE_SIMILARITY` | `0.25` | Cosine floor for dense hits. |
| `HISTORY_TURNS` | `6` | Prior turns sent to Claude. |
| `QUERY_REWRITE` | `true` | Rewrite follow-ups before retrieval. |
| `MAX_UPLOAD_MB` / `MAX_PAGES` / `MAX_DOCS_PER_WORKSPACE` | `20` / `300` / `20` | Limits. |
| `RATE_LIMIT_ASK_PER_MINUTE` / `RATE_LIMIT_UPLOAD_PER_MINUTE` | `12` / `6` | Per workspace + IP. |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated. |
| `APP_API_KEY` | – | When set, every non-health request needs `X-API-Key`. |
| `DATA_DIR` | `data` | SQLite, uploads, indexes. Mount a volume in production. |

Changing the embedding provider or model is safe: each workspace index records what built it and is rebuilt from the stored chunks on first load if it no longer matches.

## Tests

```bash
EMBEDDING_PROVIDER=hashed pytest -q      # 44 tests, ~2 s
ruff check . && ruff format --check .
```

The suite covers chunking and text repair, filename sanitising and upload sniffing, the rate limiter, hybrid retrieval (scoping, cutoffs, persistence, deletion, provider change), and the HTTP API end to end with a fake Claude: upload → background index → stream events in order → persisted citations, follow-ups with history, overview questions, workspace isolation, 429s and the API-key gate. PDFs for the tests are generated in-process, so no fixtures are checked in.

## Deployment

### Kubernetes

Manifests live in [deploy/k8s](deploy/k8s) (`base/` plus a production overlay): a namespace, a ConfigMap for non-secret settings, a Secret template for API keys, a 2 Gi PersistentVolumeClaim for `/data`, a single-replica Deployment (`Recreate` strategy, because SQLite and the FAISS files sit on one ReadWriteOnce volume), a ClusterIP Service, and an optional nginx Ingress with proxy buffering off so streamed answers aren't batched.

```bash
# 1. Build the image (and push it, unless the cluster can see your local Docker images)
docker build -t studymate-api:latest .

# 2. Create the secret once; it is never written to the repo
kubectl create namespace studymate
kubectl -n studymate create secret generic studymate-api-secrets --from-literal=GEMINI_API_KEY='your-key'

# 3. Apply everything else
kubectl apply -k deploy/k8s

# 4. Check and try it
kubectl -n studymate rollout status deploy/studymate-api
kubectl -n studymate port-forward svc/studymate-api 8000:80
curl http://127.0.0.1:8000/health
```

#### Production: Vercel frontend + k3s backend on a free Oracle VM

The production overlay in `deploy/k8s/overlays/production` adds what a public deployment needs: the GHCR image built by CI for amd64 and arm64, a Traefik Ingress for `study-mate-ai.duckdns.org`, a cert-manager ClusterIssuer for Let's Encrypt, a CronJob that keeps DuckDNS pointed at the VM, and `CORS_ORIGINS` set to the Vercel site.

On a fresh Ubuntu VM (Oracle Cloud Always Free Ampere works; open ports 80 and 443 in the VCN security list first):

```bash
export GEMINI_API_KEY=...  DUCKDNS_TOKEN=...
curl -fsSL https://raw.githubusercontent.com/SahilIjaz/studymate/main/study-mate-backend/deploy/k3s/bootstrap.sh | bash
```

The script installs k3s and cert-manager, creates the secrets, updates DuckDNS, applies the overlay and waits for the certificate. The image comes from `ghcr.io/sahilijaz/studymate-api`, pushed by the `Backend image` workflow on every push to `main`; make that package public once under GitHub → Packages → studymate-api → Package settings, or the node can't pull it. Re-run it after changing manifests. Then on Vercel, import the repo with root directory `studyMate-frontend` and set `NEXT_PUBLIC_API_URL=https://study-mate-ai.duckdns.org`.

Edit `deploy/k8s/base/configmap.yaml` for `CORS_ORIGINS` and model names, and `deploy/k8s/kustomization.yaml` to point `images:` at your registry tag. For a remote registry, `docker tag studymate-api:latest ghcr.io/<you>/studymate-api:<tag> && docker push ...` and set `newName`/`newTag` accordingly.

### Hugging Face Spaces (no card, no custom domain)

`deploy/huggingface/` holds a Space that wraps the GHCR image. Create a Docker Space, upload those two files (or set the `HF_TOKEN` secret and `HF_SPACE` variable on the GitHub repo so the `Backend Space` workflow pushes them after every image build), then add `GEMINI_API_KEY` as a secret and `LLM_PROVIDER`, `EMBEDDING_PROVIDER`, `CORS_ORIGINS` as variables in the Space settings. The API is served at `https://<user>-<space>.hf.space`. Free Spaces have no persistent disk and sleep after about two days idle.

### Render

`render.yaml` describes a Docker web service with a 1 GB persistent disk mounted at `/data`. Set `ANTHROPIC_API_KEY` in the dashboard and `CORS_ORIGINS` to the frontend origin. Any container host works the same way: one container, one volume, the env vars above.

For more than one replica, swap the in-process limiter and index cache for Redis-backed ones and move the vectors to pgvector or Qdrant; the `Embedder`, `WorkspaceIndex` and `Database` boundaries are the seams.

## Design notes

- **Why hybrid retrieval.** Small embedding models blur rare tokens (course codes, formula names, proper nouns). BM25 nails those; dense vectors cover wording differences. RRF merges the two without having to calibrate their score scales.
- **Why a relative cutoff.** Absolute similarity thresholds don't transfer across embedding models. Cutting relative to the best hit works for all three providers and makes "I couldn't find that" an honest, cheap answer with no LLM call.
- **Why SQLite + FAISS files.** Study notes are small. One file per concern, zero infrastructure, and a restart or redeploy keeps everything. The repository layer is the only thing to rewrite for Postgres.
- **Why background indexing.** Embedding a 200-page PDF takes seconds. The upload returns immediately with `processing`, the UI polls, and the event loop is never blocked: parsing, embedding and FAISS calls all run in worker threads.
- **Prompt safety.** Document text is wrapped in `<source>` tags and the system prompt treats it as data. Our own delimiter tags inside PDF text are neutralised before they reach the prompt.
- **Query rewriting.** A follow-up like "and the second phase?" has nothing to embed. A small model rewrites it into a standalone query first; if that call fails, the raw question is used so retrieval never depends on it.

## Roadmap

- OCR fallback (Tesseract) for scanned PDFs, currently rejected with a clear message.
- Cross-encoder reranking of the fused candidates.
- Real authentication (OIDC) so workspaces map to accounts instead of client-held ids.
- Streaming upload progress over the same SSE channel.

## Author

Sahil Ijaz
