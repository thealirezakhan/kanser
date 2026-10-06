# Multimodal Lung Cancer Agentic AI — Master Execution Blueprint

Production-grade, low-latency, highly secure full-stack platform. No Streamlit.
Stack: FastAPI + LangGraph + Laya/Jev (System 1) + Groq/Gemini (System 2) + Next.js 15 + ChromaDB/LanceDB + BiomedCLIP + Presidio.

**How to use this file:** Work top-down through Section 3 phases. Tick Section 4 boxes as you go. A phase is done only when its exit criteria pass.

---

## Section 1: Decoupled System Architecture Topology

### 1.1 Topology

```
┌─────────────────────────────────────────────────────────────────────────┐
│ BROWSER — Next.js 15 (App Router, TS, Tailwind, shadcn/ui)             │
│  SSR pages · Server Actions · WebSocket client · DICOM viewer          │
└───────────────┬───────────────────────────────┬─────────────────────────┘
                │ HTTPS/TLS 1.3 (REST)         │ WSS (agent step stream)
                ▼                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ FASTAPI CORE ROUTER (async, stateless workers — uvicorn + workers=N)    │
│                                                                         │
│  Middleware chain (order enforced):                                     │
│   1. TLS terminator (reverse proxy: Caddy/nginx, TLS 1.3 only)          │
│   2. CORS (explicit allowlist)                                          │
│   3. Rate limiter (slowapi: 60 req/min global, 5/min diagnose)          │
│   4. Auth (JWT bearer, RBAC: clinician / admin / service)               │
│   5. PII GUARD — Microsoft Presidio (zero-trust: blocks any outbound    │
│      payload to external LLM that still contains PHI)                   │
│   6. Integrity — SHA-256 hash of every uploaded DICOM/pathology/lab     │
│      file, verified on write, recorded in audit log                     │
│   7. Audit Logger — append-only, hash-chained immutable log             │
│                                                                         │
│  REST:  /api/health  /api/cases  /api/cases/{id}/diagnose               │
│         /api/documents/ingest  /api/runs/{id}  /api/evidence            │
│  WS:    /ws/runs/{id}   (fallback: SSE /api/runs/{id}/events)           │
└───────────────┬─────────────────────────────────────────────────────────┘
                │ structured CaseState (Pydantic, PHI-free)
                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ SYSTEM 1 — FAST DECISION ROUTER  (budget: < 50 ms, no text generation)  │
│  Laya local primitives (choice / score / noul) or Jev API, behind a     │
│  System1Router adapter. Deterministic heuristic fallback if either      │
│  is down (graceful degradation).                                        │
│  Decides: required modalities present? → which agents activate;        │
│  risk grade; triage priority; confidence floor.                         │
│  Missing genomics file ⇒ genomics agent DROPPED from graph (no          │
│  hallucination, no wasted compute).                                     │
└───────────────┬─────────────────────────────────────────────────────────┘
                │ routing map + activated-agent list
                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ SYSTEM 2 — LANGGRAPH AGENT SWARM (StateGraph, cyclic, checkpointed)     │
│                                                                         │
│  intake → system1_route → parallel fan-out:                             │
│     ├─ RadiologyAgent     (BiomedCLIP, local worker thread)             │
│     ├─ PathologyAgent     (patch features, local)                       │
│     └─ ClinicalGenomicsAgent (labs, notes, EGFR/ALK/KRAS)               │
│                → rag_evidence (hybrid BM25+dense → Cross-Encoder re-rank)│
│                → evidence_verify (drop >5yr / contradictory papers)     │
│                → debate ⇄ consensus   (cycle, max 3 iterations,         │
│                                        confidence-weighted resolution)  │
│                → self_critic (mimics check: granuloma, pneumonia, …;    │
│                                can route BACK to debate once)           │
│                → explain  (Groq Llama-3-70B or Gemini — clinician view  │
│                             + patient view; ONLY payloads that passed   │
│                             Presidio leave the machine here)            │
│                                                                         │
│  State: LangGraph checkpointer → local encrypted store (AES-256 at rest)│
│  Every node transition → immutable audit event (actor, hash, timestamp) │
└───────────────┬─────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ DATA LAYER (all local / embedded)                                       │
│  ChromaDB or LanceDB  — hybrid vector+BM25 index (guidelines corpus)    │
│  Postgres (asyncpg, parameterized $1,$2) — cases, runs, audit index     │
│  Blob store (local disk, AES-256) — DICOM, patches, reports             │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Layer contracts

| Boundary | Contract | Latency budget |
|---|---|---|
| Browser ↔ FastAPI | REST JSON `{"data":...}` / `{"error":{"code","message"}}`; WSS for run events | TLS handshake < 100 ms |
| FastAPI ↔ System 1 | `CaseState → RoutingMap {agents[], risk_grade, priority}` | **< 50 ms hard budget** |
| System 1 ↔ LangGraph | RoutingMap drives conditional edges / node activation | n/a (in-process) |
| LangGraph ↔ Groq/Gemini | Presidio-scrubbed prompt only; PII guard raises `UnscrubbedPayloadError` and blocks | streaming, first token < 1 s |
| Agents ↔ Vector store | Hybrid query (BM25 + dense) → Cross-Encoder re-rank → top-k | < 500 ms |
| Upload ↔ Integrity | SHA-256 computed on stream (never buffer whole file in RAM) | < 100 ms / file chunk |

### 1.3 Request lifecycle (diagnosis run)

1. Client `POST /api/cases/{id}/diagnose` (JWT) → rate limit → auth.
2. Files verified: SHA-256 recomputed == stored hash; mismatch → `409 integrity_failed`, audit entry.
3. `CaseState` built; Presidio strips PHI from any text fields.
4. System 1 routes in < 50 ms → activated agent list persisted.
5. LangGraph run starts; every node emits `agent_step` event over `/ws/runs/{id}`.
6. Debate/consensus/self-critic cycles run (bounded recursion).
7. Explain node calls Groq/Gemini with scrubbed state (PII guard re-checks at egress).
8. Final report + full step log stored; client receives `run_completed` event.

### 1.4 WebSocket event protocol

```json
{"type":"agent_step","run_id":"...","node":"radiology","status":"started","ts":"..."}
{"type":"agent_step","run_id":"...","node":"radiology","status":"completed","confidence":0.87,"ts":"..."}
{"type":"routing","run_id":"...","activated":["radiology","clinical_genomics"],"dropped":["genomics"],"latency_ms":12}
{"type":"evidence","run_id":"...","citations":[{"pmid":"...","year":2024,"score":0.91}]}
{"type":"warning","run_id":"...","code":"guideline_deviation","message":"..."}
{"type":"run_completed","run_id":"...","diagnosis":"..."}
{"type":"error","run_id":"...","code":"llm_rate_limited","fallback":"local_explanation"}
```

### 1.5 Failure modes → graceful degradation

| Failure | Behavior |
|---|---|
| Groq/Gemini free tier rate-limited | Queue + retry with backoff; fall back to local lightweight summarizer; banner in UI `degraded_mode` |
| Laya/Jev unavailable | Heuristic rule-based router (presence/absence of modalities) — same RoutingMap schema |
| BiomedCLIP worker OOM | Mark radiology node `unavailable`, continue swarm with reduced-confidence flag, surface in report |
| Vector store down | Skip evidence step, flag `evidence_unavailable`, consensus proceeds with agent-only confidence |
| WS dropped | Client reconnects; replay from run event log (events persisted before send) |

---

## Section 2: Free Dataset Mapping

### 2.1 Imaging, genomics, pathology

| # | Dataset | Modality | Access | License | Used by |
|---|---|---|---|---|---|
| 1 | **LIDC-IDRI** (~1,018 cases, 1,010+ thoracic CT) | Lung CT | The Cancer Imaging Archive (TCIA) | CC BY 3.0 (de-identified) | Radiology agent train/eval; nodule detection |
| 2 | **NSCLC-Radiomics** (TCIA) | CT + segmentations | TCIA | CC BY 3.0 | Radiomics features, segmentation eval |
| 3 | **LUNGx / SPIE-AAPM-NCI** (TCIA) | CT | TCIA | CC BY 3.0 | Nodule classification benchmarks |
| 4 | **TCGA-LUAD, TCGA-LUSC** | RNA-seq, mutations, WSI pathology | GDC Data Portal | Open (TCGA data-use) | Genomics + pathology agents |
| 5 | **CPTAC** (LUAD/BRC cohorts + others) | Proteogenomics, WSI | GDC / TCIA | Open (Inscribed) | Biomarker (EGFR/ALK/KRAS) reasoning |
| 6 | **NIH ChestX-ray14** (~112k images) | Chest X-ray | NIH / GitHub mirror | CC0 / open | CXR triage agent eval |
| 7 | **CheXpert** (~224k images) | Chest X-ray | Stanford | Research use (check terms) | CXR pretraining/eval |
| 8 | **MIMIC-CXR** + clinical notes | Chest X-ray + reports | PhysioNet (credentialing required) | PhysioNet Credentialed | Clinical-note ↔ image pairing |
| 9 | **PadChest** (~160k images) | Chest X-ray | Universidad de Granada | CC BY-NC 4.0 | Multilingual report eval |
| 10 | **VinDr-CXR** | Chest X-ray | PhysioNet | PhysioNet license | Detection benchmarks |

### 2.2 RAG corpus (evidence layer)

| Source | Content | Access | Notes |
|---|---|---|---|
| **PubMed Open Access Subset** | Full-text OA biomedical articles | NLM FTP / API, CC BY | Filter: lung cancer, NSCLC, SCLC, nodules, biomarkers |
| **PubMed E-utilities** | Abstracts + metadata (year for staleness filter) | Free API (rate-limit 3/s, no key) | Year captured at ingest → >5 yr papers auto-downweighted |
| **ClinicalTrials.gov** | Trial registry export (API v2) | Free | Biomarker-matched trial lookup |
| **NCCN Guidelines** | Standard-of-care | Free for registered healthcare professionals — **verify license before embedding**; if restricted, use open alternatives (WHO Thoracic Tumour Classification, ATS/ERS statements, open reviews) | Guideline-alignment checks |
| **Structured abstracts from TCGA/CPTAC papers** | Genotype–phenotype links | OA papers | Genomics agent grounding |

### 2.3 Ingestion & legal rules

1. De-identified datasets only; confirm each dataset's license before shipping in repo (link, don't commit, bulk data).
2. Download scripts + checksums live in `data/README.md`; raw data in `.gitignore`.
3. MIMIC/PhysioNet: credentialing required — treat as optional local-only enrichment.
4. Every ingested doc gets: source URL, license, year, SHA-256 → stored with the chunk.
5. Guideline corpus rebuilt monthly (staleness filter depends on fresh metadata).

---

## Section 3: Phase-by-Phase Implementation Roadmap

Estimates assume 1 developer, greenfield repo, includes tests.

### Phase 0 — Repo & scaffolding (≈ half day)

- Monorepo: `backend/` (Python/uv), `frontend/` (Next.js), `docker-compose.yml`, `.env.example`, `.gitignore` (never commit `.env`).
- Tooling: `ruff`, `pytest`, `pytest-cov`, `mypy` (backend); `biome`/`eslint` + ` Vitest` (frontend).
- CI stub: ruff → pytest → `npm run build` → docker compose build.
- **Exit:** `ruff check backend/` green; `pytest` runs (0 tests OK); `npm run build` green.

### Phase 1 — FastAPI core (≈ 2 days)

- `main.py` app factory; routers: health, cases, documents, runs.
- Pydantic models: `CaseInput`, `CaseState`, `RoutingMap`, `AgentReport`, `RunEvent` (max_anystr_length caps).
- asyncpg pool (min 2 / max 10); parameterized queries only; migrations via `alembic`.
- Response envelope `{"data"}` / `{"error"}`; status-code table per `api-design` skill.
- Error handler: log with `logging` (never `print`), never leak internals to client.
- **Exit:** `POST /api/cases` → 201 + `Location`; validation failure → 422 envelope; pytest ≥ 80% on touched modules.

### Phase 2 — Security foundation (≈ 2–3 days) — do BEFORE any LLM integration

- SHA-256 streaming hash on upload; verify-on-read; reject on mismatch (409).
- Presidio pipeline: anonymize text fields → replace with stable cryptographic hashes; **egress PII guard** that raises if PHI patterns survive (this is security-critical: 100% test coverage required).
- AES-256 at rest for blob store (`cryptography`, key from env, never logged).
- Append-only hash-chained audit log (event = prev_hash + payload + ts).
- Rate limiting (slowapi), CORS allowlist, security headers middleware.
- **Exit:** pytest security suite green: injection attempts blocked, unscrubbed payload cannot reach LLM client (mock asserts), hash chain verifies.

### Phase 3 — System 1 router (≈ 1–2 days)

- `System1Router` protocol: `route(case: CaseState) -> RoutingMap` with implementations: `LayaRouter`, `JevRouter`, `HeuristicRouter` (fallback), selected by env.
- Wire as FastAPI dependency + inline LangGraph conditional edge.
- Instrument latency; alert in tests if p95 ≥ 50 ms (heuristic path measured with mocked Laya/Jev).
- Missing-modality rule: absent genomics files → drop genomics agent; absent imaging → drop radiology; always keep clinical if any text exists.
- **Exit:** pytest proves < 50 ms route on 1k synthetic cases; drop rules correct; fallback activates when Laya/Jev raises.

### Phase 4 — LangGraph state machine (≈ 3–4 days)

- `StateGraph` with typed shared state (`CaseState`); checkpointer to encrypted local store.
- Nodes: `system1_route`, `radiology`, `pathology`, `clinical_genomics`, `rag_evidence`, `evidence_verify`, `debate`, `consensus`, `self_critic`, `explain`.
- Parallel fan-out via graph branching; debate loop with `recursion_limit` ≤ 3; `self_critic` may bounce to `debate` once.
- Conditional edges: conflict detector (confidence delta > threshold) triggers debate; missing modalities skip nodes.
- Each node: structured output (`AgentReport`: hypothesis, confidence, missing_flags) + emits WS event.
- Consensus = confidence-weighted, not majority vote.
- **Exit:** integration test: full mock-LLM run produces diagnosis; conflict fixture triggers debate; missing-genomics fixture never calls genomics node.

### Phase 5 — Advanced RAG pipeline (≈ 2 days)

- Ingest: PubMed OA/E-utilities → chunk → embed (local embedding model) → ChromaDB/LanceDB with BM25 metadata.
- Query: hybrid (dense + BM25) → Cross-Encoder re-rank → top-k.
- `evidence_verify`: drop papers > 5 years old (downweight/discard per policy) or contradicting biomarker profile; attach citations with year + score.
- **Exit:** pytest: known query returns expected guideline chunk; stale paper filtered; store-down fallback flags run.

### Phase 6 — Vision/genomics workers (≈ 2 days)

- BiomedCLIP (or MedGemma) in a bounded local worker thread/pool (never block the event loop — `run_in_executor` / separate process).
- CT slice windowing → embeddings → nodule/density flags + bounding boxes; pathology patch features; batch for throughput.
- OOM/unavailable → node `unavailable` + reduced-confidence flag (see §1.5).
- **Exit:** one real LIDC-IDRI case produces structured radiology report in pytest fixture; event loop stays responsive (health check < 100 ms during inference).

### Phase 7 — Next.js 15 frontend (≈ 4–5 days)

- App Router + TS + Tailwind + shadcn/ui; pages: `/cases`, `/cases/[id]`, `/runs/[id]`, `/login`.
- `POST` via Server Actions or route-handler proxy; JWT stored httpOnly cookie.
- Real-time: WS client hook (`useRunStream`) rendering agent step timeline from §1.4 events; SSE fallback.
- Agent swarm visualization: React Flow graph (nodes = agents, states = idle/running/done/blocked) — component ≤ 200 lines, split if needed.
- DICOM/X-ray viewer (cornerstone.js or simple canvas windowing), bounding-box overlay from radiology events.
- Evidence panel: citations with year/score; `degraded_mode` and `warning` banners.
- Accessibility: semantic HTML, `aria-label` on icon buttons, `data-testid` on all test hooks.
- **Exit:** `npm run build` green; manual flow: create case → upload → diagnose → live steps → report; Vitest smoke on `useRunStream`.

### Phase 8 — Hardening & verification (≈ 1–2 days)

- Run full Section 4 checklists (security audit + verification loop).
- Load test System 1 (< 50 ms p95) and diagnose endpoint under rate limit.
- Playwright E2E: ingestion, graph navigation, live run stream, search.
- `docker compose build` + TLS termination config; production CORS/rate-limit values.
- **Exit:** Verification Report all PASS (format in §4.10).

**Total: ≈ 17–22 dev-days.**

---

## Section 4: Granular Actionable Task Checklist

### 4.1 Repository initialization

- [ ] `git init`; add `.gitignore` (`.env`, `node_modules`, `__pycache__`, `data/raw/`, `*.dicom`, chroma sqlite files)
- [ ] Create `backend/`, `frontend/`, `data/`, `docs/` layout
- [ ] `uv init` (or venv) + `backend/pyproject.toml` with pinned deps: fastapi, uvicorn[standard], langgraph, pydantic, asyncpg, slowapi, presidio-analyzer, presidio-anonymizer, cryptography, chromadb (or lancedb), rank_bm25, sentence-transformers/cross-encoder, httpx, pytest, pytest-cov, ruff
- [ ] `npx create-next-app@latest frontend` (TS, Tailwind, App Router) + shadcn/ui init
- [ ] Write `.env.example`: `DATABASE_URL`, `GROQ_API_KEY=`, `GEMINI_API_KEY=`, `JWT_SECRET`, `AES_KEY`, `CORS_ORIGINS`, `SYSTEM1_PROVIDER=laya|jev|heuristic`
- [ ] Add `docker-compose.yml` (backend, frontend, postgres; vector store embedded = no service)
- [ ] CI workflow: ruff → pytest → npm build → docker build
- [ ] First commit + README with run instructions

### 4.2 Backend core

- [ ] App factory, `/api/health` returning version + dependency status
- [ ] Pydantic schemas for `CaseInput`, `CaseState`, `RoutingMap`, `AgentReport`, `RunEvent`
- [ ] asyncpg pool + alembic migration: `cases`, `runs`, `audit_log` tables
- [ ] CRUD: create/list/get case; upload endpoint (streaming, multipart)
- [ ] `POST /api/cases/{id}/diagnose` → starts run, returns `run_id` (202)
- [ ] Envelope + error handlers (404/422/409/429/500 formats)
- [ ] logging (structured), no `print`, no secrets in logs
- [ ] pytest ≥ 80% on modules touched this phase

### 4.3 Security layer (100% coverage on PII guard)

- [ ] Streaming SHA-256 on upload; stored hash; verify on read; 409 on mismatch
- [ ] Presidio anonymizer for all text leaving the box; stable hash tokens for re-identification by authorized role only
- [ ] Egress PII guard decorator on Groq/Gemini client — raises `UnscrubbedPayloadError`
- [ ] AES-256 blob encryption; key via env; key never logged
- [ ] Hash-chained append-only audit log (every agent step, every API mutation)
- [ ] slowapi rate limits (global 60/min, diagnose 5/min, ingest 10/min)
- [ ] CORS allowlist from env; production value ≠ `["*"]`
- [ ] Security headers: HSTS, X-Content-Type-Options, X-Frame-Options, CSP
- [ ] JWT auth + RBAC dependency (`clinician`/`admin`); parameterized SQL everywhere (no f-strings)
- [ ] TLS 1.3 termination config (Caddy/nginx); internal traffic plaintext only behind proxy

### 4.4 System 1 (Laya/Jev) router

- [ ] `System1Router` protocol + Laya / Jev / Heuristic implementations
- [ ] Primitives mapped: `choice` → modality activation; `score` → risk grade; `noul` → confidence floor
- [ ] Missing-modality drop rules + unit tests (genomics absent, imaging absent, text-only)
- [ ] p95 < 50 ms test on heuristic path; latency logged per request
- [ ] Fallback triggers on provider exception/timeout (timeout budget ~30 ms)

### 4.5 LangGraph swarm

- [ ] Typed `CaseState` + checkpointer (encrypted local)
- [ ] All 10 nodes implemented with structured `AgentReport` output
- [ ] Parallel fan-out for radiology/pathology/clinical
- [ ] Debate cycle (max 3) + confidence-weighted consensus (not majority)
- [ ] Self-critic with mimic-check prompt; single bounce-back edge to debate
- [ ] Conflict-triggered conditional edge (confidence delta threshold)
- [ ] Each node emits `agent_step` WS event before/after
- [ ] Integration test: mock LLM full run; conflict fixture; missing-modality fixture
- [ ] Recursion/cycle guards: `recursion_limit` set, loop counters in state

### 4.6 Advanced RAG

- [ ] Ingestion scripts: PubMed OA/E-utilities, ClinicalTrials.gov, guideline PDFs (license-checked)
- [ ] Chunk + metadata (source, year, license, SHA-256) → embed → ChromaDB/LanceDB
- [ ] Hybrid search (BM25 + dense) + Cross-Encoder re-rank
- [ ] `evidence_verify`: stale (>5 yr) filter + biomarker contradiction filter
- [ ] Citation objects surfaced in report and WS `evidence` event
- [ ] Store-down degradation test

### 4.7 Frontend

- [ ] Pages: `/login`, `/cases` (list/create), `/cases/[id]` (upload+status), `/runs/[id]` (live)
- [ ] `useRunStream` WS hook with reconnect + SSE fallback
- [ ] Agent timeline + React Flow swarm visualization (running/done/blocked states)
- [ ] DICOM/X-ray viewer with bbox overlay
- [ ] Evidence panel (citations, year, score); `degraded_mode` / `warning` banners
- [ ] Clinician view vs patient view toggle on final report
- [ ] `data-testid` on every interactive element; semantic HTML; aria-labels
- [ ] `npm run build` green; Vitest smoke tests for stream hook
- [ ] Responsive at 320 / 768 / 1024 / 1440 px

### 4.8 Agent swarm UX states

- [ ] Idle → routing → per-agent running → debate indicator → consensus → self-critic → explain → done
- [ ] Blocked/unavailable agents shown distinctly (not silent)
- [ ] Warning flags from self-critic rendered prominently
- [ ] Run error state with retry affordance
- [ ] Audit trail view (admin RBAC only)

### 4.9 Security audit checklist (run before every release)

- [ ] No hardcoded secrets anywhere (`grep -rn "api_key\|password\|secret"` clean; `.env` untracked)
- [ ] All inputs validated with Pydantic; file type + size limits enforced
- [ ] No SQL/Cypher/f-string query construction (parameterized only)
- [ ] PII guard test proves no PHI reaches external LLM (mock egress assert)
- [ ] SHA-256 integrity verified on sample tampered upload → rejected
- [ ] Audit log hash chain verifies; log is append-only (no update/delete paths in code)
- [ ] CORS restricted to known origins; rate limiting active; 429 tested
- [ ] TLS 1.3 only (sslscan/testssl against staging); HSTS header present
- [ ] AES-256 keys in env/secret manager only; rotation documented
- [ ] Error responses leak no stack traces / internal URLs
- [ ] No API keys or PHI in logs (grep log output in CI)
- [ ] `pip audit` / `npm audit` — no high/critical unpatched
- [ ] RBAC enforced on every mutating route (test each role)
- [ ] WS endpoint authenticated; unauthenticated subscribe rejected

### 4.10 Verification loop (gate for every phase & pre-PR)

```
VERIFICATION REPORT
==================
Backend Lint (ruff):     [PASS/FAIL]
Backend Tests (pytest):  [PASS/FAIL]  coverage: __%
Frontend Build:          [PASS/FAIL]
Frontend Tests:          [PASS/FAIL]
Security Scan:           [PASS/FAIL]
E2E (Playwright):        [PASS/FAIL]
Docker Build:            [PASS/FAIL]

Overall: [READY / NOT READY]
```

- [ ] `ruff check backend/` clean
- [ ] `pytest -v` green, coverage ≥ 80% (PII/integrity/auth paths = 100%)
- [ ] `npm run build` green
- [ ] Security grep clean (4.9)
- [ ] Playwright: ingest flow, live run stream, report render, auth gate
- [ ] `docker compose build` succeeds
- [ ] System 1 p95 < 50 ms under load sample
- [ ] Pre-deploy: production CORS, rate limits on, HTTPS enforced, secrets rotated, DB creds rotated

---

## Section 5 — new.md Gap Analysis & Phase Plan (Phase 9+)

Audit of `new.md` (Proposed Workflow + 10 Novel Ideas) against current state (Phases 0–8 shipped).
**Status key:** ✅ shipped · 🟡 partial · ❌ missing. **Nothing below is started.**

### 5.1 Gap inventory

| new.md item | Status | Evidence in codebase |
|---|---|---|
| Data Standardization Agent (clean/validate/convert) | ❌ | uploads stored raw; no unified intake schema |
| Planning Agent (which modalities/specialists/tools) | 🟡 | `route_case` heuristic presence-routing only; no LLM planner, no tool selection |
| Specialist agents → Diagnosis/Confidence/Evidence/**Missing Information** | 🟡 | reports carry hypothesis+confidence; `missing_flags` hardcoded `[]` (swarm.py) |
| Knowledge Retrieval Agent (PubMed + guidelines + drug DB) | 🟡 | local Chroma 40 PubMed abstracts only; no guidelines, no drug database |
| Evidence Verification (hallucination / contradiction / outdated / unsupported) | 🟡 | `filter_evidence` = year+source filter; no LLM claim-check |
| Consensus via confidence-weighted reasoning | ✅ | `consensus` node |
| Explainability (dx/conf/evidence/**image regions**/reasons/alternatives) | 🟡 | text explain ✅ clinician/patient ✅; bounding-box regions not wired; no structured reasons/alternatives |
| Doctor Dashboard | 🟡 | minimal runs/cases UI; Stitch redesign in progress (screens 1–3) |
| 1. Dynamic Agent Planning ⭐5 | 🟡 | heuristic only (see Planning) |
| 2. Agent Debate ⭐5 | ✅ | debate loop ≤3 rounds |
| 3. Confidence Calibration ⭐4 | ❌ | raw per-agent confs, no calibrated overall + reasons |
| 4. Missing Modality Reasoning ⭐5 | ❌ | agents dropped silently; no explicit uncertainty statement |
| 5. Self-Critique ⭐5 | ✅ | `self_critic` node |
| 6. Evidence Verification ⭐5 | 🟡 | see verification gap |
| 7. Longitudinal Memory ⭐5 | ❌ | no visits, no growth/progression compare |
| 8. Adaptive Explainability ⭐4 | ✅ | Clinician/Patient toggle |
| 9. Guideline Verification ⭐5 | ❌ | no NCCN/ACCP alignment check |
| 10. Multi-Level Fusion ⭐5 | ❌ | single fusion point; no staged image→clinical→knowledge→reasoning |
| Input breadth (blood reports, VCF, prior visits, histo images) | 🟡 | CT DICOM + notes + txt upload; vision worker exists, not in main flow |

### 5.2 New phases (build order)

- [ ] **Phase 9 — Data Standardization Agent**: unified intake schema (imaging / notes / labs / genomics / visits), validation + normalization pass, quality flags; parsers for structured blood reports and VCF; feed `case.metadata`. Exit: garbage inputs rejected with structured errors; all cases carry `standardized` payload.
- [ ] **Phase 10 — LLM Planning Agent**: planner LLM picks specialists + tools (vision? retrieval? drug check?) from standardized case; heuristic `route_case` stays as fallback; plan trace streamed as event. Exit: plan event + cost/fallback counters; planner tests with FakeLLM.
- [ ] **Phase 11 — Missing-modality reasoning + confidence calibration**: real `missing_flags` per agent; explicit uncertainty statements when modalities absent; calibrated overall confidence (per-agent + weighted overall + stated reason, e.g. "no pathology → −18%"). Exit: calibration block in report; tests for down-weight cases.
- [ ] **Phase 12 — Evidence verification + guideline verification**: LLM verifier per citation (relevance / contradiction / outdated / unsupported → keep/reject); add guideline corpus (NCCN/ACCP excerpts) + drug-database source; `guideline_check` node flags diagnosis-vs-guideline discrepancies. Exit: verified-only citations with per-citation verdicts; discrepancy flags surfaced in report.
- [ ] **Phase 13 — Longitudinal memory**: visits table + prior-run compare (nodule growth, stage progression); case timeline API + dashboard widget. Exit: visit 2 run references visit 1 deltas.
- [ ] **Phase 14 — Explainability enrichment**: wire vision-worker regions into explain output (overlay data), structured `reasons[]` + `alternatives[]`; patient/clinician variants per audience. Exit: report shows regions + alternatives; tests on schema.
- [ ] **Phase 15 — Multi-level fusion**: staged fusion pipeline with per-stage artifacts (image → clinical → knowledge → reasoning) replacing single-shot consensus input. Exit: fusion-stage events + ablation-friendly state.
- [ ] **Phase 16 — Stitch UI rollout**: build all 3 Stitch screens (light theme) into the app — Live Agent Swarm Reasoning Room (`stitch/` export, light), Case Workspace & Evidence Cockpit, Clinical Command Center; wire to live run stream + real data. (Screen 1 conversion: in progress separately.)

Dependency note: 9 → 10 → 11 → 12 → 15; 13 and 14 independent after 9; 16 parallel anytime.

**Next action:** review this section — Phase 9 first when building resumes; Stitch screen 1 (light) ships now as UI work.
