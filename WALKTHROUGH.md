# Kanser — End-to-End Walkthrough

Full journey: start stack → login → create case → preview routing → upload file → diagnose → live timeline → report with evidence citations.

## Start

```powershell
docker compose up -d --build
```

| Service | URL / port |
|---------|-----------|
| Web UI  | http://localhost:3000 |
| API     | http://localhost:8000 |
| Postgres| localhost:5433 (user/pass/db: `kanser`) |

Health check: `http://localhost:8000/api/health` → `{"data":{"status":"ok",...}}`

> Only `kanser-*` containers belong to this project. Never touch `rippletrace-*`.

## 1. API keys (real LLM verdicts)

Create `.env` in repo root (never commit):

```ini
GROQ_API_KEY=gsk_your_key_here
# optional: GROQ_MODEL=openai/gpt-oss-120b   (default already set)
```

- Docker: compose `env_file` injects it into the api container automatically.
- Local dev: `app/main.py` loads `.env` via python-dotenv at startup.
- Verify: `docker compose exec api python -c "import os; print(len(os.environ.get('GROQ_API_KEY','')))"` → key length > 0.
- Available models for your key: query `GET https://api.groq.com/openai/v1/models` with the key. Default `openai/gpt-oss-120b` works.
- Without a key: verdict falls back to `Insufficient evidence - local fallback` with warning `external LLM unavailable; verdict unverified`.

## 2. Login

1. Open http://localhost:3000 → redirects to `/login`.
2. Credentials: **admin / admin** (override via `ADMIN_USER` / `ADMIN_PASSWORD` env).
3. JWT stored in localStorage. If you get 401s after changing `JWT_SECRET`, clear site data to force re-login.

## 3. Create a case

1. Go to **Cases** → **New case** form.
2. Sample values:

| Field | Sample value |
|-------|--------------|
| Patient ref | `DEMO-001` |
| Modalities | `ct`, `notes` (checkboxes) |
| Clinical notes | `55yo ex-smoker. 2.1 cm spiculated solid nodule RUL found on screening CT. Recommend PET-CT and tissue biopsy.` |

3. Submit → case detail page opens.

## 4. Preview routing

Click **Preview routing**. Expected (heuristic provider, <1 ms):

- `activated: ["radiology", "clinical"]`
- `dropped: ["pathology", "genomics"]`
- `risk_grade: "medium"`, `priority: 2`

Routing derives from modality presence — add `pathology` modality to activate it.

## 5. Upload a study file

1. **Choose File** → pick `sample-ct-report.txt` (repo root):

   ```
   CT Chest report: 2.1 cm spiculated solid nodule, right upper lobe. No acute infiltrate. Recommend PET-CT and biopsy per lung nodule guideline.
   ```

2. Expected message: `Uploaded sample-ct-report.txt (sha256 a020383...)`.

## 6. Diagnose

Click **Diagnose** → navigates to `/runs/{run_id}`.

Expected live timeline (streams over WebSocket, arrives in seconds — each completed step shows its `detail` line underneath, see section 8):

```
clinical · completed · 0.86        + hypothesis text
radiology · completed · 0.86       + hypothesis text
rag_evidence · completed · 5 hits      ← real ChromaDB corpus
evidence / evidence_verify
debate · round 1                   + adjusted={"clinical": 0.78, ...}
consensus · completed              + "Primary non-small cell lung cancer (0.92)"
self_critic · completed            + alternative conditions (granuloma, TB, ...)
explain · completed                + full clinician explanation
run_completed
```

Then the **Report** card appears:

- **Verdict**: real Groq diagnosis + confidence (e.g. `Primary non-small cell lung cancer (NSCLC)`, 0.92).
- **Warnings**: self-critic differentials (10+ items).
- **Evidence**: 5 unique PubMed citations, e.g. `pmid:42657018 (2026)` — corpus = 40 PubMed abstracts in `backend/data/chroma`.
- Toggle **Clinician / Patient** to switch explanation wording.

Without `GROQ_API_KEY`: verdict `Insufficient evidence - local fallback`, warning `external LLM unavailable; verdict unverified` (see section 1).

## 7. Back to cases

**← Back to cases** → list shows `DEMO-001` with modalities and date. Reopen any time; **Diagnose** can run again.

## 8. Agent timeline (behind the scenes)

Each `agent_step` in the timeline carries a `detail` line showing what the node actually did:

| Node | Detail shows |
|------|--------------|
| `clinical` / `radiology` / ... | agent hypothesis text + confidence |
| `rag_evidence` | hit count |
| `debate` | reweighted confidences, e.g. `adjusted={"clinical": 0.78, "radiology": 0.78}` |
| `consensus` | final diagnosis + confidence |
| `self_critic` | alternative conditions flagged (granuloma, pneumonia, ...) |
| `explain` | full clinician explanation (bounding boxes, molecular profile, citations) |

With `GROQ_API_KEY` set, expect a real verdict (e.g. `Primary non-small cell lung cancer (NSCLC)` @ 0.92) and 10+ self-critic warnings instead of the local-fallback text.

## Rate limits (important for testing)

- Global: **60 req/min** per IP; `POST /api/simulate`-style heavy route: diagnose **5/min**.
- Hammering buttons/polls → HTTP 429 with `Retry-After`. Wait ~60 s and retry. Do not spam Diagnose while demoing.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Insufficient evidence - local fallback` + `external LLM unavailable` | `.env` not wired: `GROQ_API_KEY` missing/empty in container — check `docker compose exec api printenv GROQ_API_KEY`, then `docker compose up -d` |
| `Groq error 404 model_not_found` | Set `GROQ_MODEL` in `.env` to a model your key can list (`GET /openai/v1/models`) |
| 429 Too Many Requests | Wait 60 s; rate limit is per-IP shared by browser + curl |
| 401 Unauthorized | Token vs `JWT_SECRET` mismatch — clear localStorage, login again |
| Run page says `expired` | API restarted (runs are in-memory). Start a new Diagnose. |
| Empty Evidence list | Corpus missing — run `python scripts/ingest_corpus.py` inside api container / backend venv |
| 5432 port conflict | Postgres is mapped to host **5433** on purpose (native PG owns 5432) |

## Dev mode (optional, outside Docker)

```powershell
# backend
cd backend
.venv\Scripts\pytest -q -p no:warnings   # 63 passed, 1 skipped
.venv\Scripts\ruff check .
.venv\Scripts\uvicorn app.main:app --reload --port 8000

# frontend
cd frontend
npm run lint && npx vitest run && npm run build
npm run dev                              # :3000
```

Backend tests: 63 passed (+1 BiomedCLIP E2E skipped unless `RUN_VISION_E2E=1`). Frontend: eslint clean, 5 vitest tests, production build green.
