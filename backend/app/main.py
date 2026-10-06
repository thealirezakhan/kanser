import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import router
from app.limits import diagnose_limiter, global_limiter

# local dev: read repo .env (missing in container; compose env_file covers that)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")  # backend/.env if present
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")  # repo root

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_STATUS_CODES = {
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    413: "payload_too_large",
    429: "rate_limited",
}


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app() -> FastAPI:
    app = FastAPI(title="Kanser API", version="0.1.0")
    app.include_router(router)

    @app.on_event("startup")
    async def _refuse_default_secrets() -> None:
        from app.auth import assert_strong_secret

        assert_strong_secret()

    @app.middleware("http")
    async def _rate_limit_and_headers(request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)  # preflights don't consume quota
        key = request.client.host if request.client else "unknown"
        limiter = (
            diagnose_limiter
            if request.url.path.endswith("/diagnose")
            else global_limiter
        )
        if not limiter.allow(key):
            return _error(429, "rate_limited", "Too many requests, slow down")
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    # CORS added last = outermost: 429s/errors still carry ACAO headers
    origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _error(422, "validation_error", str(exc.errors()))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        status = exc.status_code
        return _error(status, _STATUS_CODES.get(status, "http_error"), str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled error on %s", request.url.path, exc_info=True)
        return _error(500, "internal_error", "Internal server error")

    app.state.audit_path = Path(os.environ.get("AUDIT_LOG", "data/audit/audit.jsonl"))

    if os.environ.get("DISABLE_AUTH") == "1":
        logger.warning("AUTH DISABLED (DISABLE_AUTH=1) - dev/test only")

    from fastapi import WebSocket, WebSocketDisconnect

    from app.auth import verify_token
    from app.runs import run_store

    async def _ws_auth(websocket: WebSocket) -> bool:
        """Accept, then require {type: auth, token} as the first message.

        Token never travels in the URL, so access logs cannot leak it.
        """
        await websocket.accept()
        try:
            first = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        except (WebSocketDisconnect, TimeoutError, ValueError, RuntimeError):
            await websocket.close(code=4401)
            return False
        if first.get("type") != "auth":
            await websocket.close(code=4401)
            return False
        if os.environ.get("DISABLE_AUTH") != "1":
            try:
                verify_token(str(first.get("token", "")))
            except Exception:
                await websocket.close(code=4401)
                return False
        return True

    @app.websocket("/ws/runs/{run_id}")
    async def ws_run(websocket: WebSocket, run_id: str):
        if not await _ws_auth(websocket):
            return
        q = run_store.subscribe(run_id)
        if q is None:
            await websocket.close(code=4404)
            return
        try:
            while True:
                ev = await q.get()
                await websocket.send_json(ev)
                if ev.get("type") in ("run_completed", "run_failed"):
                    break
        except WebSocketDisconnect:
            pass
        finally:
            run_store.unsubscribe(run_id, q)

    @app.websocket("/ws/cases/{case_id}/chat")
    async def ws_chat(websocket: WebSocket, case_id: str):
        if not await _ws_auth(websocket):
            return
        from app.chat import chat_case
        from app.llm import get_llm
        from app.pii import get_pii_guard
        from app.repo import get_repo

        case = await get_repo().get_case(case_id)
        if case is None:
            await websocket.close(code=4404)
            return
        try:
            while True:
                data = await websocket.receive_json()
                message = str(data.get("message", "")).strip()[:4000]
                if not message:
                    continue
                result = await chat_case(
                    case_id, case, message, llm=get_llm(), guard=get_pii_guard()
                )
                for i, turn in enumerate(result["turns"]):
                    await websocket.send_json({"type": "chat_turn", "seq": i, **turn})
                await websocket.send_json(
                    {
                        "type": "chat_done",
                        "tokens": result["tokens"],
                        "context_builds": result["context_builds"],
                        "history_size": result["history_size"],
                    }
                )
        except (WebSocketDisconnect, RuntimeError):
            pass

    return app


app = create_app()
