# KANser — Clinical Workflow Matrix

Companion to `docs/CLINICAL_REALITY_AUDIT.md`. Real-world lung cancer workflow steps vs implemented capability.
Status: **IMPLEMENTED / PARTIAL / MOCKED / HARDCODED / UNUSED / MISSING / BROKEN**.

---

## A. Intake & history

| # | Workflow step | Status | Evidence |
|---|---|---|---|
| A1 | Create case with patient reference | IMPLEMENTED | `POST /api/cases` (`api.py:55-61`), `/cases` form (`cases/page.tsx:63`) |
| A2 | Patient identity as structured record | MISSING | free-text `patient_ref` only; no Patient table (`repo.py:77-101`) |
| A3 | Demographics: age, sex, smoking, pack-years, exposures | MISSING | grep `smoking|pack_year|age` backend → 0 |
| A4 | Symptoms with onset/duration/progression | MISSING | notes free text only |
| A5 | Prior malignancy / family history / comorbidities | MISSING | 0 hits |
| A6 | Performance status | MISSING | 0 hits |
| A7 | Duplicate-patient detection | MISSING | no patient key to match on |
| A8 | Clinical notes upload | PARTIAL | `api.py:135-137` writes `notes_addendum` — **never read by any consumer** (grep `notes_addendum` → 1 write hit) |
| A9 | Document list / version / re-open | MISSING | no Document entity; files write-only on disk (`api.py:90-99`) |
| A10 | Duplicate upload detection | PARTIAL | SHA-256 stored (`api.py:93-99`) but never compared → no dedup |

## B. Imaging workup

| # | Workflow step | Status | Evidence |
|---|---|---|---|
| B1 | CT/CXR upload | PARTIAL | accepted (`standardize.py:24-25`), stored, **not linked to case** (`api.py:123-139` — only labs/genomics/notes branch) |
| B2 | DICOM metadata (Study/Series/SOP UIDs, modality, date) | MISSING | raw bytes only; grep `StudyInstanceUID` → 0 |
| B3 | Viewer: slices, window/level, zoom, pan | MISSING | no canvas/viewer code in `frontend/src` |
| B4 | Measurement (RECIST), nodule size tracking | MISSING | only manually entered visit `size_mm` (`Visits`) |
| B5 | AI detection overlay on image | MISSING | vision never renders; annotations not persisted |
| B6 | Radiologist reads report as text | MISSING | PDF/radiology report → `classify_file` says `notes` (`standardize.py:31`) → text parse fails for PDF (`api.py:104-107`) → empty |
| B7 | AI image analysis | MOCKED/UNREACHABLE | `POST /vision/analyze` (`api.py:235-243`) not called by UI/graph; deps absent in image → 500 in Docker |

## C. Tissue diagnosis (pathology)

| # | Workflow step | Status | Evidence |
|---|---|---|---|
| C1 | Specimen entity (site, procedure, adequacy) | MISSING | 0 hits |
| C2 | Histologic classification (NSCLC/SCLC/subtype) | MISSING as data | only free-text LLM hypothesis (`swarm.py:135-140`) |
| C3 | IHC panel (TTF-1, Napsin A, P40, CK7…) | MISSING | grep `TTF|napsin|p40|ihc` backend → 0 |
| C4 | Pathology PDF parse (report) | BROKEN | PDF → UnicodeDecodeError → `text=""` (`api.py:104-107`); no PDF lib in deps |
| C5 | Pathology agent consumes path data | BROKEN | expects `slide_image`/`slide`, never written (`swarm.py:42`); same notes prompt as others |
| C6 | Pathologist identity / verification | MISSING | 0 hits |
| C7 | Preliminary vs final vs amended report | MISSING | no version states (grep `amended|superseded` → 0) |
| C8 | Slide imaging / whole-slide | MISSING | no ingestion path |

## D. Molecular profiling

| # | Workflow step | Status | Evidence |
|---|---|---|---|
| D1 | VCF upload + parse | IMPLEMENTED (shallow) | `parse_vcf` (`standardize.py:70-102`) → `{gene,chrom,pos,ref,alt}` |
| D2 | Variant interpretation (pathogenicity, VAF, transcript) | MISSING | 0 hits |
| D3 | Assay/lab/specimen/date/pending/failed states | MISSING | 0 hits |
| D4 | PD-L1 TPS | MISSING | grep `pdl1|PD-L1|tps` → 0 backend |
| D5 | EGFR/ALK/ROS1/KRAS/BRAF/MET/RET/NTRK panel result | MISSING as structured data | free-text only; **live runs fabricate results** (Safety doc §3) |
| D6 | Second VCF/lab upload appended, not overwritten | BROKEN | `merge_case` replaces `vcf` wholesale (`repo.py` last-write-wins) |
| D7 | Genomics agent receives parsed variants | MISSING | prompt shows modalities+notes only (`swarm.py:127-129`) |

## E. Staging

| # | Workflow step | Status | Evidence |
|---|---|---|---|
| E1 | Clinical TNM capture | MISSING | grep `T-stage|N-stage|M-stage|tnm` → 0 |
| E2 | Pathologic stage | MISSING | as above |
| E3 | Stage group derivation with evidence | MISSING | 0 hits |
| E4 | SCLC vs NSCLC staging systems distinct | MISSING | 0 hits |
| E5 | Stage displayed from evidence, not generation | MISSING | stage strings only possible via LLM free text (ungated) |
| E6 | Risk triage "high/medium/low" | IMPLEMENTED (regex) | `_HIGH_RISK`/`_MED_RISK` (`system1.py:11-16`) — keyword triage, not staging |

## F. Multidisciplinary discussion

| # | Workflow step | Status | Evidence |
|---|---|---|---|
| F1 | Tumor board room (case list + chat) | IMPLEMENTED | `/tumor-board` |
| F2 | Address agents by specialty (`@radiology` …, `@all`) | IMPLEMENTED | `resolve_targets` (`chat.py:38-44`); E2E verified |
| F3 | Human roles (pulmonology, radiology, pathology, oncology…) | MISSING | mentions map to AI agents only |
| F4 | Shared evidence panel (imaging + path + molecular side-by-side) | MISSING | single chat column |
| F5 | Decision record (impression, stage, plan, owner, follow-up) | MISSING | 0 hits |
| F6 | Meeting minutes / export | MISSING | 0 hits |
| F7 | Patient identity shown in chat | PARTIAL | `patient_ref` header exists (`tumor-board/page.tsx:93`) but **chat body is not keyed per case** (`tumor-board/page.tsx:113` — no `key={active.id}`) → prior case messages persist |
| F8 | Context refresh after new upload/run | BROKEN | `_ensure_context` builds once per case, never invalidated (`chat.py:103-108`) |

## G. Longitudinal follow-up

| # | Workflow step | Status | Evidence |
|---|---|---|---|
| G1 | Visits with date + size | IMPLEMENTED | `POST /cases/{id}/visits` (`api.py:178-189`) |
| G2 | Growth trend / doubling time | IMPLEMENTED (pooled) | `progression` (`longitudinal.py:11-47`); E2E: +3 mm, 11.6 d |
| G3 | Per-lesion tracking | MISSING | single pooled series (`longitudinal.py:17-24`) |
| G4 | Treatment episodes (surgery, chemo, RT, immunotherapy) | MISSING | 0 hits |
| G5 | Response assessment (iRECIST) | MISSING | 0 hits |
| G6 | Prior cancer history | MISSING | 0 hits |
| G7 | `observed_at` vs record `created_at` | MISSING | only visit date; grep `observed_at` → 0 |
| G8 | Date validation (future dates, ordering) | MISSING | `date.fromisoformat` only (`longitudinal.py:5-8`) |
| G9 | Same-date measurements edge | BROKEN | `days == 0` → `rate 0.0` with nonzero delta (`longitudinal.py:36`) |

## H. Reporting & sign-off

| # | Workflow step | Status | Evidence |
|---|---|---|---|
| H1 | Run report view | IMPLEMENTED | `/runs/[id]` |
| H2 | Clinician / patient explanation views | IMPLEMENTED | tabs (`runs/[id]/page.tsx:224-243`) |
| H3 | Confidence display | IMPLEMENTED, unsafe | `NN% Match` bar (`runs/[id]/page.tsx:210-219`) — no taxonomy, no abstention |
| H4 | Claim provenance (`[SOURCE]` tags) | MISSING | grep `provenance` → 0 |
| H5 | Physician accept / reject / correct an AI finding | MISSING (prototype only) | buttons only in `public/swarm.html` |
| H6 | Sign-off with who/when/what changed | MISSING | 0 hits |
| H7 | Versioned report (v1 superseded by v2) | MISSING | 0 hits |
| H8 | Export (PDF/print) | MISSING | 0 hits |
| H9 | Citation list from run | IMPLEMENTED (unvalidated) | `evidence` panel (`runs/[id]/page.tsx:278-299`); IDs come from LLM-writable `literature` (`swarm.py:400`) |

## I. Safety & governance (cross-cutting)

| # | Capability | Status | Evidence |
|---|---|---|---|
| I1 | AuthN (JWT) | IMPLEMENTED | `auth.py:20-36`; admin/admin default (`auth.py:40-41`) |
| I2 | AuthZ (per-case/role) | MISSING | any token → all cases (`api.py:64,69,296`) |
| I3 | PHI scrub before LLM | IMPLEMENTED | `GuardedLLM` (`swarm.py:59-69`) |
| I4 | Prompt-injection defense | MISSING | raw notes into prompts (`swarm.py:129`); 0 injection tests |
| I5 | Audit trail of PHI access | IMPLEMENTED code, UNUSED | `AuditLog` (`security.py:43-78`) never instantiated |
| I6 | Rate limiting | IMPLEMENTED | global 60/min, diagnose 5/min (`api.py:291`, `limits.py`) |
| I7 | Output validation / abstention | MISSING | see Safety doc |
| I8 | Secrets from env | PARTIAL | `docker-compose.yml:27` commits `JWT_SECRET: change-me-32-bytes-min-in-prod` |
| I9 | Model/prompt/corpus versioning per run | MISSING | runs store result only (`runs.py:50-62`) |
| I10 | FHIR / coding systems | MISSING | 0 hits |

---

## Summary counts

| Status | Steps |
|---|---|
| IMPLEMENTED | A1, D1, E6, F1, F2, G1, G2, H1, H2, H3†, H9*, I1*, I3, I5‡, I6 (15 rows) |
| PARTIAL | A8, A10, B1, F7, I8 (5 rows) |
| BROKEN | C4, C5, D6, F8, G9 (5 rows) |
| MISSING | 48 of 74 rows |
| MOCKED/UNREACHABLE | B7, debate (see Agentic audit), safety chrome (Safety doc §6) |

\* unvalidated / default creds · † implemented but unsafe (no taxonomy/abstention) · ‡ code present, never instantiated · B6 counted MISSING (status) though evidence describes BROKEN behavior.

**Bottom line:** the platform reliably does case CRUD, visit trends, group chat with AI agents, run orchestration, and evidence search. Every step that requires a real clinical *artifact* — patient record, imaging study, pathology report, molecular report, staging, decision record, signed report — is MISSING or BROKEN.
