# KANser — Multimodal Lung Cancer Agentic AI Diagnosis

Tumor-board command center: ingest clinical documents and DICOM, get a deterministic
System-1 clinical read (pathway, risk, readiness gates, TNM, contradictions), then run a
LangGraph agent swarm (radiology / pathology / genomics / clinical) that debates, verifies
RAG citations, fuses a calibrated confidence — or **abstains** when the evidence does not
support a claim — and explains the result to clinician and patient separately.

> Research/prototyping software. Not a medical device; not for clinical use.

## Stack

| Layer    | Tech |
|----------|------|
| API      | FastAPI + Pydantic, JWT (HS256), asyncpg |
| Agents   | LangGraph state graph; Groq / Gemini / offline `LocalLLM` fallback |
| Storage  | PostgreSQL 17 (auto-migrated tables), in-memory repo when `DATABASE_URL` is unset |
| Retrieval| Chroma + BM25 hybrid search, hashed embeddings (no model download) |
| Safety   | Presidio PII scrubbing, prompt-injection wrapping, claim gating, audit JSONL |
| Frontend | Next.js 16 (App Router), React 19, Tailwind 4, WebSocket streaming |

## Run

```bash
# 1. Database
docker compose up -d postgres

# 2. Backend  (http://localhost:8000)
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows; source .venv/bin/activate elsewhere
pip install -e ".[dev]"
uvicorn app.main:app --reload

# 3. Frontend (http://localhost:3000)
cd frontend
npm install
npm run dev
```

Full stack: `docker compose up --build` (postgres 5433, api 8000, web 3000).

## Configuration

Copy `.env.example` to `.env` (never commit `.env`).

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Postgres DSN; unset = in-memory repo (dev only) |
| `JWT_SECRET` | 32+ bytes; app refuses known/default secrets at startup |
| `AES_KEY` | Encryption key for stored secrets |
| `GROQ_API_KEY` / `GEMINI_API_KEY` | LLM providers; unset = offline `LocalLLM` fallback |
| `SYSTEM1_PROVIDER` | Deterministic routing provider selection |
| `CORS_ORIGINS` | Comma-separated, default `http://localhost:3000` |
| `ADMIN_USER` / `ADMIN_PASSWORD` | Login credentials (defaults `admin` / `admin` — change) |
| `DISABLE_AUTH=1` | Dev/test only: disables auth entirely |
| `CHROMA_PATH` | Vector store path (default `data/chroma`) |
| `UPLOAD_DIR` / `UPLOAD_MAX_BYTES` | Upload target (default `data/uploads`) and 50 MB cap |
| `AUDIT_LOG` | Audit trail path (default `data/audit/audit.jsonl`) |

## Verify

```bash
cd backend && ruff check . && pytest        # lint + 245 tests
cd frontend && npm run lint && npm run test && npm run build
```

Current status: backend 243 passed / 2 skipped (2 gated: live Postgres, vision E2E),
ruff clean; frontend 6 tests, eslint clean, `next build` clean.

## Repository layout

```
backend/app/     FastAPI app: api, auth, swarm (LangGraph), system1, rag,
                 readiness, tnm, abstention, findings, imaging, chat, pii, vision
backend/tests/   pytest suite (hermetic: auth off, LLM isolated, memory repo)
frontend/src/    app routes (cases, runs, swarm, tumor-board, evidence, longitudinal,
                 alerts, admin) + components (assessment, chat, timeline, findings)
docker-compose.yml  postgres / api / web
stitch/          exported design screens (HTML + preview PNGs)
```

## Documentation

Architecture, roadmap and checklists live in `BLUEPRINT.md`, `WALKTHROUGH.md`,
`project.md`, `new.md`, `knowledge.md` and `docs/` (clinical gap register, safety and
hallucination audits, workflow matrix). They are context, not source of truth — the code is.
