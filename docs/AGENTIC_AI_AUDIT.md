# KANser — Agentic AI Audit

Companion to `docs/CLINICAL_REALITY_AUDIT.md`. One row per agent/component. Status vocabulary: **IMPLEMENTED** (code + tests + live), **PARTIALLY IMPLEMENTED**, **MOCKED** (looks functional, output not real), **HARDCODED**, **UNUSED** (exists, no consumer), **BROKEN**, **UNTESTED**, **PLANNED**, **MISSING**.

---

## 1. Component matrix

| Component | Backend location | Frontend surface | Tests | Status | Notes |
|---|---|---|---|---|---|
| Radiology agent | `swarm.py:118-158` (`AGENT_NODES`) | `/swarm`, run timeline | `test_swarm.py` | PARTIALLY IMPLEMENTED | Same generic prompt as every agent (`swarm.py:123-130`); no image input; expects `dicom_scan`/`imaging_findings` (`swarm.py:41`) never present |
| Pathology agent | same node factory | `/swarm`, cases checkbox | same | BROKEN (non-functional) | Expects `slide_image`/`slide` (`swarm.py:42`) — keys never written; receives notes text only; no Specimen/IHC entities anywhere |
| Genomics agent | same node factory | `/swarm` | same | PARTIALLY IMPLEMENTED | Expects `vcf_file`/`vcf` (`swarm.py:43`); VCF parsed only if uploaded as file metadata (`api.py:132-134`); no structured biomarker model |
| Clinical agent | same node factory | `/swarm` | same | PARTIALLY IMPLEMENTED | Expects `labs_panel`/`labs` (`swarm.py:44`); labs parsed only when CSV uploaded (`api.py:129-131`) |
| System 1 router | `system1.py:60-184` | `POST /cases/{id}/routing`, alerts | `test_system1.py` | PARTIALLY IMPLEMENTED | Heuristic default; Laya path off (`.env`), see Laya doc |
| Planner (System 1.5) | `planner.py:59-85` | `POST /cases/{id}/diagnose` (inside graph) | `test_planner.py` | PARTIALLY IMPLEMENTED | `Plan.tools` (`planner.py:16,45`) serialized to state (`swarm.py:583`) — **no consumer; UNUSED** |
| RAG retrieval | `rag.py:105-198` | `/evidence`, run citations | `test_rag.py` | PARTIALLY IMPLEMENTED / BROKEN dense path | `HashEmbedder` uses `hash(token)` (`rag.py:18`) — process-salted; embeddings invalid after restart. BM25 path works. `rerank` silent no-op when `sentence_transformers` absent (`rag.py:135-136`) |
| Evidence verify | `swarm.py:194-244` | run event stream | `test_swarm.py` | IMPLEMENTED (LLM-gated) | freshness >5yr + `required_biomarker` filter (`rag.py:144-164`); relevance drop via LLM (`swarm.py:200-217`) |
| Fusion / calibration | `swarm.py:89-108,246-271` | `calibration` event | `test_swarm_upgrades.py` | IMPLEMENTED but weak | weights hardcoded (`swarm.py:47`); confidence is LLM self-report (`swarm.py:138`); evidence count only appended to `reason` (`swarm.py:101-102`) |
| Debate | `swarm.py:464-490` | run timeline | `test_swarm_upgrades.py` | MOCKED | prompt receives `{agent: confidence}` floats only — **hypotheses stripped**; single LLM call rewrites numbers; cannot alter diagnosis |
| Consensus | `swarm.py:273-335` | Reasoning Inspector | `test_swarm.py` | IMPLEMENTED (ungated) | LLM picks diagnosis string; `_parse` fallback `"unresolved"` (`swarm.py:304`); no abstention |
| Self-critic | `swarm.py:337-375` | warnings panel | `test_swarm_upgrades.py` | IMPLEMENTED, fail-open | default `{"warnings": [], "aligned": True}` (`swarm.py:351-357`) on parse failure — model failure renders as "guideline aligned" |
| Explain | `swarm.py:377-419` | Clinician/Patient tabs | `test_swarm.py` | IMPLEMENTED (no validation) | `literature` = LLM-supplied strings, whitelist only if list empty (`swarm.py:400`) — fabricated citations pass |
| Vision | `vision.py` | `POST /vision/analyze` | `test_vision.py` | UNUSED / BROKEN in Docker | Not called by graph or UI; torch/transformers/PIL absent from image → 500 in container; `trust_remote_code=True` (`vision.py:29`); 2-class zero-shot threshold 0.5 (`vision.py:48`) |
| Data standardization | `standardize.py` | ingest response `standardized` | `test_standardize.py`, `test_ingest_standardize.py` | PARTIALLY IMPLEMENTED | `swarm.py` puts payload in `state["standardized"]` (`swarm.py:561`) — **no node reads it**; labs/VCF parsers work; PDF → empty text (`api.py:104-107`) |
| Group chat | `chat.py` | `/tumor-board` `GroupChat` | `test_chat.py` | IMPLEMENTED (stale-context bug) | `_ensure_context` builds once (`chat.py:103-108`); `filter_evidence` not applied to chat RAG hits (`chat.py:86-90`) |
| Longitudinal | `longitudinal.py` | `/longitudinal` | `test_visits.py` | PARTIALLY IMPLEMENTED | pooled single series (`longitudinal.py:17-24`); first-vs-last only; same-date edge → `rate 0.0` (`longitudinal.py:36`) |
| PII guard | `pii.py` | inside `GuardedLLM` | `test_security.py` | IMPLEMENTED | scrub before LLM egress (`swarm.py:59-69`) |
| Audit log | `security.py:43-78` | — | `test_security.py` | UNUSED | `AuditLog` never instantiated; `audit_path` unread (`main.py`) |
| AES/integrity utils | `security.py:10-40` | — | `test_security.py` | UNUSED | no encryption-at-rest caller |
| Alerts | `api.py:296-319` | `/alerts` | `test_production_api.py` | IMPLEMENTED | failed runs + high-risk regex (`system1.py:11-16`) |
| Report builder / sign-off | — | — | — | MISSING | no Report entity, no override buttons (prototype-only in `public/swarm.html`) |
| Patient/Document/Specimen/Study | — | — | — | MISSING | only `cases`, `visits`, `runs` tables |
| Biomarker/PD-L1 model | — | — | — | MISSING | grep `pdl1|PD-L1` backend → 0 |
| Staging (T/N/M) | — | — | — | MISSING | grep `stage` → only risk regex (`system1.py:11`) |
| DICOM viewer | — | — | — | MISSING | grep `canvas|slice` in frontend → 0 |
| Report/provenance display | — | — | — | MISSING | grep `provenance|source:` frontend → 0 |

---

## 2. Per-agent detail

### 2.1 Radiology
- **Input:** `modalities`, `metadata`, `clinical_notes` text (`swarm.py:120-129`). No pixels, no DICOM, no findings object.
- **Output:** `{"hypothesis", "confidence"}` (`swarm.py:135-140`). No structured findings, no bounding boxes produced — yet live outputs claim boxes (see Safety doc, evidence `page-2026-09-24T20-00-05-964Z.yml`).
- **Missing-flag:** always `dicom_scan` unless `metadata.dicom_scan` or `ct`/`cxr` in modalities (`swarm.py:50-56`) — flag text only, no functional effect on confidence beyond generic `-0.05` penalty.

### 2.2 Pathology
- Expects `slide_image`/`slide` (`swarm.py:42`) — never written by any ingest path → permanent `missing_flags: ["slide_image"]`.
- On case with `pathology` modality checked (`cases/page.tsx`), agent still receives only clinical notes. **Status: PLANNED / NON-FUNCTIONAL.** Full gap: GAP-004.

### 2.3 Genomics
- VCF upload → `metadata.vcf` (`api.py:132-134`) → `parse_vcf` (`standardize.py:70-102`) extracts `{gene, chrom, pos, ref, alt}`.
- Agent prompt does not include parsed variants — only `Modalities available` + notes (`swarm.py:127-129`). Genomics facts reach the model only if typed into notes. Output typed as free `hypothesis` string → biomarker claims unconstrained (GAP-001/006).

### 2.4 Clinical
- Labs CSV → `metadata.labs_raw` (`api.py:129-131`) → `parse_labs` (`standardize.py:36-67`) — but prompt includes notes only. Same gap as genomics.

---

## 3. Multi-agent orchestration

- Graph: `fan_out → [agents ∥ rag_evidence] → evidence_verify → fusion_stages → (debate | consensus) → self_critic → (debate | explain)` (`swarm.py:436-459`).
- Conflict gate: spread ≥ 0.3 between any two agent confidences (`swarm.py:80-82`), max 3 debate rounds (`swarm.py:422-429`).
- Critic feedback: warnings present → one more debate round (`swarm.py:431-434`).
- Debate content: **confidence floats only** — the debate cannot see or revise any hypothesis (`swarm.py:464-470`). Orchestrated disagreement is theatrical.

## 4. Agentic-layer verdict

| Question | Answer |
|---|---|
| Do agents have distinct inputs? | No — one shared prompt template (`swarm.py:123-130`) |
| Do agents have distinct output schemas? | No — identical `hypothesis/confidence` |
| Do agents fail closed when data missing? | No — missing flag logged; agent still opines; confidence floor 0.01 (`swarm.py:97`) |
| Does debate change outcomes? | No — sees only numbers |
| Is any claim validated before display? | No |
| Is the tool plan executed? | No — `plan.tools` written, never read |
| Is vision reachable? | No |
| Overall | **Research prototype with a well-shaped graph skeleton; the clinical specialization layer is largely PLANNED.** |
