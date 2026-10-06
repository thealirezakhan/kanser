KANser — Project Knowledge Pack
1. Executive summary
KANser ("kanser" = cancer) is a multimodal lung-cancer diagnostic command center: a FastAPI backend that ingests clinical documents/DICOM, runs a deterministic "System 1" clinical read, then fans out a LangGraph multi-agent swarm (radiology / pathology / genomics / clinical) that debates, fuses evidence from a local RAG store, reaches consensus or abstains, and explains the result to clinician and patient separately. A Next.js 16 frontend presents it as a case workspace, live run stream, tumor-board group chat, longitudinal timeline, evidence search, and alerts dashboard.
Maturity: working MVP with strong safety/abstention logic and good test hygiene (245 backend tests), single-user auth, several authorization holes, and several documented-but-unbuilt features. Backend runs offline by default (LocalLLM fallback); Groq/Gemini are optional. Repo has one commit (84171df Initial Commit) plus 104 uncommitted changed paths.
2. What the product does
- Create a case with intake (age, sex, reason, notes, modalities) — frontend/src/components/intake-wizard.tsx, POST /api/cases (backend/app/api.py:64).
- Upload studies: text reports, labs CSV, VCF, DICOM — POST /api/documents/ingest (api.py:123), UI at frontend/src/app/cases/[id]/page.tsx:64-88.
- Deterministic per-case assessment ("System 1"): pathway, risk grade, readiness gates, TNM staging, contradictions, "what the system will not infer" — GET /api/cases/{id}/assessment (api.py:328) → assess_case() (app/system1.py).
- Run the agent swarm — POST /api/cases/{id}/diagnose (api.py:418) → run_case() (app/swarm.py:559); events stream over WS /ws/runs/{run_id} (main.py:120).
- View result: consensus diagnosis, calibrated confidence, abstention with known/unknown/resolvable-by, clinician + patient explanations, warnings, citations — frontend/src/app/runs/[id]/page.tsx.
- Ask the board: group chat with @radiologist/@pathologist/@genomicist/@clinician/@all over WS /ws/cases/{id}/chat (main.py:139) with REST fallback (group-chat.tsx:141).
- Verify extracted findings (accept/reject/edit/unknown) — POST /api/findings/{id}/verify (api.py:291).
- Longitudinal visits + progression, evidence search with dropped-citation reasons, alerts (failed runs + high-risk cases), admin/system status page.
3. Users, domain, stakes
Single-credential clinician tool (login ADMIN_USER/ADMIN_PASSWORD, default admin/admin — auth.py:58-63). Domain: oncology/thoracic tumor board. Stakes are high (diagnosis), which explains the abstention machinery: the system is explicitly built to not answer when evidence is missing (abstention.py, states.py, tnm.py).
4. Architecture overview
Browser (Next.js 16, port 3000)
  │  fetch + WebSocket (JWT in localStorage; WS auth rides first message)
  ▼
FastAPI (backend/app/main.py create_app) ── rate limit middleware, CORS, error envelope
  ├── /api router (api.py, router-level Depends(require_auth))
  ├── auth (JWT HS256)  audit (JSONL)  pii (Presidio)  prompt_guard  claims
  ├── system1 (deterministic routing/readiness/TNM)  readiness  conflicts  findings  longitudinal
  ├── swarm (LangGraph StateGraph) ── guarded LLM ── llm.py (Groq | Gemini | LocalLLM fallback)
  ├── rag (Chroma + BM25 hybrid, HashEmbedder)  vision (BiomedCLIP)
  └── repo.py (PostgresRepo | MemoryRepo) + runs.py (in-memory RunStore + asyncpg write-through)
Postgres 17 (port 5433) · Chroma dir backend/data/chroma · uploads data/uploads
5. Tech stack (declared vs installed)
Backend declared (backend/pyproject.toml:6-23): fastapi, uvicorn, pydantic, python-multipart, asyncpg, presidio-analyzer/anonymizer, cryptography, pyjwt, pydicom, langgraph, rank-bm25, chromadb, spacy, httpx, python-dotenv; optional laya, dev pytest/pytest-cov/ruff. Python ≥3.11.
Actually installed in backend/.venv: langgraph 1.2.12, chromadb 1.5.9, spacy 3.8.16, presidio 2.2.364, pydicom 3.0.2, numpy 2.4.6, torch 2.14.0, transformers 5.17.0 — the last two are not declared in pyproject (vision endpoint depends on undeclared packages).
Frontend declared (frontend/package.json): next 16.3.6, react 19.2.8, react-dom 19.2.8, tailwindcss 4, eslint 9, typescript 5, vitest 5. No React Flow, no lucide-react, no chart/graph library (grep of frontend/src finds none) — icons are Google Material Symbols.
6. Repo layout
kanser/
├── backend/  app/*.py (29 modules), tests/ (28 files, 245 tests), Dockerfile, pyproject.toml, .venv
├── frontend/ src/app (12 routes), src/components, src/lib, Dockerfile, package.json
├── docker-compose.yml, .env(.example), Dockerfiles
├── docs/, skills/, stitch/, .opencode/, .playwright-mcp/
└── *.md (README, BLUEPRINT, WALKTHROUGH, project, new) + screenshots  ← context only, not truth
7. Backend structure & entry points
- main.py:37 create_app() — factory; app = create_app() at line 177. Startup hook refuses default JWT secrets (main.py:41-45, auth.py:21). HTTP middleware does rate limiting + security headers (47-63). CORS last so 429s carry ACAO (66-72). Unified error envelopes (74-86). Two WebSocket endpoints (120, 139).
- api.py:31 router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)]) — auth is router-wide; public paths exempted inside require_auth (auth.py:46-55).
- File sizes: swarm.py 641 lines, api.py 534, system1.py 374, repo.py 385 — three exceed the 400-line coding-standard ceiling (skill coding-standards).
8. REST API surface (all under /api, all auth-gated)
Method	Path
POST	/auth/login
GET	/health
POST	/cases
GET	/cases
GET	/cases/{id}
POST	/documents/ingest
GET	/cases/{id}/findings
POST	/findings/{id}/verify
POST	/cases/{id}/routing
POST	/readiness/preview
GET	/cases/{id}/assessment
POST	/cases/{id}/chat
POST	/cases/{id}/visits
GET	/cases/{id}/visits
POST	/cases/{id}/diagnose
POST	/vision/analyze
GET	/runs/{id}
GET	/runs
GET	/evidence/search
GET	/system/status
GET	/alerts
Success envelope {"data": ...}, error {"error": {"code","message"}} (main.py:33-34).
9. WebSocket surface
- WS /ws/runs/{run_id} (main.py:120): subscribe with backlog-seeded queue (runs.py:237), closes after run_completed|run_failed.
- WS /ws/cases/{id}/chat (main.py:139): streams chat_turn then chat_done with token totals.
- Both: _ws_auth accepts, then requires {type:"auth", token} as first message within 10s; token never in URL (main.py:98-118). No case/run ownership check after auth.
10. Authentication
JWT HS256, TTL 8h, secret from JWT_SECRET (auth.py:10-11). assert_strong_secret() refuses missing/<32-char/known-default secrets at startup unless DISABLE_AUTH=1 (auth.py:21-30). require_auth returns "" when auth disabled or path public (auth.py:46-55). Login compares against ADMIN_USER/ADMIN_PASSWORD (default admin/admin) with hmac.compare_digest (auth.py:58-63) — no user table, no roles, single account; the owner column exists for a multi-user future. Frontend: token in localStorage (frontend/src/lib/api.ts), every page does a client-side getToken() redirect — no Next.js middleware/server guard; all routes except /cases/[id], /runs/[id] prerender as static (build output).
11. Authorization & tenancy
_can_read(actor, owner) = actor == "" or owner == "" or actor == owner (api.py:35-38) — legacy unowned rows stay readable.
Owner-checked: cases create/list/get, findings list, assessment, chat, diagnose, run get (api.py:71, 95, 111, 286, 337, 358, 427, 461).
Not owner-checked (evidence): POST /documents/ingest when case_id given (api.py:123-266 — only 404 check), POST /cases/{id}/routing (313), GET|POST /cases/{id}/visits (370, 384), POST /findings/{id}/verify (292), GET /runs (470), GET /alerts (512), GET /evidence/search, POST /vision/analyze, and both WebSockets (main.py:120, 140). Tests cover cross-user read only: test_authz_audit.py:44 test_cross_user_case_read_forbidden.
12. Hardening
- Rate limits: 60/min global, 5/min per IP for /diagnose, keyed by client IP, OPTIONS exempt (main.py:47-63, limits.py).
- Headers: X-Content-Type-Options: nosniff, X-Frame-Options: DENY, Referrer-Policy: no-referrer (main.py:60-62).
- Upload caps: UPLOAD_MAX_BYTES (default 50MB) streaming sha256 with mid-write abort (api.py:137-150); vision 64MB (api.py:443).
- Audit JSONL data/audit/audit.jsonl: case.create/list/read, run.create/read, document.ingest, chat.message, finding.verify (app/audit.py:10).
- Secrets: .env gitignored; compose hardcodes dev Postgres creds kanser:kanser (docker-compose.yml:4-6); .env.example documents only 7 vars (DATABASE_URL, JWT_SECRET, AES_KEY, GROQ_API_KEY, GEMINI_API_KEY, SYSTEM1_PROVIDER, CORS_ORIGINS) while code reads more (ADMIN_USER, ADMIN_PASSWORD, DISABLE_AUTH, UPLOAD_DIR, UPLOAD_MAX_BYTES, AUDIT_LOG, CHROMA_PATH, GROQ_MODEL, RUN_VISION_E2E, KANSER_TEST_DB).
13. Data model
Auto-migrated with CREATE TABLE IF NOT EXISTS (no Alembic):
- cases (repo.py:135): id, patient_ref, modalities, clinical_notes, metadata jsonb, created_at, owner TEXT NOT NULL DEFAULT '' (plus ALTER TABLE ... ADD COLUMN IF NOT EXISTS owner at :148), intake.
- visits (repo.py:155), findings (repo.py:175) with provenance (source_doc, source_kind, origin, verification).
- runs (runs.py:52): id, status, case_id, result jsonb, events jsonb, timestamps.
- metadata is a string→string map used as a document bag: documents (JSON list), labs_raw, vcf, pathology_report, imaging_findings, dicom_header, notes_addendum (api.py:205-233).
14. Persistence & run store
get_repo() picks PostgresRepo(dsn) if DATABASE_URL set, else MemoryRepo() (repo.py, end of file) — no DB = fully in-memory dev mode. RunStore (runs.py:152): memory is source of truth; asyncpg write-through only on terminal status completed|failed (runs.py:178); fetch_db() restores after restart and re-seeds memory so WS works (runs.py:209); pools keyed per event loop (runs.py:32). Event queues are backlog-seeded so late subscribers lose nothing (runs.py:237-247). No TTL/pruning anywhere — the frontend's expired run state (runs/[id]/page.tsx:178, STATUS_STYLE) is unreachable dead UI (grep for expired in backend/app = 0 hits). Run IDs are human-readable: patient-slug-case6-timestamp (runs.py:15).
15. End-to-end flow
1. Intake → POST /api/cases (Visit 1 auto-created, api.py:73-83) → POST /api/readiness/preview from the wizard (intake-wizard.tsx:176).
2. Upload → ingest classifies (classify_file), standardizes labs/VCF/notes, extracts DICOM header + imaging findings + deterministic extract_findings, merges modalities, invalidates chat context (api.py:152-251).
3. Assess → GET /assessment → assess_case() returns pathway, routing, readiness, TNM, contradictions, must_not_infer (api.py:341).
4. Diagnose → 202, background _execute_run (api.py:396-415) → run_case:
standardize_case event → assess_case (System 1) event → planner event → LangGraph stream → events pushed to run_store → on completion invalidate_context(case_id) (api.py:411).
5. Explain → clinician/patient text, literature whitelist, warnings; UI shows it (runs/id).
16. Ingestion & standardization
classify_file → kinds: labs, genomics, notes, pathology, imaging_report, ct, raw. standardize_case (standardize.py) produces schema_version + quality_flags, whose messages become the run's initial warnings (swarm.py:615-618). Deterministic extractors: findings.py (lesion size, histology, nodes, non-diagnostic tissue), imaging.py (DICOM header via pydicom, report measurements, modality classification), conflicts.py (cross-document contradictions). Files stored under data/uploads as <uuid>_<name> plus .sha256 sidecar (api.py:133-150).
17. System 1 — deterministic layer (no LLM)
system1.py (route_case, assess_case) + readiness.py (evaluate) + tnm.py + longitudinal.py (progression) + states.py/abstention.py (derive_diagnosis_state, evaluate_abstention). Produces: pathway, activated/dropped agents with skip reasons, risk grade/priority, HITL & tumor-board flags, provider, readiness gates per pathway, uncertainty flags, recommended investigations (test/question/why/priority), TNM determinable with warnings, contradiction list, must_not_infer list. Provider selectable via SYSTEM1_PROVIDER; tests cover 5 worked examples A–E (test_longitudinal.py:113-248).
18. Planner & routing
route_case() (system1.py) gives base routing; build_plan(case, routing, llm=guarded) (planner.py) may override the agent set, emitting plan event with agents/tools/reasons/provider (swarm.py:527-535, 570-577). Provider heuristics: planner._heuristic + LLM path.
19. LangGraph swarm (swarm.py)
State: CaseState TypedDict with merge/concat reducers (swarm.py:21-36). Nodes: radiology|pathology|genomics|clinical (fan-out from START by routing, fallback rag_evidence, :480) → rag_evidence → evidence_verify → fusion_stages → conditional debate↔consensus (conflict = max−min confidence ≥ 0.3, max 3 rounds, :82-84, 454-462) → self_critic (may loop back to debate once, :464-467) → explain → END. Compiled with recursion_limit: 40 (swarm.py:621).
Details:
- Per-agent prompt demands JSON {"hypothesis","confidence"}; missing confirmatory artifacts produce missing_flags (radiology wants dicom_scan/imaging_findings, pathology slide, genomics vcf, clinical labs) (:42-58).
- GuardedLLM scrubs every prompt through Presidio before egress (:61-71).
- Confidence is not the LLM's: _calibrate() = weighted mean (radiology .3, pathology .3, clinical .25, genomics .15) minus 0.05 per missing modality, clamped 0.01–0.99; LLM self-report kept separately as llm_confidence (:49, 91-110, 325).
- evidence_verify applies filter_evidence (stale/contradicted) then an LLM relevance pass with wrap_untrusted citation text (:196-248).
- consensus fuses staged scores (image/clinical/knowledge), runs abstention, sets diagnosis_state (:277-358).
- explain produces clinician + patient text; sanitize_literature whitelists citation IDs to retrieved evidence; gate_clinician_text blocks bounding-box/molecular claims without vision/genomics (:400-452).
20. LLM layer (llm.py)
GroqClient (httpx, rate-limited wrapper), Gemini, and LocalLLM deterministic fallback; get_llm() selects by env (GROQ_API_KEY, GEMINI_API_KEY, SYSTEM1_PROVIDER). With no keys the system still runs end-to-end — tests rely on this (test_llm.py:9 test_local_llm_no_network). Model name surfaced by GET /system/status.
21. RAG & evidence (rag.py)
HashEmbedder (256-dim hashed bag-of-words, no model download) + ChromaStore (path data/chroma, local HF-style mirror) + BM25 (rank_bm25) → hybrid_search → rerank → filter_evidence (drops stale/contradicted per case metadata) → build_query(reports). get_rag() returns a callable or a no-op when no store data (rag.py:181+). Evidence IDs feed the citation whitelist.
22. Clinical safety controls
- Abstention: evaluate_abstention() — e.g. histologic claim without pathology, molecular claim without genomics, bounding-box claim without a vision run → abstain{reason, known, unknown, resolvable_by}, confidence forced to 0 (swarm.py:317-327); UI renders it prominently (runs/id:267-294).
- Diagnosis states: insufficient_evidence → finding → suspicion → working_diagnosis → confirmed → staged → treatment_context (derive_diagnosis_state), with unknown states (no_evidence, tissue_pending, non_diagnostic, …) styled amber in the UI (assessment-panel.tsx:22-28).
- Conflicts never silently resolved: histology/measurement conflicts force indeterminate stage (conflicts.py, tests test_findings.py:135-184).
- Claims gating: claims.sanitize_literature, claims.gate_clinician_text; VISION_RAN flag in vision.py:73.
- Prompt injection: prompt_guard.wrap_untrusted around all untrusted text in prompts (swarm.py:131, 207, 304, 401).
- PII: pii.PiiGuard.anonymize + assert_clean on every LLM call (get_pii_guard).
- UI honesty: confidence labeled "model self-report, uncalibrated" (runs/id:303).
23. PII & security posture
Presidio analyzer/anonymizer wired into GuardedLLM and chat (api.py:364, main.py:159). AES key from AES_KEY (security.py also provides AuditLog). No secrets in code (grep of backend finds only env reads); .env present locally but gitignored. Dev-grade weaknesses: single default admin/admin account, hardcoded compose DB creds, no HTTPS/staging config, permissive CORS default http://localhost:3000 (overridable via CORS_ORIGINS).
24. Vision / imaging capability
vision.py implements real DICOM pixel decode (pydicom) → grayscale RGB → BiomedCLIP zero-shot prompts ("malignant pulmonary nodule" vs "normal lung") with flagged + scores; VISION_RAN gates bounding-box claims. Status: IMPLEMENTED but operationally fragile — torch/transformers are installed in .venv yet not declared in pyproject.toml, model weights are not in the HF cache (cache contains only stable-diffusion entries), so first call downloads ~hundreds of MB and requires network; /api/vision/analyze has no owner/authz beyond router-level auth and no frontend caller (only mentioned as a static row on admin/page.tsx:32). E2E vision test is opt-in: test_vision.py:109 skips unless RUN_VISION_E2E=1.
25. Frontend
Next.js App Router, all client components ("use client"), Tailwind 4 tokens (globals.css), Material Symbols icons. Routes: / dashboard, /login, /cases, /cases/[id], /runs/[id], /swarm, /tumor-board, /evidence, /alerts, /longitudinal, /admin, /_not-found. Build output: only /cases/[id] and /runs/[id] are dynamic; the rest are static-prerendered with client-side auth redirects.
Key components: shell.tsx (nav + alerts/status polling at :213-218), intake-wizard.tsx (readiness preview + create), assessment-panel.tsx (full System 1 readout incl. contradictions, gates, routing, must-not-infer, recommendations), findings-panel.tsx (verify workflow), case-timeline.tsx (visits + add visit), group-chat.tsx (WS with REST fallback, per-agent token counters, mention chips), useRunStream.ts + lib/runEvents.ts (WS with sequence/reducer, remount-by-id to avoid state bleed — runs/[id]:80-81 "GAP-003"). No graph/React Flow view exists despite skills mentioning one.
26. Testing & quality gates (verified this session)
Gate
backend: pytest
skips
backend: ruff check .
frontend: vitest run
frontend: eslint
frontend: next build
CI
Test strengths: authz/audit, WS auth handshake, upload caps, abstention states, conflicts, ingestion/standardization, chat targeting + context invalidation, RAG citation rules, LLM offline hermeticity (autouse fixtures in tests/conftest.py: auth off, LLM isolated, memory repo). Weakness: exactly one cross-user authorization test; no tests for the owner-check gaps listed in §11.
27. Deployment, configuration, environment
docker-compose.yml: postgres:17-alpine (host 5433 → 5432, healthcheck), api (build ./backend, port 8000, env_file: .env, explicit DATABASE_URL/CORS_ORIGINS/CHROMA_PATH, volume ./backend/data:/app/data, waits for healthy Postgres), web (build ./frontend, port 3000, NEXT_PUBLIC_API_URL=http://localhost:8000). Backend Dockerfile + frontend Dockerfile present; main.py:17-18 loads .env from repo root for local dev (compose supplies it in container).
Env vars read by code: DATABASE_URL, JWT_SECRET, AES_KEY, GROQ_API_KEY, GEMINI_API_KEY, SYSTEM1_PROVIDER, CORS_ORIGINS, ADMIN_USER, ADMIN_PASSWORD, DISABLE_AUTH, GROQ_MODEL, AUDIT_LOG, CHROMA_PATH, UPLOAD_DIR, UPLOAD_MAX_BYTES, KANSER_TEST_DB, RUN_VISION_E2E, NEXT_PUBLIC_API_URL. Documented in .env.example: the first 7 only.
28. Status matrix & known gaps
IMPLEMENTED (code + tests): case CRUD with owner, visits/longitudinal, findings+verify, deterministic extraction (labs/VCF/pathology/imaging/DICOM), standardization, System 1 routing/readiness/TNM/states, LangGraph swarm with debate/consensus/critic/explain, calibrated confidence, abstention, conflicts, RAG hybrid+filter, JWT auth + startup secret check, rate limits + security headers, WS streaming (runs + chat) with token-in-first-message, audit JSONL, PII guard, prompt-injection guard, claim gating, BiomedCLIP vision code, Docker Compose, 245 backend tests.
PARTIAL: vision (declared deps missing, weights not cached, no UI path); multi-tenancy (owner column + checks exist but single account, and 7 endpoints/2 WS skip checks, §11); run history (persists only terminal states; no expired state ever set); auth docs (.env.example omits ADMIN_*, DISABLE_AUTH, etc.).
CONFIGURED-BUT-UNUSED: POST /api/cases/{id}/routing (no frontend caller), POST /api/vision/analyze (UI only lists it in admin), laya optional dependency (no imports found), frontend expired run state (dead), POST /api/cases/{id}/chat REST path used only as WS fallback.
PLANNED (in docs/skills only — zero code): /api/graph/* endpoints, Neo4j, /api/extraction/extract, /api/simulate, React Flow knowledge graph, per skills/*.md and api-design skill. Grep for graph/overview|simulate|neo4j in backend = no matches.
UNKNOWN: production usage/monitoring, whether Groq/Gemini keys are ever configured, real user counts, DB migration strategy beyond CREATE TABLE IF NOT EXISTS, model weight provenance/volume, any performance/latency measurements (no benchmarks found), i18n/Turkish localization (UI strings are English despite Turkish product name).
Risks (ranked): (1) authorization gaps in §11 — ingest, visits, routing, finding-verify, /runs, /alerts, both WS; (2) default admin/admin if ADMIN_* unset; (3) undeclared vision deps + first-call model download; (4) no CI; (5) swarm.py/api.py exceed file-length standards; (6) Postgres creds hardcoded in compose; (7) in-memory fallback silently degrades durability when DATABASE_URL missing.
29. Source map (file → responsibility)
Backend — main.py app factory/middleware/WS · api.py all REST routes + authz · auth.py JWT/credentials · schemas.py Pydantic models (CaseInput/VisitIn/FindingIn, owner) · repo.py Memory/Postgres repos + auto-migration · runs.py RunStore + runs table · swarm.py LangGraph graph + calibration · system1.py routing/assessment · readiness.py gates/recommendations · tnm.py staging · states.py/abstention.py diagnosis states · conflicts.py/findings.py/imaging.py/standardize.py deterministic extraction · planner.py tool/agent plan · llm.py providers · rag.py embed/store/hybrid/filter · chat.py board chat + context cache · pii.py Presidio guard · prompt_guard.py injection wrapping · claims.py literature/claim gating · security.py AES + AuditLog · audit.py audit record() · limits.py rate limiters · longitudinal.py progression · vision.py BiomedCLIP · __init__.py empty.
Tests — tests/ 28 files mirroring modules; conftest.py autouse hermetic fixtures.
Frontend — src/lib/api.ts fetch/ws/token · src/lib/useRunStream.ts + runEvents.ts run streaming · src/app/* 11 pages · src/components/shell|group-chat|assessment-panel|findings-panel|case-timeline|intake-wizard|intake-readiness|intake-fields|ui/*.
Ops — docker-compose.yml, backend/Dockerfile, frontend/Dockerfile, .env(.example), backend/pyproject.toml, frontend/package.json.
Non-authoritative — README.md, BLUEPRINT.md, WALKTHROUGH.md, project.md, new.md, docs/*, skills/* (describe features that don't exist, see §28).
10-minute explanation
What it is (1 min). KANser is a tumor-board command center. A clinician logs in, opens a case (age, sex, presenting problem, notes, which modalities exist), uploads reports/labs/genomics/DICOM, and asks the system to assess and diagnose. The distinctive thing: the platform is engineered to refuse to answer when the evidence isn't there, and to show exactly what it's missing.
Ingestion (1 min). POST /api/documents/ingest streams the file to data/uploads, hashes it with sha256 (sidecar written), classifies the kind (labs CSV, VCF, pathology, imaging report, CT, notes), standardizes labs/VCF into a unified schema with quality flags, pulls DICOM headers with pydicom, extracts measurements from radiology text, and creates provenance-tracked findings (source_doc, origin: ai, confidence). A clinician can later accept/reject/edit each finding; conflicts between documents are detected, never auto-resolved.
System 1 — the deterministic brain (1.5 min). Before any LLM runs, system1.assess_case computes a clinical read purely in code: which pathway the case is on, risk grade and priority, which of the four specialist agents should be activated and why the others are dropped, readiness gates (imaging ready? tissue ready?), uncertainty flags, TNM stage when determinable (otherwise "indeterminate — insufficient evidence"), contradiction list, and an explicit must_not_infer list ("will not infer histology without pathology"). GET /api/cases/{id}/assessment returns all of it, and the UI renders it as the case's assessment panel. This is the safety floor: even a fully offline install gives structured, explainable triage.
The swarm (2 min). POST /diagnose returns 202 and runs a LangGraph state graph in the background: standardize event → System 1 event → planner event → fan-out to whichever specialist agents routing selected → each returns {hypothesis, confidence} as JSON and flags its missing confirmatory artifact → RAG retrieves candidate citations (hash embeddings + Chroma + BM25 hybrid) → evidence_verify drops stale/contradicted citations deterministically and then asks the LLM which remaining ones are irrelevant → staged fusion (image / clinical / knowledge scores) → if agent confidences diverge by ≥0.3, a debate node reweights them (max 3 rounds) → consensus → self_critic (mimics like granuloma/pneumonia, NCCN alignment; may push one more debate) → explain, which produces a clinician view and a compassionate patient view separately.
Where confidence comes from (1 min). The LLM's own number is not the headline. _calibrate() computes a weighted mean (radiology 0.3, pathology 0.3, clinical 0.25, genomics 0.15), subtracts 0.05 per missing modality, clamps to 0.01, 0.99, and the UI labels the raw LLM number "model self-report, uncalibrated."
Abstention (1 min). After consensus, evaluate_abstention checks whether the claim is licensed by available evidence — histology without pathology, molecular claims without genomics, bounding-box claims without a completed vision run — and if not, sets confidence = 0 and returns {reason, known, unknown, resolvable_by}. The run page shows "Abstained — Insufficient Evidence" with those three lists. Diagnosis states (suspicion, working_diagnosis, confirmed, staged…) derive from modalities + abstention, so the system never claims more certainty than the artifacts support.
Live UX (1 min). Events stream over /ws/runs/{id} (auth as first message, never in the URL; queues are backlog-seeded so a late joiner sees everything). The run page shows the event timeline, then the reasoning inspector: diagnosis, calibrated confidence bar, clinician/patient toggle, "information deficits" flags, and grounding citations. The tumor-board page is a group chat where @all fans out to all four agents turn by turn over /ws/cases/{id}/chat with automatic REST fallback, showing per-agent token totals.
Plumbing (1 min). Storage: PostgresRepo when DATABASE_URL exists, otherwise a pure in-memory repo — runs persist to a runs table only when they finish, and are restored after restart. JWT HS256 with an 8-hour TTL, a startup check that refuses weak/default secrets, DISABLE_AUTH for dev, router-wide auth on /api, per-IP rate limits (60/min, 5/min for diagnose), nosniff/DENY/no-referrer headers, JSONL audit trail, Presidio PII scrubbing on every prompt, prompt-injection wrapping of all untrusted text, and a literature whitelist so the model can only cite retrieved evidence.
Honest gaps (1 min). Single account (admin/admin by default) — owner-based tenancy exists but seven endpoints and both WebSockets skip the owner check; vision (BiomedCLIP) is coded but its torch/transformers deps aren't declared and weights aren't cached; no CI; no knowledge-graph/Neo4j/simulation features despite what the skills docs describe; the frontend's "run expired" state can never trigger; no Next.js server-side auth guard. Verification today: 243 backend tests pass (2 gated skips), ruff clean, 6 frontend tests pass, eslint and next build clean.
Bottom line. The core loop — ingest → deterministic assess → guarded multi-agent debate → calibrated consensus or abstention → dual-audience explanation, all streamed live — is genuinely implemented and well tested. What's missing is operational polish (multi-user authz completeness, CI, dependency declaration) and everything advertised in the docs that has no code behind it.