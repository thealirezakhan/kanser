# KANser — Clinical Reality Audit

Read-only audit of the KANser repository against real-world lung-cancer decision support.
Every claim cites `file:line`. Classification tags: IMPLEMENTED / PARTIALLY IMPLEMENTED / MOCKED / HARDCODED / UNUSED / BROKEN / UNTESTED / PLANNED / MISSING.

Scope: `backend/app/*` (17 modules), `backend/tests/*` (17 files), `frontend/src/*` (12 routes), Docker, config, docs. Followed the data, the API, the state, the graph, the evidence, the final report. Companion documents:

- `docs/CLINICAL_GAP_REGISTER.md` — prioritized gap entries (GAP-xxx)
- `docs/AGENTIC_AI_AUDIT.md` — per-agent value matrix
- `docs/CLINICAL_WORKFLOW_MATRIX.md` — workflow-by-workflow status
- `docs/LAYA_SYSTEM1_ARCHITECTURE.md` — System 1 audit + redesign
- `docs/SAFETY_AND_HALLUCINATION_AUDIT.md` — safety gates and hallucination controls

---

## 1. Executive Summary

KANser is a working full-stack prototype that runs a real LangGraph agent graph over real (Groq) LLM calls, with real PHI scrubbing, real WebSocket streaming, real PubMed-backed retrieval, and a real Next.js 12-route frontend. That is more than a demo shell.

It is **not yet a clinical decision-support environment** a pulmonologist or tumor board could rely on, because the clinical middle layer is missing: there is no patient model, no staging, no histology, no IHC, no biomarker/PD-L1 representation, no specimen model, no document versioning, no provenance, no abstention, no physician review path, and no contradiction detection between clinical sources. The system's core loop is still:

> `Documents → Agents → LLM → Diagnosis`

with the missing evidence represented only as a `-0.05 × missing modalities` penalty on a confidence number (swarm.py:95-97), never as a block.

The most safety-relevant findings:

1. **No output validation.** Captured production runs show a run where only `clinical` and `radiology` agents executed, yet the clinician-facing explanation reports `EGFR L858R (VAF 12%), KRAS G12C … PD-L1 TPS 30%` and bounding-box coordinates, plus fabricated author citations (`Smith et al., 2023`). Enabler: `swarm.py:400` passes LLM-supplied `literature` strings through unvalidated; nothing blocks molecular or pathology claims when the corresponding data does not exist. **P0**
2. **No abstention.** Missing pathology never prevents a "Consensus Diagnosis" from rendering as `NN.N% Match` (`runs/[id]/page.tsx:208-219`). Confidence floor is 0.01, not 0 (`swarm.py:97`). **P0**
3. **No structured clinical model.** Entities are exactly `Case`, `Visit`, `Run` (`schemas.py:9-44`, `runs.py:52-60`). No T/N/M, histology, IHC, PD-L1, specimen, patient demographics, smoking status, or treatment anywhere in the schema. **P1**
4. **"Debate" is not a debate.** The debate prompt receives `{agent: confidence}` floats only — hypotheses stripped (`swarm.py:466-470`). One LLM call rewrites numbers. **P1**
5. **Security posture cannot support multi-clinician use.** Known JWT secret committed in `docker-compose.yml`, default `admin/admin` (`auth.py:40-41`), zero per-resource authorization, audit-log class implemented but never instantiated (`security.py:43-78`), uploads not gitignored (80 untracked clinical files, some committed). **P0/P1**
6. **Frontend state leaks.** Run events not reset between runs (`useRunStream.ts:13`), chat messages not keyed per case (`tumor-board/page.tsx:113`) → cross-patient display. Run page shows no patient identity. **P0**

Verdict on the "agentic" claim: the agents exist and run, but their clinical responsibilities are thin (one prompt, one JSON reply each — `swarm.py:118-158`), two of the four can never see their own data type (standardized payload read by zero nodes: `swarm.py:561`), planner tools are decorative (`plan.tools` consumed nowhere), and the vision model is unreachable in the shipped container. Detailed verdict per agent: `docs/AGENTIC_AI_AUDIT.md`.

---

## 2. What KANser Actually Does Today

Verified against implementation:

- **Auth**: single shared credential, JWT HS256, 8 h TTL (`auth.py:10-17,40-44`). Rate limits 60/min global, 5/min diagnose, per-IP (`limits.py:25-26`, `main.py:42-49`).
- **Case CRUD**: create/list/get cases (`api.py:55-79`). Case = `patient_ref` string + modality list + free-text notes + metadata dict (`schemas.py:9-24`).
- **Document ingest**: TXT/MD/CSV/VCF classify correctly; PDF accepted but decoded as empty (no PDF library — `api.py:104-107`); DICOM stored raw, never parsed; PNG/JPG always labelled `"ct"` (`standardize.py:20-33`). SHA-256 written on upload, never verified on read (`api.py:93-99`, `verify_integrity` test-only).
- **Standardization**: extracts labs key-values, VCF gene rows, quality flags (`standardize.py:36-145`). Output is written to state (`swarm.py:561`) and read by **zero graph nodes**.
- **Routing**: `HeuristicRouter` (default; modality-presence rules + risk regex — `system1.py:34-75`), optional `LayaRouter` (`system1.py:78-144`, laya 0.3.20 present in venv, **disabled** by `.env` `SYSTEM1_PROVIDER=heuristic`, **absent from the Docker image** — optional extra, `pyproject.toml:26`).
- **Planner**: heuristic or LLM plan (`planner.py:59-85`) — gates `activated` agents (`swarm.py:537-544`); `plan.tools` is display-only (no consumer).
- **Graph**: 11 nodes — 4 specialists (one LLM prompt each, `swarm.py:118-158`), `rag_evidence`, `evidence_verify`, `fusion_stages`, `debate`, `consensus`, `self_critic`, `explain` (`swarm.py:436-461`). Conditional debate on confidence spread ≥0.3 (`swarm.py:80-82`).
- **RAG**: hybrid Chroma + BM25 over 40 PubMed abstracts (`scripts/ingest_corpus.py`), hash embedder (broken across restarts — see §16), 5-year staleness filter (`rag.py:144-155`), LLM relevance drop (`swarm.py:199-219`), rerank permanently a silent no-op (`rag.py:135-136`, `sentence_transformers` not installed).
- **PHI**: Presidio `PiiGuard` + `GuardedLLM` wraps **every** LLM call site (graph, planner, REST chat, WS chat — `swarm.py:59-69,535,545`, `chat.py:143`). Prompt-side only; responses not scanned on egress.
- **Runs**: async execution, WS event stream, terminal-state persistence to Postgres (`runs.py:178`), run IDs derived `patient-case6-timestamp` (`runs.py:15-20`).
- **Chat**: per-case group chat with `@all` fan-out, bounded history (16), token accounting (`chat.py`); context cached once per case and **never invalidated** (`chat.py:103-108`).
- **Longitudinal**: visits with size_mm; progression = first-vs-last delta trend (`longitudinal.py:34-37`).
- **Frontend**: 12 routes (dashboard, cases, workspace, run report, swarm, tumor-board chat, evidence search, longitudinal, alerts, admin, login).

## 3. What KANser Claims To Do

From `README.md:3`, `BLUEPRINT.md:3-4`, `project.md:1`, admin UI, shell:

- "Production full-stack platform … Laya/Jev System 1 router" (README:3)
- "Multimodal lung cancer agentic AI diagnosis platform" (`layout.tsx:17`)
- "highly secure", "TLS 1.3 / PHI Scrubbed", "AES-256-GCM field encryption at rest" (`shell.tsx:186`, `admin/page.tsx:137`)
- "Audit Logger — append-only, hash-chained … every agent step" (BLUEPRINT:33)
- Rate-limit "Retry-After" header (WALKTHROUGH:147)
- Failure modes: retry with backoff, degraded-mode banner, vision-node reduced-confidence flag (BLUEPRINT:121-123)
- Multimodal ingestion, evidence-grounded consensus, guideline alignment (NCCN), structured agent reports

## 4. Claims Not Supported By Implementation

| Claim | Verdict | Evidence |
|---|---|---|
| "Production" | **FALSE** | admin/admin default (`auth.py:40-41`), public JWT secret (`docker-compose.yml:27`), no retry/backoff, no metrics, no RBAC |
| "Laya/Jev router" | **PARTIAL / FALSE** | Laya implemented but off by default and absent in image; **Jev: 0 code hits** |
| "Next.js 15" | **FALSE** | `package.json`: next 16.3.6, react 19.2.8 |
| "Gemini (System 2)" | **FALSE** | key in `.env`, 0 code hits |
| "AES-256-GCM at rest" | **FALSE** | `aes_encrypt` used only by tests (`test_security.py:19`) |
| "Audit log every mutation/step" | **FALSE** | `AuditLog` never instantiated; `main.py:79` `audit_path` unread |
| "SHA-256 verified on read → 409" | **FALSE** | hash written, never verified at runtime; no 409 path exists |
| "Retry-After on 429" | **FALSE** | `_error` sets no headers (`main.py:30-31`) |
| "LLM rate-limit → retry/backoff/degraded banner" | **FALSE** | `RateLimited` uncaught → run `failed` (`llm.py:67-68`, `api.py:218-221`) |
| "Vision OOM → reduced-confidence node" | **FALSE** | exception → 500; deps absent from pyproject/Docker |
| "TLS 1.3" badge | **FALSE** | no TLS config in repo; hardcoded UI text (`shell.tsx:186`) |
| Admin "PHI scrubbed before every LLM call" | **TRUE** | `GuardedLLM` at every call site |
| "Vector store down → continue, flag" | **TRUE** | `swarm.py:186-192` + test |
| `POST /api/extraction/extract` listed in admin | **FALSE** | endpoint does not exist (RippleTrace leftover, `admin/page.tsx:33`) |

## 5. Real-World Lung Cancer Workflow Comparison

Target conditional pathway vs KANser:

| Stage | KANser status |
|---|---|
| Suspicion / detection | Case creation with free-text notes; no structured suspicion. **MISSING** |
| Clinical assessment | Free-text only; no demographics, symptoms, smoking, comorbidity, PS. **MISSING** |
| Initial imaging review | Upload stores file; no viewer, no DICOM UIDs, no structured findings. **PARTIAL** |
| Risk characterization | Regex keyword risk grade (`system1.py:43-48`); no Fleischner/RADS logic. **PARTIAL** |
| Decision re: tissue diagnosis | **MISSING** |
| Biopsy / cytology | **MISSING** (no specimen entity) |
| Pathology | Agent name + modality checkbox only. **PLANNED / NON-FUNCTIONAL** |
| Histologic classification | **MISSING** |
| IHC | **MISSING** (0 hits backend-wide) |
| Molecular / biomarker | VCF gene strings only; no interpretation, no PD-L1, no assay. **PARTIAL** |
| Staging | **MISSING** (regex "stage iii" only, `system1.py:11-13`) |
| Multidisciplinary interpretation | Per-case AI group chat. **PARTIAL** |
| Treatment-planning context | **MISSING** |
| Longitudinal follow-up | Visits + one pooled size series (no per-lesion). **PARTIAL** |

The system accepts a CT upload and free-text note and returns a diagnosis with a percentage. That is the "CT + notes = diagnosis" pattern the mission explicitly rejects.

## 6. Missing Clinical Inputs (input matrix)

| Domain | Expected | Status | Evidence | Recommended change |
|---|---|---|---|---|
| Demographics | age, sex, smoking, pack-years, exposures, family hx, PS | **MISSING** | 0 field hits in `repo.py`/`schemas.py` | Structured `Patient` entity + demographics |
| Symptoms | cough, hemoptysis, duration, progression, incidental flag | **MISSING** | free text only | Structured symptom/observation fields |
| Initial imaging | studies, series, priors, comparison, PET/MRI | **PARTIAL** | `.dcm` stored unparsed, `api.py:104-107`; no Study/Series entity | DICOM metadata parse + study/series model |
| Imaging features | size, lobe, morphology, attenuation, invasion, nodes | **MISSING** | no structured radiology findings; `imaging_findings` key never written | Structured radiology findings schema |
| Pathology | specimen → adequacy → morphology → dx → IHC → molecular | **MISSING** | 0 IHC hits; no Specimen entity | Full pathology workflow (GAP-004) |
| Molecular | gene, variant, VAF, assay, tissue/plasma, pending/fail | **PARTIAL** | `standardize.py:97-99` gene/pos/ref/alt strings only | Versioned biomarker model (GAP-006) |
| PD-L1 | TPS, assay, specimen, interpretation, unavailable states | **MISSING** | 0 hits | Structured PD-L1 result (GAP-006) |
| Labs | CBC/CMP/renal/liver, date, units, ref range | **PARTIAL** | string map, no dates/ranges (`standardize.py:36-67`) | Typed observations with dates |
| Tissue acquisition | procedure, site, accessibility, staging intent | **MISSING** | — | Procedure/specimen entity (GAP-005) |
| Nodal/mediastinal | stations, PET, EBUS, nodal pathology | **MISSING** | — | Staging evidence model (GAP-007) |
| Prior cancer | primary site, histology, date, treatment, recurrence | **MISSING** | — | History entity (GAP-010) |
| Treatment context | surgery/RT/systemic, line, response, AE | **MISSING** | 0 hits | Treatment episodes (GAP-011) |

## 7. Missing Documents

| Document | Upload | Parse | Store | Reason over | Status |
|---|---|---|---|---|---|
| Radiology report (TXT/MD) | yes | yes | orphan metadata (`notes_addendum`, **never read**) | no | **BROKEN** (`api.py:136`) |
| PDF reports | yes | **no** — `UnicodeDecodeError → text=""` (`api.py:104-107`) | yes | no | **BROKEN** |
| DOCX | no | no | — | — | **MISSING** |
| DICOM | yes | no (stored raw) | yes | no (no UIDs) | **PARTIAL** |
| Pathology slides (.svs/.tiff) | no | no | — | — | **MISSING** |
| Scanned reports / OCR | no | no | — | — | **MISSING** |
| Molecular/NGS report (PDF) | as PDF → empty | no | yes | no | **BROKEN** |
| Lab CSV | yes | 4-word header sniff | merges (last-write-wins) | yes (labs) | **PARTIAL** |
| VCF | yes | yes | merges (**overwrites prior VCF**) | yes (gene list) | **PARTIAL** |
| Images (jpg/png) | yes | no | labelled `ct` regardless | no | **HARDCODED** |
| Preliminary/final/amended/superseded | — | — | no version state | — | **MISSING** |
| Duplicate detection | SHA-256 computed, never compared (`api.py:98-99`) | — | — | — | **MISSING** |

## 8. Missing Tests / Investigations

127 backend test functions exist (17 files), covering envelopes, routing, debate bounds, PII scrubbing, RAG filters, visits math, WS auth. Absent entirely (confirmed by search):

- staging, biomarkers, PD-L1, histology, IHC, pathology gating
- abstention / refuse-to-answer / confidence floor behavior
- cross-patient isolation (no test proves case A ≠ case B reasoning)
- prompt injection (0 matches)
- corrupted/truncated uploads
- adversarial LLM outputs (`confidence: "NaN"`, `1e9`, lists — `swarm.py:138` `float()` can raise and kill the run)
- temporal consistency / date conflicts
- contradiction handling between clinical sources
- Groq production path through `run_case` (conftest deletes `GROQ_API_KEY` for all tests)
- real Laya (only `FakeLaya`), hash-embedder cross-process stability (would fail)
- frontend: only `runEvents.test.ts` (5 tests); zero page/component tests

## 9. Missing Data Models

Entities that must exist and don't: **Patient, Encounter, Document (as first-class record), ImagingStudy, Series, Specimen, Procedure, Observation (typed), Condition/Diagnosis, Staging (T/N/M + group), BiomarkerResult, Medication/TreatmentEpisode, Report (versioned), Review/SignOff, Annotation, AuditEntry (table)**. Current schema: 3 tables — `cases`, `visits`, `runs` (`repo.py:77-101`, `runs.py:50-62`). One FK (`visits.case_id`), no indexes, no migrations (no alembic).

## 10. Imaging Gaps

- No image viewer of any kind (grep `canvas|dicom|window|slice|zoom` in `frontend/src` → only `String.slice` hits).
- DICOM stored without `StudyInstanceUID`/`SeriesInstanceUID`/modality capture; never decoded at ingest.
- `POST /api/vision/analyze` exists (`api.py:235-243`) but **no UI calls it**, and in Docker it 500s (torch/transformers/PIL absent from `pyproject.toml`).
- Vision model = 2-class zero-shot prompt pair `"malignant pulmonary nodule"` / `"normal lung"` with 0.5 threshold (`vision.py:39-48`) — binary detector, no measurements, no annotations persisted, no provenance.
- No prior-study comparison, no interval growth at imaging level (longitudinal uses manually entered mm only).

## 11. Pathology Gaps

**Status: PLANNED / NON-FUNCTIONAL.** Evidence: no Specimen/IHC/histology entities; `_AGENT_EXPECTS["pathology"] = ("slide_image","slide")` (`swarm.py:40-45`) — neither is ever a modality, so the pathology agent (when activated by a checkbox) permanently reports missing data and still produces an LLM hypothesis from the same notes/radiology context as every other agent (`swarm.py:123-132`). The pathology agent never receives pathology data because none exists in structured form. The modality checkbox `pathology` on case creation (`cases/page.tsx:17`) merely activates the node.

## 12. Molecular Gaps

- VCF parsing → `{gene, chrom, pos, ref, alt}` (`standardize.py:70-102`); no transcript, zygosity, VAF, pathogenicity, assay, specimen, lab, date, pending/failed states.
- `standardized` payload never reaches any agent (see §18).
- PD-L1: 0 hits. No TPS, assay, interpretation.
- No biomarker knowledge base, no guideline linkage, no versioning of biomarker guidance.
- Risk: agents freely assert molecular results in output (observed live — §17).

## 13. Staging Gaps

No T/N/M, no stage group, no clinical vs pathologic stage distinction. Only `_HIGH_RISK` regex `metasta|stage (iii|iv|4)` (`system1.py:11-13`) used for alert priority. Any "Stage III" text in output is unconstrained LLM generation. Required form per mission (T/N/M + evidence per component, else "Stage incomplete") does not exist anywhere. **P1.**

## 14. Longitudinal Gaps

- Visits: date + size_mm + notes only; **no lesion identity** — all measurements pooled into one series (`longitudinal.py:17-24`); two lesions → meaningless trend.
- First-vs-last only; intermediate measurements ignored (`longitudinal.py:34`).
- Same-date edge: `delta>1mm, days=0` → trend "growing" with `rate=0.0` (`longitudinal.py:36-37`) — inconsistent output.
- No treatment episodes, no response/progression semantics, no study linkage, no `observed_at` vs `created_at` distinction anywhere in backend (grep → 0).

## 15. Tumor Board Gaps

`/tumor-board` = case list + AI group chat (`tumor-board/page.tsx`). No shared evidence panel, no human specialist roles, no decision record, no pre-read, no disagreement capture, no sign-off. Mentions (`@radiologist`) address **AI agents**, not people (`group-chat.tsx:28`). Chat context frozen at first message (`chat.py:103-108`) — board can discuss stale state after new uploads. **PARTIAL / misnamed.**

## 16. Evidence / RAG Audit

- Corpus: 40 PubMed abstracts ingested whole-document (no chunking) (`ingest_corpus.py:64-69`); metadata `{year, source, pmid}`; `required_biomarker` filter exists but ingest never writes it (`rag.py:156-162`).
- **Embedder broken across processes**: `HashEmbedder` uses `hash(token)` (`rag.py:18`) — per-process salted; after restart, stored vectors and query vectors live in different spaces → dense half of hybrid retrieval is effectively random. No `PYTHONHASHSEED`. BM25 half still works. Tests pass only because they ingest+query in-process. Tag: **BROKEN.**
- **Rerank silently disabled**: `except Exception: return hits` (`rag.py:135-136`) and `sentence_transformers` not installed → no-op in every environment.
- Query = concatenated agent hypotheses, 1000 chars (`rag.py:167-171`) — not clinical-context-aware (no histology/stage/biomarker/guideline query building).
- No supporting-vs-contradicting evidence search; no evidence-type taxonomy (guideline vs trial vs case report); no guideline versioning (no NCCN document is ingested despite prompt naming NCCN — `swarm.py:341`).
- Citation handling: `explain` passes LLM-generated `literature` strings unvalidated (`swarm.py:400`) → fabricated citations observed in production capture.
- Fail-open: store errors → empty evidence, run continues, calibration reason does not note it (`swarm.py:186-192`).

## 17. Hallucination / Safety Audit

Detail: `docs/SAFETY_AND_HALLUCINATION_AUDIT.md`. Headline findings:

- **No claim-level evidence** anywhere: no node checks that diagnosis/hypothesis text traces to case data or citations. Grep `abstain|unsupported` in `swarm.py` → 0.
- **Observed fabricated output** (captured in `.playwright-mcp/*.yml`): molecular panel `EGFR L858R (VAF 12%) … PD-L1 TPS 30%` and CT bounding boxes from a run where genomics/vision never executed; fabricated author citations `Smith et al., 2023; Johnson & Lee, 2022`.
- Fail-open defaults: self_critic garbage → `aligned: True, warnings: []` (`swarm.py:353,357`); evidence_verify LLM garbage → keep all (`swarm.py:199-219` default `drop: []`); consensus LLM garbage → confidence still displayed from calibration (`swarm.py:304-310`).
- Unclamped confidences: `float(data.get("confidence", 0.5))` (`swarm.py:138`) and debate `float(conf)` (`swarm.py:475`) — non-numeric kills the run; out-of-range passes into calibration.
- **Prompt injection: no defense.** Raw `clinical_notes` (up to 0.5) into prompts (`swarm.py:129`), retrieved corpus text into prompts (`swarm.py:204,299`), chat history re-injected (`chat.py:113-124`). 0 injection tests.
- PII: prompt-side only (GuardedLLM everywhere — good), responses never scrubbed; MRN pattern `\b\d{7,10}\b` can mangle 7-digit PMIDs in prompts (`pii.py:26-31`).

## 18. Agentic AI Audit

Detail: `docs/AGENTIC_AI_AUDIT.md`. Summary:

| Agent | Value verdict |
|---|---|
| radiology | **DECORATIVE-ADJACENT** — one prompt over notes+modalities; never sees imaging data or structured findings (`swarm.py:123-132`); missing-flag key `imaging_findings` never written |
| pathology | **DECORATIVE** — never receives pathology data (none exists); permanently missing-flagged (`swarm.py:40-45`) |
| genomics | **LOW VALUE** — never receives VCF/variants (`standardized` unread); only knows modality presence |
| clinical | **HIGHEST of four** — receives notes (the only real input), but no structured demographics/symptoms |
| rag_evidence | **HIGH VALUE** — real retrieval, honest degradation (`swarm.py:160-192`) |
| evidence_verify | **MEDIUM** — real staleness/biomarker filters, LLM drop is fail-open |
| debate | **MOCKED** — confidence floats only, no claims (`swarm.py:466-470`) |
| consensus | **MEDIUM** — weighted average with real missing penalty; evidence does not affect the number (`swarm.py:89-108`) |
| self_critic | **LOW-MEDIUM** — hint-seeded free list, fail-open (`swarm.py:337-375`) |
| explain | **MEDIUM-HIGH** but unsafe — unvalidated literature (`swarm.py:400`) |
| vision | **UNUSED/BROKEN** — no swarm integration, not runnable in Docker (`vision.py:18-54`) |
| planner tools | **MOCKED** — `plan.tools` has no consumer (`swarm.py:498,583`) |

## 19. Laya Audit

Detail: `docs/LAYA_SYSTEM1_ARCHITECTURE.md`. Current usage: `laya.Router.predict` for 3 modality-presence `noul` questions + 1 risk `choice` (`system1.py:81-144`). Disabled by default (`.env:7`), absent from Docker image, fallback try/except in `get_router` is dead code (`system1.py:149-157` — constructor cannot raise). Reads the **uncalibrated** Laya confidence field (`laya/common.py:289-294` says so) instead of `answer_confidence`, and the value is consumed nowhere. **Not used for**: evidence sufficiency, conflict gating, abstention, tool selection, re-analysis triggers — i.e., every System-1 responsibility from the mission. Latency: `LATENCY_BUDGET_MS = 50` is a dead constant; package itself documents ~200 ms CPU forward pass. Laya is **underused, not wrong**.

## 20. System 1 / System 2 Redesign

Current: System 1 = routing only (presence rules); System 2 = everything else including safety checks it cannot do (self-critique quality fail-open, no final gate).

Target contract (to be enforced, not prompted):

- **System 1 (deterministic + Laya):** intake triage, data-sufficiency scoring, evidence-completeness gate, conflict score, agent/tool selection, abstention decision, re-analysis triggers, final safety gate before report. Structured schema, <50 ms, deterministic fallback.
- **System 2 (LLM):** hypothesis generation, evidence synthesis, explanation — **only over inputs System 1 has approved**, outputs only through claim-validation and abstention gates.

No System-2 output may reach the clinician without passing System-1 validation (claim → source check, confidence bounds, missing-evidence disclosure). Full design in `docs/LAYA_SYSTEM1_ARCHITECTURE.md`.

## 21. Frontend / Physician Workflow Audit

- **No viewer, no annotation, no correction, no rejection, no sign-off.** Run report page has zero action buttons besides "Back to cases" (`runs/[id]/page.tsx:107-113`). HITL features exist only in the prototype `public/swarm.html` ("Physician Override", "Challenge Finding") — PLANNED, not built.
- Run page shows **no patient/case identity** (`runs/[id]/page.tsx:77-99`) — cannot verify which patient's run you read.
- Confidence rendered as `NN.N% Match` with progress bar (`runs/[id]/page.tsx:210-219`) — no calibration caveat, no abstention state.
- "Consensus Diagnosis" header + bold free-text diagnosis with no suspicious/confirmed taxonomy (`runs/[id]/page.tsx:204-220`).
- Cognitive load: flat unbounded list of ≥10 `EventCard`s, no progressive disclosure; `RunResult.reports` declared but never rendered (`runs/[id]/page.tsx:15`).
- **Hardcoded/fake chrome**: `42ms`, `Mesh: 12 Nodes`, `TLS 1.3 / PHI Scrubbed`, notification badge `3` (no onClick), persona "Dr. Sarah Mitchell", agent "ready" statuses, `INTAKE COMPLETE` telemetry, dead header search (`shell.tsx:112,181-197`, `page.tsx:245-265`, `cases/[id]/page.tsx:233`).
- **State leaks**: run events not reset per runId (`useRunStream.ts:13` + seq dedupe `runEvents.ts:18-21` drops new run's events); chat messages not keyed per case (`tumor-board/page.tsx:113` missing `key=`) → cross-patient PHI display. **P0.**
- Logout missing (`clearToken` never called); no RBAC; WS token in URL query (server logs — 8 JWTs found in untracked console logs).

## 22. Backend Architecture Audit

- 17 FastAPI routes + 2 WS; envelope pattern consistent; correct status codes (201+Location, 404/422/429 envelopes).
- Sync LLM calls (`GuardedLLM.complete`) executed inside async nodes (`swarm.py:66-69`) → head-of-line blocking of the event loop; one slow Groq call stalls all concurrent runs and WS heartbeats. No concurrency cap; `asyncio.create_task` without reference (`api.py:231`) — GC risk.
- Single-event-loop bug fixed in `runs.py:32-49` but **still present in `repo.py:70-76`** (single pool per instance) — masked only because tests strip `DATABASE_URL`.
- `notes_addendum` written, never read (`api.py:136`) — uploaded notes never reach the field agents read (`swarm.py:129`). **BROKEN.**
- Last-write-wins merges destroy prior VCF/labs (`repo.py:168`, non-atomic read-modify-write `repo.py:160-177`).
- Missing endpoints: documents list/view, corrections, reports, sign-off, annotations, staging, biomarkers, specimen, demographics, audit read. Admin page lists a non-existent endpoint (`admin/page.tsx:33`).

## 23. Database Audit

3 tables, inline DDL, no migrations, no indexes, one FK, no soft delete, no audit columns (`created_by`/`updated_by`), no `UNIQUE(patient_ref)`, `runs.case_id` no FK. `MemoryRepo` and all chat/run caches are process-globals with no eviction (unbounded growth). Test suite can write to any local Postgres on 5432 without opt-in (`test_postgres.py:23` skip logic vs `conftest.py:22` comment mismatch).

## 24. Security Audit

Detail feeds: security subagent report. Rating: **adequate single-user dev hygiene; unsuitable for multi-clinician PHI.**

- **P0**: known `JWT_SECRET` in compose (tokens forgeable); default admin/admin; zero per-resource authz (any token → every case/run/chat); 80 untracked clinical uploads + 4 committed (`.gitignore` misses `data/uploads/`); frontend cross-patient display bugs (§21).
- **P1**: no audit trail (class exists, unused); WS token in query string (leaks to logs/history); localStorage token, no revocation; uploads no size cap, no content-type check; integrity hash never verified at runtime; `trust_remote_code=True` in vision model load (`vision.py:24-30`); no prompt-injection defense.
- **P2**: no HSTS/CSP; no ingest rate limit; no `Retry-After`; rate limiter ignores `X-Forwarded-For`; validation errors echo input (`main.py:67`).
- **Never claim compliance**: encryption-at-rest and audit claims in UI are FALSE (§4).

## 25. Interoperability Audit

**FUTURE INTEROPERABILITY GAP.** No FHIR resources, no DICOM UIDs, no LOINC/SNOMED/ICD coding anywhere; labs stored as free-text string map. Domain model cannot currently map to Patient/Observation/DiagnosticReport/ImagingStudy/Specimen without the entity work in §9. No fake FHIR claimed in code (only the general "production" rhetoric).

## 26. Performance Audit

- System 1 heuristic: p95 asserted <50 ms in test (`test_system1.py:58`); Laya CPU path documented 193–464 ms (`system1.py:18-19`).
- Run latency: **not measured** — no duration field on runs, no per-node timing, no metrics endpoint. Cost per case: unmeasured. Chat token counts are tracked (`chat.py:154-157`) — the only usage accounting in the system.
- Blocking sync LLM calls on the event loop (§22) is the dominant latency/scalability risk.

## 27. Testing Audit

See §8. Coverage of envelope/routing/mechanics is genuinely good for a prototype (127 tests). Clinical-safety coverage is effectively **zero**: no abstention, isolation, injection, staging, pathology-gating, temporal, or adversarial-output tests. Frontend: 5 pure-function tests, no page tests, no E2E in CI.

## 28. Demo-vs-Real Functionality Audit

**Real**: JWT login, case CRUD, ingest (txt/csv/vcf), LLM graph run with streaming, PII scrub, RAG retrieval (BM25 half), visits math, rate limits, run persistence.

**Mocked/hardcoded/decorative**: debate substance (floats only), planner tools, vision (broken in Docker, unused by UI), `plan.tools`, shell telemetry/notifications/persona, `INTAKE COMPLETE`, admin security checklist, admin endpoint list (includes non-existent route), `public/swarm.html` clinical numbers (81% malignancy, cT1c cN0 cM0, fabricated Lancet citation) — shipped in `public/` though not routed.

**Broken**: PDF ingest (empty), `notes_addendum` path, hash-embedder across restarts, rerank (silent no-op), `get_router` Laya fallback (dead), `repo.py` per-loop pool, run-event state reset, chat message keying, `float()` confidence coercion (run-killer), same-date progression edge, vision endpoint in container.

**Demo contamination**: DEMO-001 is docs-only (0 backend hits); no seed endpoint; no cross-case leakage found in backend keys (all keyed by case_id/run_id) — but frontend display bugs (§21) and globally shared chat history/context undermine that isolation at the UI layer.

## 29–32. Prioritized Issues

**P0 — Safety / Clinical Integrity**

1. Fabricated clinical claims (molecular, bounding boxes, citations) can reach clinicians; no output-side validation (§17, GAP-001).
2. No abstention: diagnosis always renders with a percentage; missing pathology never blocks (§2, GAP-002).
3. Frontend cross-patient state leaks + no patient identity on run report (§21, GAP-003).
4. Known JWT secret + admin/admin + zero per-resource authz + unignored clinical uploads (§24, GAP-014).
5. UI presents AI output as "Consensus Diagnosis NN% Match" without suspicious/confirmed taxonomy or provenance (§21, GAP-015).

**P1 — Core Clinical Capability**

6. No structured pathology/IHC/histology workflow (§11, GAP-004).
7. No staging representation with evidence (§13, GAP-007).
8. No structured biomarker/PD-L1 model (§12, GAP-006).
9. Data model lacks Patient/Specimen/Study/Document entities; notes uploads dead-end (§9, §22, GAP-005).
10. Debate is not a debate; self-critic fail-open; confidence cosmetic (§18, GAP-008).
11. Laya underused; no System-1 safety gates; planner tools decorative (§19–20, GAP-009).
12. RAG: broken dense retrieval across restarts, no context-aware querying, no guideline versioning, unvalidated citations (§16, GAP-010).
13. Longitudinal: no per-lesion model, no treatment/prior-cancer (§14, GAP-011).

**P2 — Clinical Productivity**

14. No imaging viewer / DICOM model; vision unreachable (§10, GAP-012).
15. No report builder, sign-off, provenance display, physician correction (§21, GAP-013).
16. No document versioning/amendment/duplicate handling (§7, GAP-016).
17. No prompt-injection defense or tests (§17, GAP-017).
18. Audit logging implemented but unused (§24, GAP-018).
19. Tumor board lacks decision record/roles (§15, GAP-019).

**P3 — Optimization / P4 — Research**

20. Metrics/observability, latency instrumentation, cost tracking (§26).
21. FHIR/DICOM full interoperability (§25).
22. Model/prompt/corpus versioning per run (reproducibility, GAP-020).
23. Knowledge-update pipeline for guidelines (research/future).
24. Remove dead code (`_PHONE`, `LATENCY_BUDGET_MS`, `case_has_data`, RippleTrace skills leftovers, admin phantom endpoint).

## 33. Recommended Architecture

Move from `Documents → Agents → LLM → Diagnosis` to the mission's target pipeline: Patient/Clinical Context → Multimodal Evidence → Data Quality Gate → **System 1 (Laya) control plane** (know/don't-know, agent+tool selection, parallelization, conflict score, verification requirement, abstention gate) → Specialist Agents over **typed inputs only** → Evidence Retrieval + Verification (source, freshness, contradictions, claim grounding) → Debate only when conflict-real → Consensus (evidence-aware) → Self-Critique (claim-specific) → **System 1 final safety gate** → Uncertainty + "What would change this?" → Physician Review → signed report → Longitudinal Memory. Full spec: `docs/LAYA_SYSTEM1_ARCHITECTURE.md`, phased in §37.

## 34. Recommended Clinical Workflow

Conditional, stage-aware: intake triage classifies where the patient is on the pathway (suspicion → imaging → tissue decision → pathology → molecular → staging → MDT → follow-up) and the system only offers conclusions the current stage supports. Missing next-step evidence surfaces as an explicit "what would resolve this" checklist, not a confidence penalty.

## 35. Recommended Laya Architecture

See `docs/LAYA_SYSTEM1_ARCHITECTURE.md`: Laya as fast control plane (state estimation, sufficiency, routing, conflict scoring, abstention, re-run triggers) + deterministic fallback with identical schema; measured latency budget; never a diagnostic authority; final safety gate before clinician.

## 36. Recommended Agent Architecture

Each agent gets: typed input contract (e.g. radiology → structured findings + DICOM-derived measurements; pathology → specimen+IHC), structured output schema (`hypotheses, observations, evidence, missing_information, contradictions, confidence, abstain`), declared reliability metadata, human reviewer, and a downstream consumer that actually uses its output. See `docs/AGENTIC_AI_AUDIT.md` for per-agent recommendations.

## 37. Implementation Roadmap

**Phase A — Clinical Safety Foundation (must fix before clinical demo)**
Output claim validation + abstention states + provenance tagging; fix frontend leaks + patient identity on run page; remove/repair fake UI claims; secure secrets/authz baseline; stop ignoring `notes_addendum`; confidence bounds & semantics; fail-closed critic defaults.

**Phase B — Clinical Completeness (before advanced demo)**
Patient/demographics; pathology+IHC+histology; staging with evidence; biomarker/PD-L1 model; document versioning + PDF parsing; per-lesion longitudinal; DICOM study/series + minimal viewer; context-aware evidence query + guideline versioning.

**Phase C — Agentic Intelligence (before pilot)**
Laya control plane per contract; real debate (claims, not floats); claim-specific self-critique; contradiction engine; re-analysis triggers; planner tools wired or removed; typed agent input/output contracts.

**Phase D — Physician Workflow**
Report builder with sections from structured data; sign-off with who/when/what changed; source-document viewer with click-to-source; correction/rejection/override; real tumor-board decision record; timeline from structured events.

**Phase E — Enterprise Readiness**
RBAC + per-case authorization; audit trail activated; metrics/observability; migrations/indexes; FHIR path; performance (async LLM); tenant isolation; knowledge-update pipeline; model/prompt/corpus versioning.

## 38. Acceptance Criteria (exemplars — full set in CLINICAL_GAP_REGISTER.md)

Example for abstention (GAP-002): *A case with no pathology data cannot display "Consensus Diagnosis"; the UI shows "Cannot establish histologic diagnosis — pathology unavailable", lists what is known/unknown and what evidence would resolve it; automated test feeds a no-pathology case and asserts the abstention state and absence of a confidence percentage; confidence floor of 0 displayed only when evidence exists.*

Example for provenance (GAP-015): *Every statement in the report carries [SOURCE: document] / [AI INFERENCE] / [PHYSICIAN INPUT] / [EXTERNAL EVIDENCE]; clicking opens the source; test asserts no unattributed claim renders.*

## 39. Open Questions

1. Intended deployment: single-investigator research tool or multi-clinician hospital system? (Authz scope differs fundamentally.)
2. Is Groq free tier the target runtime LLM? (Rate-limit failure mode then becomes common, not edge.)
3. Which guideline corpus is licensed/usable? (NCCN is prompted but not ingested; licensing matters.)
4. Is BiomedCLIP actually required, or should vision be cut until a real imaging pipeline exists?
5. Target PACS/viewer integration (OHIF/dcm4chee) vs in-app minimal viewer?
6. Regulatory posture: is this intended as research-only decision support? (Determines how aggressively §29 P0s gate development.)
7. Laya: GPU available in target deployment? (CPU 193–464 ms vs budget 50 ms.)

## 40. Final Readiness Assessment

```
CLINICAL WORKFLOW:   Not modeled — linear "upload → diagnose" only; conditional pathway absent
DATA:                3 tables (Case/Visit/Run); no Patient/Specimen/Staging/Biomarker/Document entities
MULTIMODAL:          PARTIAL — ingest accepts files; nothing reasons over imaging/pathology content;
                     standardized payload unread by agents
PATHOLOGY:           PLANNED / NON-FUNCTIONAL — agent name + checkbox only
STAGING:             MISSING — regex keyword heuristic only
MOLECULAR:           PARTIAL — VCF gene rows only; no interpretation, no PD-L1; agents fabricate freely
LONGITUDINAL:        PARTIAL — pooled size series, no per-lesion/treatment/prior-cancer
EVIDENCE:            PARTIAL — real corpus + filters, broken dense retrieval, no claim grounding,
                     no guideline versioning, unvalidated citations
AGENTIC:             Real graph, thin agents; debate mocked; planner tools decorative; vision unused
LAYA:                IMPLEMENTED, DISABLED, UNDERUSED — routing-only, off by default, absent in image
SAFETY:              Prompt-side PHI scrub strong; no abstention, no output validation, no injection
                     defense, fail-open critic
HUMAN OVERSIGHT:     ESSENTIALLY ABSENT — no correction/rejection/sign-off/annotation; HITL only in mock HTML
SECURITY:            Dev-grade — known secrets, admin/admin, no authz, no audit, PHI uploads not ignored
INTEROPERABILITY:    MISSING — no FHIR/DICOM UIDs/coding systems
PERFORMANCE:         Unmeasured; sync LLM calls block event loop
TESTING:             Strong mechanics (127 tests), near-zero clinical-safety coverage

CURRENT PRODUCT MATURITY: Research prototype
(nearest next tier: "Advanced research system" once Phase A safety work lands;
 "Clinical-demo ready" requires Phase A + B)
```

## The Most Important Question

**If you removed the words "agentic AI" from the product, would a doctor still find KANser genuinely useful?**

**Not yet — but it is close to useful in three concrete places.** What survives the removal test today: (1) a single screen that streams structured progress of a multi-step analysis with evidence citations instead of a black box; (2) the evidence search with staleness/biomarker rejection — a real literature-organizing tool; (3) longitudinal size tracking with trend/growth/doubling math. Everything else — the four specialist agents, the debate, the tumor-board chat — currently adds little a physician could not get from the same notes plus a search engine, because the agents do not see any data type they are named for, the debate passes only numbers, and the output carries unverifiable claims. The *scaffolding* for indispensability is real; the clinical middle layer is not built.

**The 10 changes that would make KANser genuinely indispensable, ranked by clinical importance and dependency:**

1. **Claim-level grounding + abstention** (no unsupported claim renders; "insufficient evidence" is a first-class state) — everything else is unsafe without it.
2. **Provenance on every report statement** with click-to-source — turns output from assertion into auditable reasoning.
3. **Structured pathology + IHC + histology model** (specimen → adequacy → morphology → dx → IHC) — the diagnostic gold standard the current graph skips.
4. **Staging representation with per-component evidence** ("Stage incomplete" instead of invented Stage III).
5. **Structured biomarker/PD-L1 model with assay/specimen/date/pending states** — drives modern NSCLC decisions.
6. **Physician review loop** — correct/reject/annotate/override/sign-off with audit trail; the doctor stays final decision-maker.
7. **Patient + longitudinal model** (demographics, per-lesion tracking, treatment episodes, prior cancer) — makes the system a chart, not a form.
8. **Document reality**: PDF parsing, versioning (preliminary/final/amended), duplicate handling, notes actually reaching agents.
9. **System-1 control plane (Laya)** per contract: sufficiency gate, conflict-triggered debate, final safety gate, deterministic fallback — fewer wasted LLM calls and no unsupported downstream reasoning.
10. **Fix the trust surface**: frontend leak fixes + patient identity, secure secrets/RBAC/audit, remove hardcoded UI claims, clinical-safety test suite (abstention, injection, isolation, adversarial output).

Dependencies: 1 blocks 2–5; 3–5 block 6 content; 7 blocks full 6+8; 9 depends on 1's schemas; 10 runs in parallel but gates any external demo.

---

*Audit method: full read of backend app/tests, frontend src, Docker/config; four independent deep-audit passes (agents/LLM/RAG, data model/ingestion, frontend workflow, security/tests) synthesized here; live production captures reviewed as evidence of model output behavior. Read-only: no product code was modified.*
