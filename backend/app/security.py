import hashlib
import json
import secrets
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_integrity(path: Path, expected_sha256: str) -> bool:
    return sha256_file(path) == expected_sha256


def aes_encrypt(key: bytes, plaintext: bytes) -> bytes:
    if len(key) != 32:
        raise ValueError("AES-256 key must be 32 bytes")
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, None)


def aes_decrypt(key: bytes, blob: bytes) -> bytes:
    if len(key) != 32:
        raise ValueError("AES-256 key must be 32 bytes")
    nonce, ciphertext = blob[:12], blob[12:]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None)
    except InvalidTag as exc:
        raise ValueError("decryption failed: bad key or tampered data") from exc


class AuditLog:
    """Append-only hash-chained JSONL log. verify() detects any mutation."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, event: dict) -> str:
        prev_hash = "0" * 64
        if self.path.exists():
            lines = self.path.read_text(encoding="utf-8").splitlines()
            if lines:
                prev_hash = json.loads(lines[-1])["hash"]
        entry = {**event, "prev": prev_hash}
        digest = hashlib.sha256(
            json.dumps(entry, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps({**entry, "hash": digest}, separators=(",", ":")) + "\n")
        return digest

    def verify(self) -> bool:
        if not self.path.exists():
            return True
        prev_hash = "0" * 64
        for line in self.path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            stored = entry.pop("hash")
            if entry.get("prev") != prev_hash:
                return False
            digest = hashlib.sha256(
                json.dumps(entry, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if digest != stored:
                return False
            prev_hash = stored
        return True
