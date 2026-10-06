import asyncio
import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from pydantic import BaseModel, Field

from app.auth import check_credentials, create_token, require_auth
from app.longitudinal import progression
from app.repo import CaseRepo, get_repo
from app.runs import new_run_id, run_store
from app.schemas import CaseInput, FindingIn, RunAccepted, VisitIn
from app.standardize import classify_file, standardize_case
from app.system1 import route_case

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])
_STARTED_AT = time.time()


def _can_read(actor: str, owner: str) -> bool:
    # "" owner = legacy/unowned (pre-authz data) stays reachable;
    # "" actor = auth disabled
    return actor == "" or owner == "" or actor == owner


class LoginInput(BaseModel):
    username: str
    password: str


class ChatInput(BaseModel):
    model_config = {"extra": "forbid"}

    message: str = Field(min_length=1, max_length=4000)


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
    inp: CaseInput,
    response: Response,
    repo: CaseRepo = Depends(get_repo),
    user: str = Depends(require_auth),
) -> dict:
    case = await repo.create_case(inp, owner=user)
    # Longitudinal contract: every case opens with Visit 1
    from datetime import date as _date

    await repo.add_visit(
        case.id,
        VisitIn(
            visit_date=_date.today(),
            visit_type="initial_consultation",
            reason=(inp.intake.reason_for_presentation if inp.intake else inp.clinical_notes[:200]),
            doctor=user,
        ),
    )
    from app.audit import record

    record(user, "case.create", case.id)
    response.headers["location"] = f"/api/cases/{case.id}"
    return {"data": case}


@router.get("/cases")
async def list_cases(
    repo: CaseRepo = Depends(get_repo), user: str = Depends(require_auth)
) -> dict:
    visible = [c for c in await repo.list_cases() if _can_read(user, c.owner)]
    from app.audit import record

    record(user, "case.list", f"{len(visible)}")
    return {"data": visible}


@router.get("/cases/{case_id}")
async def get_case(
    case_id: str,
    repo: CaseRepo = Depends(get_repo),
    user: str = Depends(require_auth),
) -> dict:
    case = await repo.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if not _can_read(user, case.owner):
        raise HTTPException(status_code=403, detail="Not allowed on this case")
    from app.audit import record

    record(user, "case.read", case_id)
    return {"data": case}


def _upload_dir() -> Path:
    return Path(os.environ.get("UPLOAD_DIR", "data/uploads"))


@router.post("/documents/ingest", status_code=201)
async def ingest_document(
    file: UploadFile,
    case_id: str | None = Form(default=None),
    visit_id: str | None = Form(default=None),
    repo: CaseRepo = Depends(get_repo),
    user: str = Depends(require_auth),
) -> dict:
    upload_dir = _upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload.bin").name.replace("\x00", "")
    stored = upload_dir / f"{uuid4().hex}_{safe_name}"
    import hashlib

    max_bytes = int(os.environ.get("UPLOAD_MAX_BYTES", str(50 * 1024 * 1024)))
    h = hashlib.sha256()
    written = 0
    with open(stored, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > max_bytes:
                f.close()
                stored.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Upload too large")
            h.update(chunk)
            f.write(chunk)
    digest = h.hexdigest()
    stored.with_suffix(stored.suffix + ".sha256").write_text(digest, encoding="utf-8")

    # Data Standardization Agent: classify + parse text payloads into unified schema
    text = ""
    if stored.stat().st_size <= 2 * 1024 * 1024:
        try:
            text = stored.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            text = ""
    kind = classify_file(safe_name, text)
    from app.imaging import (
        classify_imaging_modality,
        extract_dicom_header,
        extract_imaging_findings,
    )

    dicom_header = None
    if stored.suffix.lower() in {".dcm", ".dicom"}:
        dicom_header = extract_dicom_header(stored)
    standardized = None
    if kind in ("labs", "genomics", "notes"):
        standardized = standardize_case(
            {
                "patient_ref": "",
                "modalities": [kind] if kind != "notes" else ["notes"],
                "clinical_notes": text if kind == "notes" else "",
                "metadata": {
                    "labs_raw": text if kind == "labs" else "",
                    "vcf": text if kind == "genomics" else "",
                },
            }
        )

    if case_id is not None:
        case = await repo.get_case(case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")
        visits = await repo.list_visits(case_id)
        attached_visit = visit_id or (visits[-1].id if visits else "")
        existing_docs: list[dict] = []
        if case.metadata.get("documents"):
            try:
                existing_docs = json.loads(case.metadata["documents"])
            except json.JSONDecodeError:
                existing_docs = []
        existing_docs.append(
            {
                "id": uuid4().hex,
                "filename": safe_name,
                "kind": kind,
                "visit_id": attached_visit,
                "sha256": digest,
                "uploaded_at": datetime.now(UTC).isoformat(),
            }
        )
        metadata_updates: dict[str, str] = {"documents": json.dumps(existing_docs)}
        add_modalities: list[str] = []
        if kind == "labs":
            metadata_updates["labs_raw"] = text
            add_modalities.append("labs")
        elif kind == "genomics":
            metadata_updates["vcf"] = text
            add_modalities.append("genomics")
        elif kind == "notes":
            metadata_updates["notes_addendum"] = text[:100_000]
            add_modalities.append("notes")
        elif kind == "pathology":
            metadata_updates["pathology_report"] = text[:100_000]
            add_modalities.append("pathology")
        elif kind == "imaging_report":
            findings = extract_imaging_findings(text)
            metadata_updates["imaging_findings"] = json.dumps(findings)
            add_modalities.append(classify_imaging_modality(text))
        elif kind == "ct":
            add_modalities.append("ct")
        if dicom_header is not None:
            metadata_updates["dicom_header"] = json.dumps(dicom_header)
            mod = dicom_header.get("modality", "")
            if mod in {"CT", "PT"}:
                add_modalities.append("ct")
            elif mod in {"DX", "CR"}:
                add_modalities.append("cxr")
        if metadata_updates or add_modalities:
            await repo.merge_case(case_id, metadata_updates, add_modalities)
            from app.chat import invalidate_context

            invalidate_context(case_id)
        from app.findings import extract_findings

        for f in extract_findings(kind or "", text):
            await repo.add_finding(
                case_id,
                FindingIn(
                    visit_id=attached_visit,
                    source_doc=safe_name,
                    source_kind=kind or "",
                    key=f["key"],
                    value=f["value"],
                    origin="ai",
                    confidence=f.get("confidence", "medium"),
                ),
            )
    from app.audit import record

    record(user, "document.ingest", stored.name)
    return {
        "data": {
            "filename": safe_name,
            "stored_as": stored.name,
            "sha256": digest,
            "size": stored.stat().st_size,
            "kind": kind,
            "case_id": case_id,
            "standardized": standardized,
            "dicom_header": dicom_header,
        }
    }


class FindingVerifyInput(BaseModel):
    model_config = {"extra": "forbid"}

    action: Literal["accept", "reject", "edit", "unknown"]
    value: str = Field(default="", max_length=2000)
    confidence: Literal["high", "medium", "low"] | None = None


@router.get("/cases/{case_id}/findings")
async def list_case_findings(
    case_id: str,
    repo: CaseRepo = Depends(get_repo),
    user: str = Depends(require_auth),
) -> dict:
    case = await repo.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if not _can_read(user, case.owner):
        raise HTTPException(status_code=403, detail="Not allowed on this case")
    return {"data": {"findings": await repo.list_findings(case_id)}}


@router.post("/findings/{finding_id}/verify")
async def verify_finding(
    finding_id: str,
    inp: FindingVerifyInput,
    repo: CaseRepo = Depends(get_repo),
    user: str = Depends(require_auth),
) -> dict:
    updated = await repo.verify_finding(
        finding_id, inp.action, inp.value, inp.confidence or "", user
    )
    if updated is None:
        from app.audit import record

        record(user, "finding.verify", finding_id)
        raise HTTPException(status_code=404, detail="Finding not found")
    from app.audit import record

    record(user, "finding.verify", finding_id)
    return {"data": updated}


@router.post("/cases/{case_id}/routing")
async def preview_routing(case_id: str, repo: CaseRepo = Depends(get_repo)) -> dict:
    case = await repo.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"data": route_case(case)}


@router.post("/readiness/preview")
async def readiness_preview(inp: CaseInput) -> dict:
    from app.readiness import evaluate

    intake = inp.intake.model_dump() if inp.intake else {}
    return {"data": evaluate(intake, list(inp.modalities))}


@router.get("/cases/{case_id}/assessment")
async def case_assessment(
    case_id: str,
    repo: CaseRepo = Depends(get_repo),
    user: str = Depends(require_auth),
) -> dict:
    case = await repo.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if not _can_read(user, case.owner):
        raise HTTPException(status_code=403, detail="Not allowed on this case")
    from app.system1 import assess_case

    return {"data": assess_case(case, findings=await repo.list_findings(case_id))}


@router.post("/cases/{case_id}/chat")
async def case_chat(
    case_id: str,
    inp: ChatInput,
    repo: CaseRepo = Depends(get_repo),
    user: str = Depends(require_auth),
) -> dict:
    from app.chat import chat_case
    from app.llm import get_llm
    from app.pii import get_pii_guard

    case = await repo.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if not _can_read(user, case.owner):
        raise HTTPException(status_code=403, detail="Not allowed on this case")
    from app.audit import record

    record(user, "chat.message", case_id)
    result = await chat_case(
        case_id, case, inp.message, llm=get_llm(), guard=get_pii_guard()
    )
    return {"data": result}


@router.post("/cases/{case_id}/visits", status_code=201, response_model=None)
async def add_visit(
    case_id: str,
    inp: VisitIn,
    response: Response,
    repo: CaseRepo = Depends(get_repo),
) -> dict:
    visit = await repo.add_visit(case_id, inp)
    if visit is None:
        raise HTTPException(status_code=404, detail="Case not found")
    response.headers["location"] = f"/api/cases/{case_id}/visits"
    return {"data": visit}


@router.get("/cases/{case_id}/visits")
async def list_visits(case_id: str, repo: CaseRepo = Depends(get_repo)) -> dict:
    if await repo.get_case(case_id) is None:
        raise HTTPException(status_code=404, detail="Case not found")
    visits = await repo.list_visits(case_id)
    return {
        "data": {
            "visits": visits,
            "progression": progression([v.model_dump(mode="json") for v in visits]),
        }
    }


async def _execute_run(run_id: str, case_id: str, case) -> None:
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
        from app.chat import invalidate_context

        invalidate_context(case_id)
    except Exception:
        logger.error("Run %s failed", run_id, exc_info=True)
        run_store.update(run_id, status="failed")
        run_store.push_event(run_id, {"type": "run_failed"})


@router.post("/cases/{case_id}/diagnose", status_code=202)
async def diagnose(
    case_id: str,
    repo: CaseRepo = Depends(get_repo),
    user: str = Depends(require_auth),
) -> dict:
    case = await repo.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if not _can_read(user, case.owner):
        raise HTTPException(status_code=403, detail="Not allowed on this case")
    run_id = new_run_id(case_id, case.patient_ref)
    run_store.create(run_id, case_id=case_id)
    from app.audit import record

    record(user, "run.create", run_id)
    asyncio.create_task(_execute_run(run_id, case_id, case))
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
async def get_run(
    run_id: str,
    repo: CaseRepo = Depends(get_repo),
    user: str = Depends(require_auth),
) -> dict:
    snap = run_store.get(run_id) or await run_store.fetch_db(run_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="Run not found")
    case_id = snap.get("case_id")
    if case_id:
        case = await repo.get_case(case_id)
        if case is not None and not _can_read(user, case.owner):
            raise HTTPException(status_code=403, detail="Not allowed on this case")
    from app.audit import record

    record(user, "run.read", run_id)
    return {"data": snap}


@router.get("/runs")
async def list_runs(limit: int = Query(default=50, ge=1, le=200)) -> dict:
    return {"data": {"runs": await run_store.list_summaries(limit)}}


@router.get("/evidence/search")
async def evidence_search(q: str = Query(..., min_length=1, max_length=500)) -> dict:
    from app.rag import filter_evidence, get_rag

    try:
        hits = get_rag()(q)
        kept, dropped = filter_evidence(hits, {})
        return {
            "data": {
                "query": q,
                "verified": kept,
                "dropped": [
                    {"id": d.get("id"), "reason": d.get("reason")} for d in dropped
                ],
            }
        }
    except Exception:
        logger.error("evidence search failed", exc_info=True)
        return {"data": {"query": q, "verified": [], "dropped": []}}


@router.get("/system/status")
async def system_status() -> dict:
    from app.llm import get_llm

    return {
        "data": {
            "status": "ok",
            "version": "0.1.0",
            "llm": get_llm().name,
            "auth": "disabled" if os.environ.get("DISABLE_AUTH") else "enabled",
            "uptime_seconds": int(time.time() - _STARTED_AT),
            "rate_limit": {"global": "60/min", "diagnose": "5/min per IP"},
        }
    }


@router.get("/alerts")
async def alerts(repo: CaseRepo = Depends(get_repo)) -> dict:
    runs = await run_store.list_summaries(200)
    failed = [r for r in runs if r["status"] == "failed"]
    high_risk = []
    for case in await repo.list_cases():
        routing = route_case(case)
        if routing.risk_grade == "high":
            high_risk.append(
                {
                    "case_id": case.id,
                    "patient_ref": case.patient_ref,
                    "priority": routing.priority,
                    "risk_grade": routing.risk_grade,
                }
            )
    high_risk.sort(key=lambda c: c["priority"], reverse=True)
    return {
        "data": {
            "failed_runs": failed,
            "high_risk_cases": high_risk,
            "total_cases": len(high_risk),
        }
    }
