import asyncio
from threading import Lock
from typing import Any


class RunStore:
    def __init__(self) -> None:
        self._runs: dict[str, dict[str, Any]] = {}
        self._subs: dict[str, list[asyncio.Queue]] = {}
        self._lock = Lock()

    def create(self, run_id: str) -> None:
        with self._lock:
            self._runs[run_id] = {
                "run_id": run_id,
                "status": "queued",
                "events": [],
                "result": None,
            }

    def update(self, run_id: str, **fields: Any) -> None:
        with self._lock:
            if run_id in self._runs:
                self._runs[run_id].update(fields)

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            snap = self._runs.get(run_id)
            return dict(snap) if snap else None

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
