"""Audit wiring (GAP-014): every case/run/document access records who/when."""

import os
import time
from pathlib import Path

from app.security import AuditLog


def record(actor: str, action: str, resource: str) -> None:
    path = Path(os.environ.get("AUDIT_LOG", "data/audit/audit.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    AuditLog(path).append(
        {
            "actor": actor or "dev",  # "" = auth disabled
            "action": action,
            "resource": resource,
            "at": int(time.time()),
        }
    )
