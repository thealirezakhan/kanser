import os
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from app.schemas import CaseInput, CaseOut


class CaseRepo(Protocol):
    async def create_case(self, inp: CaseInput) -> CaseOut: ...
    async def get_case(self, case_id: str) -> CaseOut | None: ...
    async def list_cases(self) -> list[CaseOut]: ...


class MemoryRepo:
    def __init__(self) -> None:
        self._cases: dict[str, CaseOut] = {}

    async def create_case(self, inp: CaseInput) -> CaseOut:
        case = CaseOut(id=uuid4().hex, created_at=datetime.now(UTC), **inp.model_dump())
        self._cases[case.id] = case
        return case

    async def get_case(self, case_id: str) -> CaseOut | None:
        return self._cases.get(case_id)

    async def list_cases(self) -> list[CaseOut]:
        return list(self._cases.values())


class PostgresRepo:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool = None

    async def _get_pool(self):
        if self._pool is None:
            import asyncpg

            self._pool = await asyncpg.create_pool(self._dsn, min_size=2, max_size=10)
            await self._pool.execute(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY,
                    patient_ref TEXT NOT NULL,
                    modalities JSONB NOT NULL,
                    clinical_notes TEXT NOT NULL DEFAULT '',
                    metadata JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
        return self._pool

    async def create_case(self, inp: CaseInput) -> CaseOut:
        import json

        case = CaseOut(id=uuid4().hex, created_at=datetime.now(UTC), **inp.model_dump())
        pool = await self._get_pool()
        await pool.execute(
            "INSERT INTO cases (id, patient_ref, modalities, clinical_notes, metadata, created_at)"
            " VALUES ($1, $2, $3, $4, $5, $6)",
            case.id,
            case.patient_ref,
            json.dumps(case.modalities),
            case.clinical_notes,
            json.dumps(case.metadata),
            case.created_at,
        )
        return case

    async def get_case(self, case_id: str) -> CaseOut | None:
        import json

        pool = await self._get_pool()
        row = await pool.fetchrow(
            "SELECT id, patient_ref, modalities, clinical_notes, metadata, created_at"
            " FROM cases WHERE id = $1",
            case_id,
        )
        if not row:
            return None
        return CaseOut(
            id=row["id"],
            patient_ref=row["patient_ref"],
            modalities=json.loads(row["modalities"]),
            clinical_notes=row["clinical_notes"],
            metadata=json.loads(row["metadata"]),
            created_at=row["created_at"],
        )

    async def list_cases(self) -> list[CaseOut]:
        import json

        pool = await self._get_pool()
        rows = await pool.fetch(
            "SELECT id, patient_ref, modalities, clinical_notes, metadata, created_at FROM cases"
        )
        return [
            CaseOut(
                id=r["id"],
                patient_ref=r["patient_ref"],
                modalities=json.loads(r["modalities"]),
                clinical_notes=r["clinical_notes"],
                metadata=json.loads(r["metadata"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]


_repo: CaseRepo | None = None


def get_repo() -> CaseRepo:
    global _repo
    if _repo is None:
        dsn = os.environ.get("DATABASE_URL", "")
        _repo = PostgresRepo(dsn) if dsn else MemoryRepo()
    return _repo
