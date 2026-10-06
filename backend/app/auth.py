import hmac
import os
import time

import jwt
from fastapi import HTTPException, Request

# ponytail: symmetric HS256 with shared secret - fine single-service;
# switch to asymmetric (RS256) if services split
SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me-0123456789abcdef!")
TTL_SECONDS = 8 * 3600
PUBLIC_PATHS = {"/api/health", "/api/auth/login"}

_KNOWN_BAD_SECRETS = {
    "dev-secret-change-me-0123456789abcdef!",
    "change-me-32-bytes-min",
    "change-me-32-bytes-min-in-prod",
}


def assert_strong_secret() -> None:
    """Refuse known/default secrets when auth is enabled (GAP-014)."""
    if os.environ.get("DISABLE_AUTH") == "1":
        return
    secret = os.environ.get("JWT_SECRET", "")
    if len(secret) < 32 or secret in _KNOWN_BAD_SECRETS:
        raise RuntimeError(
            "JWT_SECRET missing, too short, or a known default; "
            "set a unique 32+ byte secret before enabling auth"
        )


def create_token(sub: str) -> str:
    claims = {"sub": sub, "exp": int(time.time()) + TTL_SECONDS}
    return jwt.encode(claims, SECRET, algorithm="HS256")


def verify_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    return str(payload.get("sub", ""))


def require_auth(request: Request) -> str:
    """Return the authenticated subject ("" when auth disabled/public)."""
    if os.environ.get("DISABLE_AUTH") == "1":
        return ""
    if request.url.path in PUBLIC_PATHS:
        return ""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return verify_token(header.removeprefix("Bearer ").strip())


def check_credentials(username: str, password: str) -> bool:
    expected_user = os.environ.get("ADMIN_USER", "admin")
    expected_pw = os.environ.get("ADMIN_PASSWORD", "admin")
    return hmac.compare_digest(username, expected_user) and hmac.compare_digest(
        password, expected_pw
    )
