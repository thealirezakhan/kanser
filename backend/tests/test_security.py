import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_sha256_matches_hashlib():
    from app.security import sha256_bytes

    data = b"lung-ct-slice"
    assert sha256_bytes(data) == hashlib.sha256(data).hexdigest()


def test_aes256_roundtrip_and_wrong_key():
    from app.security import aes_decrypt, aes_encrypt

    key = b"k" * 32
    blob = aes_encrypt(key, b"secret phi payload")
    assert aes_decrypt(key, blob) == b"secret phi payload"
    with pytest.raises(ValueError):
        aes_decrypt(b"w" * 32, blob)


def test_audit_log_chain_verify_and_tamper_detected(tmp_path):
    from app.security import AuditLog

    log_path = tmp_path / "audit.jsonl"
    audit = AuditLog(log_path)
    audit.append({"actor": "api", "action": "case.create", "id": "1"})
    audit.append({"actor": "agent", "action": "radiology.run", "id": "2"})
    audit.append({"actor": "agent", "action": "consensus", "id": "3"})
    assert audit.verify() is True

    lines = log_path.read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[1])
    event["action"] = "tampered"
    lines[1] = json.dumps(event, separators=(",", ":"))
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert AuditLog(log_path).verify() is False


def test_rate_limiter_unit():
    from app.limits import SlidingWindowLimiter

    lim = SlidingWindowLimiter(max_calls=2, period=60)
    assert lim.allow("ip1") is True
    assert lim.allow("ip1") is True
    assert lim.allow("ip1") is False
    assert lim.allow("ip2") is True


def test_diagnose_rate_limit_429_envelope():
    cid = client.post(
        "/api/cases", json={"patient_ref": "r", "modalities": []}
    ).json()["data"]["id"]
    codes = [
        client.post(f"/api/cases/{cid}/diagnose").status_code for _ in range(6)
    ]
    assert codes == [202, 202, 202, 202, 202, 429]
    r = client.post(f"/api/cases/{cid}/diagnose")
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"


def test_security_headers_present():
    r = client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"


def test_cors_allowlist():
    r = client.get(
        "/api/health", headers={"Origin": "http://localhost:3000"}
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
    r = client.get("/api/health", headers={"Origin": "http://evil.test"})
    assert r.headers.get("access-control-allow-origin") is None


def test_ingest_sha256_and_tamper_detect(tmp_path, monkeypatch):
    from app.security import verify_integrity

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    content = b"DICOM-PIXEL-DATA"
    r = client.post(
        "/api/documents/ingest",
        files={"file": ("scan.dcm", content, "application/dicom")},
    )
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["sha256"] == hashlib.sha256(content).hexdigest()
    assert ".." not in data["filename"]

    stored = next(p for p in tmp_path.iterdir() if not p.name.endswith(".sha256"))
    assert verify_integrity(stored, data["sha256"]) is True
    stored.write_bytes(b"TAMPERED")
    assert verify_integrity(stored, data["sha256"]) is False


def test_pii_guard_blocks_and_strips():
    from app.pii import PiiGuard, UnscrubbedPayloadError

    guard = PiiGuard()
    dirty = "Patient John Smith, MRN 12345678, phone 555-123-4567"
    with pytest.raises(UnscrubbedPayloadError):
        guard.assert_clean(dirty)
    clean = guard.anonymize(dirty)
    assert "John Smith" not in clean
    assert "12345678" not in clean
    guard.assert_clean(clean)
