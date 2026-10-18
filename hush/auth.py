"""Authentication: password login -> signed session cookie, plus short-lived
signed URLs so external players (VLC, Kodi, smart TVs) can open a stream
without a browser session."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from fastapi import HTTPException, Request

COOKIE = "hush_session"
SESSION_TTL = 30 * 24 * 3600


class Auth:
    def __init__(self, password: str, secret_key: str):
        self.password = password
        self.key = secret_key.encode()
        # Token ffmpeg uses on the loopback raw endpoint; never leaves the process.
        self.internal_token = secrets.token_urlsafe(32)
        self._failures: dict[str, list[float]] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.password)

    def _sig(self, msg: str) -> str:
        return hmac.new(self.key, msg.encode(), hashlib.sha256).hexdigest()[:40]

    # ---- sessions ---------------------------------------------------------
    def check_password(self, attempt: str, client: str) -> bool:
        now = time.time()
        recent = [t for t in self._failures.get(client, []) if now - t < 300]
        if len(recent) >= 8:
            raise HTTPException(429, "Too many attempts, try again in a few minutes")
        ok = hmac.compare_digest(attempt.encode(), self.password.encode())
        if not ok:
            recent.append(now)
        self._failures[client] = recent if not ok else []
        return ok

    def make_session(self) -> str:
        exp = str(int(time.time()) + SESSION_TTL)
        return f"{exp}.{self._sig('session:' + exp)}"

    def valid_session(self, value: str | None) -> bool:
        if not value or "." not in value:
            return False
        exp, sig = value.split(".", 1)
        return (exp.isdigit() and int(exp) > time.time()
                and hmac.compare_digest(sig, self._sig("session:" + exp)))

    # ---- signed URLs ----------------------------------------------------
    def sign_path(self, path: str, ttl: int = 12 * 3600) -> str:
        exp = str(int(time.time()) + ttl)
        return f"{exp}.{self._sig('url:' + path + ':' + exp)}"

    def valid_signature(self, path: str, token: str | None) -> bool:
        if not token or "." not in token:
            return False
        exp, sig = token.split(".", 1)
        return (exp.isdigit() and int(exp) > time.time()
                and hmac.compare_digest(sig, self._sig("url:" + path + ":" + exp)))

    # ---- FastAPI dependency ---------------------------------------------
    def require(self, request: Request) -> None:
        if not self.enabled:
            return
        if self.valid_session(request.cookies.get(COOKIE)):
            return
        if self.valid_signature(request.url.path, request.query_params.get("sig")):
            return
        raise HTTPException(401, "Login required")
