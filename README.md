# Multimodal Lung Cancer Agentic AI Diagnosis

Production full-stack platform: FastAPI + LangGraph + Laya/Jev System 1 router + Next.js 15.

See `BLUEPRINT.md` for architecture, roadmap, checklists.

## Run

```bash
# DB
docker compose up -d postgres

# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows; source .venv/bin/activate elsewhere
pip install -e ".[dev]"
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## Verify

```bash
cd backend && ruff check . && pytest
cd frontend && npm run build
```
