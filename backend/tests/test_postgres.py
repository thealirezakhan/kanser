import asyncio
import os
import socket

import pytest

from app.repo import PostgresRepo
from app.schemas import CaseInput

DSN = os.environ.get(
    "DATABASE_URL", "postgresql://kanser:kanser@localhost:5432/kanser"
)


def _pg_up() -> bool:
    try:
        with socket.create_connection(("localhost", 5432), timeout=1):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _pg_up(), reason="postgres not running")


def test_postgres_roundtrip():
    async def run() -> None:
        repo = PostgresRepo(DSN)
        created = await repo.create_case(
            CaseInput(patient_ref="p1", modalities=["ct"], clinical_notes="note")
        )
        got = await repo.get_case(created.id)
        assert got is not None
        assert got.patient_ref == "p1"
        assert "ct" in got.modalities
        assert any(c.id == created.id for c in await repo.list_cases())
        await repo._pool.close()

    asyncio.run(run())


def test_postgres_missing_returns_none():
    async def run() -> None:
        repo = PostgresRepo(DSN)
        assert await repo.get_case("does-not-exist") is None
        if repo._pool:
            await repo._pool.close()

    asyncio.run(run())
