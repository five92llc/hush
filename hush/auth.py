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


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_hash(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
    except ValueError:
        return False
    return hmac.compare_digest(got, bytes.fromhex(digest))


class Auth:
    def __init__(self, password: str, secret_key: str, stored_hash: str | None = None):
        self.password = password          # from config / HUSH_PASSWORD
        self.stored_hash = stored_hash    # set from the app; wins over the config password
        self.key = secret_key.encode()
        # Token ffmpeg uses on the loopback raw endpoint; never leaves the process.
        self.internal_token = secrets.token_urlsafe(32)
        self._failures: dict[str, list[float]] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.password or self.stored_hash)

    @property
    def _epoch(self) -> str:
        """Changes whenever the password does, which signs every old session out."""
        return hashlib.sha256((self.stored_hash or self.password).encode()).hexdigest()[:16]

    def set_password(self, new: str) -> str:
        self.stored_hash = hash_password(new)
        return self.stored_hash

    def _sig(self, msg: str) -> str:
        return hmac.new(self.key, msg.encode(), hashlib.sha256).hexdigest()[:40]

    # ---- sessions ---------------------------------------------------------
    def check_password(self, attempt: str, client: str) -> bool:
        now = time.time()
        recent = [t for t in self._failures.get(client, []) if now - t < 300]
        if len(recent) >= 8:
            raise HTTPException(429, "Too many attempts, try again in a few minutes")
        ok = self.verify(attempt)
        if not ok:
            recent.append(now)
        self._failures[client] = recent if not ok else []
        return ok

    def verify(self, attempt: str) -> bool:
        if self.stored_hash:
            return verify_hash(attempt, self.stored_hash)
        return hmac.compare_digest(attempt.encode(), self.password.encode())

    def make_session(self) -> str:
        exp = str(int(time.time()) + SESSION_TTL)
        return f"{exp}.{self._sig('session:' + exp + ':' + self._epoch)}"

    def valid_session(self, value: str | None) -> bool:
        if not value or "." not in value:
            return False
        exp, sig = value.split(".", 1)
        return (exp.isdigit() and int(exp) > time.time()
                and hmac.compare_digest(sig, self._sig("session:" + exp + ":" + self._epoch)))

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
