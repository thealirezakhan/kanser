import asyncio
import json
import logging
import os
import re
import time
import weakref
from datetime import UTC, datetime
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


def new_run_id(case_id: str, patient_ref: str) -> str:
    """Meaningful run id: patient slug + case prefix + timestamp (ms precision)."""
    slug = re.sub(r"[^a-z0-9]+", "-", patient_ref.lower()).strip("-")[:24] or "patient"
    now = datetime.now(UTC)
    stamp = f"{now.strftime('%Y%m%d-%H%M%S')}-{now.microsecond // 1000:03d}"
    return f"{slug}-{case_id[:6]}-{stamp}"


class _RunDB:
    """Lazy asyncpg write-through for run snapshots. Memory stays the source
    of truth for live runs; DB only restores history after restart.

    Pools are keyed per event loop: TestClient runs each request on its own
    loop, and asyncpg connections are bound to the loop that created them.
    """

    def __init__(self) -> None:
        self._pools: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
        self._locks: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()

    async def pool(self):
        dsn = os.environ.get("DATABASE_URL", "")
        if not dsn:
            return None
        loop = asyncio.get_running_loop()
        if loop in self._pools:
            return self._pools[loop]
        lock = self._locks.setdefault(loop, asyncio.Lock())
        async with lock:
            if loop in self._pools:
                return self._pools[loop]
            try:
                import asyncpg

                p = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
                await p.execute(
                    """
                    CREATE TABLE IF NOT EXISTS runs (
                        id TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        case_id TEXT,
                        result JSONB,
                        events JSONB NOT NULL DEFAULT '[]',
                        created_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
            except Exception:
                logger.warning("run persistence unavailable", exc_info=True)
                return None
            self._pools[loop] = p
        return self._pools[loop]

    async def upsert(self, run: dict[str, Any]) -> None:
        pool = await self.pool()
        if pool is None:
            return
        await pool.execute(
            """
            INSERT INTO runs (id, status, case_id, result, events, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                result = EXCLUDED.result,
                events = EXCLUDED.events,
                updated_at = EXCLUDED.updated_at
            """,
            run["run_id"],
            run["status"],
            run.get("case_id"),
            json.dumps(run.get("result")),
            json.dumps(run.get("events", [])),
            datetime.fromtimestamp(run.get("created_ts", time.time()), UTC),
            datetime.fromtimestamp(run.get("updated_at", time.time()), UTC),
        )

    async def fetch(self, run_id: str) -> dict[str, Any] | None:
        pool = await self.pool()
        if pool is None:
            return None
        row = await pool.fetchrow(
            "SELECT id, status, case_id, result, events, created_at, updated_at"
            " FROM runs WHERE id = $1",
            run_id,
        )
        if not row:
            return None
        return {
            "run_id": row["id"],
            "status": row["status"],
            "case_id": row["case_id"],
            "result": json.loads(row["result"]) if row["result"] else None,
            "events": json.loads(row["events"]),
            "created_ts": row["created_at"].timestamp(),
            "updated_at": row["updated_at"].timestamp(),
        }

    async def list(self, limit: int) -> list[dict[str, Any]]:
        pool = await self.pool()
        if pool is None:
            return []
        rows = await pool.fetch(
            "SELECT id, status, case_id, result, events, created_at, updated_at"
            " FROM runs ORDER BY updated_at DESC LIMIT $1",
            limit,
        )
        out = []
        for row in rows:
            out.append(
                {
                    "run_id": row["id"],
                    "status": row["status"],
                    "case_id": row["case_id"],
                    "result": json.loads(row["result"]) if row["result"] else None,
                    "events": json.loads(row["events"]),
                    "created_ts": row["created_at"].timestamp(),
                    "updated_at": row["updated_at"].timestamp(),
                }
            )
        return out


def _summary(run: dict[str, Any]) -> dict[str, Any]:
    result = run.get("result") or {}
    consensus = result.get("consensus") or {}
    return {
        "run_id": run["run_id"],
        "status": run["status"],
        "case_id": run.get("case_id"),
        "diagnosis": consensus.get("diagnosis"),
        "confidence": consensus.get("confidence"),
        "event_count": len(run.get("events", [])),
        "updated_at": run.get("updated_at", 0.0),
    }


class RunStore:
    def __init__(self) -> None:
        self._runs: dict[str, dict[str, Any]] = {}
        self._subs: dict[str, list[asyncio.Queue]] = {}
        self._lock = Lock()
        self._db = _RunDB()

    def create(self, run_id: str, case_id: str | None = None) -> None:
        now = time.time()
        with self._lock:
            self._runs[run_id] = {
                "run_id": run_id,
                "case_id": case_id,
                "status": "queued",
                "events": [],
                "result": None,
                "created_ts": now,
                "updated_at": now,
            }

    def update(self, run_id: str, **fields: Any) -> None:
        persist = False
        with self._lock:
            if run_id in self._runs:
                self._runs[run_id].update(fields)
                self._runs[run_id]["updated_at"] = time.time()
                persist = fields.get("status") in ("completed", "failed")
        if persist:
            self._schedule_persist(run_id)

    def _schedule_persist(self, run_id: str) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._safe_persist(run_id))

    async def _safe_persist(self, run_id: str) -> None:
        try:
            await self.persist(run_id)
        except Exception:
            logger.warning("persisting run %s failed", run_id, exc_info=True)

    async def persist(self, run_id: str) -> None:
        with self._lock:
            snap = self._runs.get(run_id)
            run = dict(snap) if snap else None
        if run is None:
            return
        run["events"] = list(run.get("events", []))
        await self._db.upsert(run)

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            snap = self._runs.get(run_id)
            return dict(snap) if snap else None

    async def fetch_db(self, run_id: str) -> dict[str, Any] | None:
        """DB restore after restart; seeds memory so WS subscribe works."""
        run = await self._db.fetch(run_id)
        if run is None:
            return None
        with self._lock:
            self._runs.setdefault(run_id, run)
        return run

    async def list_summaries(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            merged = {rid: dict(r) for rid, r in self._runs.items()}
        for run in await self._db.list(limit):
            merged.setdefault(run["run_id"], run)
        summaries = [_summary(r) for r in merged.values()]
        summaries.sort(key=lambda s: s["updated_at"], reverse=True)
        return summaries[:limit]

    def push_event(self, run_id: str, event: dict) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            seq = len(run["events"])
            run["events"].append({**event, "seq": seq})
            for q in self._subs.get(run_id, []):
                q.put_nowait({**event, "seq": seq})

    def subscribe(self, run_id: str) -> asyncio.Queue | None:
        """Queue seeded with backlog so late subscribers lose nothing."""
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            for ev in run["events"]:
                q.put_nowait(ev)
            self._subs.setdefault(run_id, []).append(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue) -> None:
        with self._lock:
            subs = self._subs.get(run_id, [])
            if q in subs:
                subs.remove(q)


run_store = RunStore()
