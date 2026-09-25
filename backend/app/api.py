import asyncio
import logging
import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from pydantic import BaseModel

from app.auth import check_credentials, create_token, require_auth
from app.repo import CaseRepo, get_repo
from app.runs import run_store
from app.schemas import CaseInput, RunAccepted
from app.security import sha256_bytes
from app.system1 import route_case

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])


class LoginInput(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
async def login(inp: LoginInput) -> dict:
    if not check_credentials(inp.username, inp.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"data": {"token": create_token(inp.username)}}


@router.get("/health")
async def health() -> dict:
    return {"data": {"status": "ok", "version": "0.1.0"}}


@router.post("/cases", status_code=201, response_model=None)
async def create_case(
    inp: CaseInput, response: Response, repo: CaseRepo = Depends(get_repo)
) -> dict:
    case = await repo.create_case(inp)
    response.headers["location"] = f"/api/cases/{case.id}"
    return {"data": case}


@router.get("/cases")
async def list_cases(repo: CaseRepo = Depends(get_repo)) -> dict:
    return {"data": await repo.list_cases()}


@router.get("/cases/{case_id}")
async def get_case(case_id: str, repo: CaseRepo = Depends(get_repo)) -> dict:
    case = await repo.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"data": case}


def _upload_dir() -> Path:
    return Path(os.environ.get("UPLOAD_DIR", "data/uploads"))


@router.post("/documents/ingest", status_code=201)
async def ingest_document(file: UploadFile) -> dict:
    upload_dir = _upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload.bin").name.replace("\x00", "")
    stored = upload_dir / f"{uuid4().hex}_{safe_name}"
    digest = sha256_bytes(b"")
    import hashlib

    h = hashlib.sha256()
    with open(stored, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            h.update(chunk)
            f.write(chunk)
    digest = h.hexdigest()
    stored.with_suffix(stored.suffix + ".sha256").write_text(digest, encoding="utf-8")
    return {
        "data": {
            "filename": safe_name,
            "stored_as": stored.name,
            "sha256": digest,
            "size": stored.stat().st_size,
        }
    }


@router.post("/cases/{case_id}/routing")
async def preview_routing(case_id: str, repo: CaseRepo = Depends(get_repo)) -> dict:
    case = await repo.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"data": route_case(case)}


async def _execute_run(run_id: str, case) -> None:
    from app.rag import get_rag
    from app.swarm import run_case

    run_store.update(run_id, status="running")
    try:
        final = await run_case(
            case,
            rag=get_rag(),
            on_event=lambda ev: run_store.push_event(run_id, ev),
        )
        run_store.update(run_id, status="completed", result=final)
        run_store.push_event(run_id, {"type": "run_completed"})
    except Exception:
        logger.error("Run %s failed", run_id, exc_info=True)
        run_store.update(run_id, status="failed")
        run_store.push_event(run_id, {"type": "run_failed"})


@router.post("/cases/{case_id}/diagnose", status_code=202)
async def diagnose(case_id: str, repo: CaseRepo = Depends(get_repo)) -> dict:
    case = await repo.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    run_id = uuid4().hex
    run_store.create(run_id)
    asyncio.create_task(_execute_run(run_id, case))
    return {"data": RunAccepted(run_id=run_id)}


@router.post("/vision/analyze")
async def vision_analyze(file: UploadFile) -> dict:
    from app.vision import get_vision_worker

    data = await file.read()
    if len(data) > 64 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (64MB max)")
    report = await get_vision_worker().analyze(data)
    return {"data": report}


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    snap = run_store.get(run_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"data": snap}
