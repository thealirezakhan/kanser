import os
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from app.schemas import CaseInput, CaseOut, FindingIn, FindingOut, VisitIn, VisitOut


class CaseRepo(Protocol):
    async def create_case(self, inp: CaseInput, owner: str = "") -> CaseOut: ...
    async def get_case(self, case_id: str) -> CaseOut | None: ...
    async def list_cases(self) -> list[CaseOut]: ...
    async def merge_case(
        self, case_id: str, metadata_updates: dict, add_modalities: list[str]
    ) -> CaseOut | None: ...
    async def add_visit(self, case_id: str, inp: VisitIn) -> VisitOut | None: ...
    async def list_visits(self, case_id: str) -> list[VisitOut]: ...
    async def add_finding(self, case_id: str, inp: FindingIn) -> FindingOut: ...
    async def list_findings(self, case_id: str) -> list[FindingOut]: ...
    async def verify_finding(
        self, finding_id: str, action: str, value: str, confidence: str, user: str
    ) -> FindingOut | None: ...


_VERIFICATION = {"accept": "accepted", "reject": "rejected", "unknown": "unknown"}


def _apply_verification(f: FindingOut, action: str, value: str, confidence: str,
                        user: str) -> FindingOut | None:
    if action in _VERIFICATION:
        return f.model_copy(
            update={"verification": _VERIFICATION[action], "verified_by": user}
        )
    if action == "edit":
        update = {
            "value": value,
            "origin": "clinician",
            "verification": "accepted",
            "verified_by": user,
        }
        if confidence:
            update["confidence"] = confidence
        return f.model_copy(update=update)
    return None


class MemoryRepo:
    def __init__(self) -> None:
        self._cases: dict[str, CaseOut] = {}
        self._visits: dict[str, list[VisitOut]] = {}
        self._findings: dict[str, FindingOut] = {}

    async def create_case(self, inp: CaseInput, owner: str = "") -> CaseOut:
        data = inp.model_dump()
        data["intake"] = data["intake"] or {}
        case = CaseOut(id=uuid4().hex, created_at=datetime.now(UTC), owner=owner, **data)
        self._cases[case.id] = case
        return case

    async def get_case(self, case_id: str) -> CaseOut | None:
        return self._cases.get(case_id)

    async def list_cases(self) -> list[CaseOut]:
        return list(self._cases.values())

    async def merge_case(
        self, case_id: str, metadata_updates: dict, add_modalities: list[str]
    ) -> CaseOut | None:
        case = self._cases.get(case_id)
        if case is None:
            return None
        updated = case.model_copy(
            update={
                "metadata": {**case.metadata, **metadata_updates},
                "modalities": sorted(set(case.modalities) | set(add_modalities)),
            }
        )
        self._cases[case_id] = updated
        return updated

    async def add_visit(self, case_id: str, inp: VisitIn) -> VisitOut | None:
        if case_id not in self._cases:
            return None
        visit = VisitOut(
            id=uuid4().hex,
            case_id=case_id,
            created_at=datetime.now(UTC),
            **inp.model_dump(),
        )
        self._visits.setdefault(case_id, []).append(visit)
        return visit

    async def list_visits(self, case_id: str) -> list[VisitOut]:
        return sorted(self._visits.get(case_id, []), key=lambda v: v.visit_date)

    async def add_finding(self, case_id: str, inp: FindingIn) -> FindingOut:
        finding = FindingOut(
            id=uuid4().hex,
            case_id=case_id,
            created_at=datetime.now(UTC),
            **inp.model_dump(),
        )
        self._findings[finding.id] = finding
        return finding

    async def list_findings(self, case_id: str) -> list[FindingOut]:
        hits = [f for f in self._findings.values() if f.case_id == case_id]
        return sorted(hits, key=lambda f: f.created_at)

    async def verify_finding(
        self, finding_id: str, action: str, value: str, confidence: str, user: str
    ) -> FindingOut | None:
        f = self._findings.get(finding_id)
        if f is None:
            return None
        updated = _apply_verification(f, action, value, confidence, user)
        if updated is None:
            return None
        self._findings[finding_id] = updated
        return updated


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
                    created_at TIMESTAMPTZ NOT NULL,
                    owner TEXT NOT NULL DEFAULT '',
                    intake JSONB NOT NULL DEFAULT '{}'
                )
                """
            )
            await self._pool.execute(
                "ALTER TABLE cases ADD COLUMN IF NOT EXISTS owner TEXT NOT NULL DEFAULT ''"
            )
            await self._pool.execute(
                "ALTER TABLE cases ADD COLUMN IF NOT EXISTS intake JSONB NOT NULL DEFAULT '{}'"
            )
            await self._pool.execute(
                """
                CREATE TABLE IF NOT EXISTS visits (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(id),
                    visit_date DATE NOT NULL,
                    size_mm DOUBLE PRECISION,
                    notes TEXT NOT NULL DEFAULT '',
                    metadata JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            for ddl in (
                "ALTER TABLE visits ADD COLUMN IF NOT EXISTS visit_type TEXT"
                " NOT NULL DEFAULT 'follow_up'",
                "ALTER TABLE visits ADD COLUMN IF NOT EXISTS reason TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE visits ADD COLUMN IF NOT EXISTS doctor TEXT NOT NULL DEFAULT ''",
            ):
                await self._pool.execute(ddl)
            await self._pool.execute(
                """
                CREATE TABLE IF NOT EXISTS findings (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(id),
                    visit_id TEXT NOT NULL DEFAULT '',
                    source_doc TEXT NOT NULL DEFAULT '',
                    source_kind TEXT NOT NULL DEFAULT '',
                    "key" TEXT NOT NULL,
                    "value" TEXT NOT NULL DEFAULT '',
                    unit TEXT NOT NULL DEFAULT '',
                    origin TEXT NOT NULL DEFAULT 'ai',
                    confidence TEXT NOT NULL DEFAULT 'medium',
                    verification TEXT NOT NULL DEFAULT 'pending',
                    verified_by TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
        return self._pool

    async def create_case(self, inp: CaseInput, owner: str = "") -> CaseOut:
        import json

        data = inp.model_dump()
        data["intake"] = data["intake"] or {}
        case = CaseOut(id=uuid4().hex, created_at=datetime.now(UTC), owner=owner, **data)
        pool = await self._get_pool()
        await pool.execute(
            "INSERT INTO cases (id, patient_ref, modalities, clinical_notes,"
            " metadata, created_at, owner, intake)"
            " VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
            case.id,
            case.patient_ref,
            json.dumps(case.modalities),
            case.clinical_notes,
            json.dumps(case.metadata),
            case.created_at,
            case.owner,
            json.dumps(case.intake),
        )
        return case

    async def get_case(self, case_id: str) -> CaseOut | None:
        import json

        pool = await self._get_pool()
        row = await pool.fetchrow(
            "SELECT id, patient_ref, modalities, clinical_notes, metadata,"
            " created_at, owner, intake FROM cases WHERE id = $1",
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
            owner=row["owner"],
            intake=json.loads(row["intake"]),
        )

    async def list_cases(self) -> list[CaseOut]:
        import json

        pool = await self._get_pool()
        rows = await pool.fetch(
            "SELECT id, patient_ref, modalities, clinical_notes, metadata,"
            " created_at, owner, intake FROM cases"
        )
        return [
            CaseOut(
                id=r["id"],
                patient_ref=r["patient_ref"],
                modalities=json.loads(r["modalities"]),
                clinical_notes=r["clinical_notes"],
                metadata=json.loads(r["metadata"]),
                created_at=r["created_at"],
                owner=r["owner"],
                intake=json.loads(r["intake"]),
            )
            for r in rows
        ]

    async def merge_case(
        self, case_id: str, metadata_updates: dict, add_modalities: list[str]
    ) -> CaseOut | None:
        import json

        case = await self.get_case(case_id)
        if case is None:
            return None
        metadata = {**case.metadata, **metadata_updates}
        modalities = sorted(set(case.modalities) | set(add_modalities))
        pool = await self._get_pool()
        await pool.execute(
            "UPDATE cases SET metadata = $2, modalities = $3 WHERE id = $1",
            case_id,
            json.dumps(metadata),
            json.dumps(modalities),
        )
        return case.model_copy(update={"metadata": metadata, "modalities": modalities})

    async def add_visit(self, case_id: str, inp: VisitIn) -> VisitOut | None:
        import json

        if await self.get_case(case_id) is None:
            return None
        visit = VisitOut(
            id=uuid4().hex,
            case_id=case_id,
            created_at=datetime.now(UTC),
            **inp.model_dump(),
        )
        pool = await self._get_pool()
        await pool.execute(
            "INSERT INTO visits (id, case_id, visit_date, size_mm, notes, metadata,"
            " created_at, visit_type, reason, doctor)"
            " VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
            visit.id,
            visit.case_id,
            visit.visit_date,
            visit.size_mm,
            visit.notes,
            json.dumps(visit.metadata),
            visit.created_at,
            visit.visit_type,
            visit.reason,
            visit.doctor,
        )
        return visit

    async def list_visits(self, case_id: str) -> list[VisitOut]:
        import json

        pool = await self._get_pool()
        rows = await pool.fetch(
            "SELECT id, case_id, visit_date, size_mm, notes, metadata, created_at,"
            " visit_type, reason, doctor"
            " FROM visits WHERE case_id = $1 ORDER BY visit_date",
            case_id,
        )
        return [
            VisitOut(
                id=r["id"],
                case_id=r["case_id"],
                visit_date=r["visit_date"],
                size_mm=r["size_mm"],
                notes=r["notes"],
                metadata=json.loads(r["metadata"]),
                created_at=r["created_at"],
                visit_type=r["visit_type"],
                reason=r["reason"],
                doctor=r["doctor"],
            )
            for r in rows
        ]

    @staticmethod
    def _row_to_finding(r) -> FindingOut:
        return FindingOut(
            id=r["id"],
            case_id=r["case_id"],
            visit_id=r["visit_id"],
            source_doc=r["source_doc"],
            source_kind=r["source_kind"],
            key=r["key"],
            value=r["value"],
            unit=r["unit"],
            origin=r["origin"],
            confidence=r["confidence"],
            verification=r["verification"],
            verified_by=r["verified_by"],
            created_at=r["created_at"],
        )

    _FINDING_COLS = (
        "id, case_id, visit_id, source_doc, source_kind, \"key\", \"value\", unit,"
        " origin, confidence, verification, verified_by, created_at"
    )

    async def add_finding(self, case_id: str, inp: FindingIn) -> FindingOut:
        finding = FindingOut(
            id=uuid4().hex,
            case_id=case_id,
            created_at=datetime.now(UTC),
            **inp.model_dump(),
        )
        pool = await self._get_pool()
        await pool.execute(
            "INSERT INTO findings (id, case_id, visit_id, source_doc, source_kind,"
            ' "key", "value", unit, origin, confidence, verification, verified_by, created_at)'
            " VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)",
            finding.id,
            finding.case_id,
            finding.visit_id,
            finding.source_doc,
            finding.source_kind,
            finding.key,
            finding.value,
            finding.unit,
            finding.origin,
            finding.confidence,
            finding.verification,
            finding.verified_by,
            finding.created_at,
        )
        return finding

    async def list_findings(self, case_id: str) -> list[FindingOut]:
        pool = await self._get_pool()
        rows = await pool.fetch(
            f"SELECT {self._FINDING_COLS} FROM findings WHERE case_id = $1"
            " ORDER BY created_at",
            case_id,
        )
        return [self._row_to_finding(r) for r in rows]

    async def verify_finding(
        self, finding_id: str, action: str, value: str, confidence: str, user: str
    ) -> FindingOut | None:
        pool = await self._get_pool()
        row = await pool.fetchrow(
            f"SELECT {self._FINDING_COLS} FROM findings WHERE id = $1", finding_id
        )
        if not row:
            return None
        updated = _apply_verification(self._row_to_finding(row), action, value,
                                      confidence, user)
        if updated is None:
            return None
        await pool.execute(
            'UPDATE findings SET "value" = $2, origin = $3, verification = $4,'
            " verified_by = $5, confidence = $6 WHERE id = $1",
            updated.id,
            updated.value,
            updated.origin,
            updated.verification,
            updated.verified_by,
            updated.confidence,
        )
        return updated


_repo: CaseRepo | None = None


def get_repo() -> CaseRepo:
    global _repo
    if _repo is None:
        dsn = os.environ.get("DATABASE_URL", "")
        _repo = PostgresRepo(dsn) if dsn else MemoryRepo()
    return _repo
