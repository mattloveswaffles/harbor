"""Accounts: password hashing, login tokens and login rate limiting.

- Passwords are hashed with scrypt (Python's standard library) and a random salt per password.
- A login returns a random token (`hbr_...`). Harbor stores only its SHA-256, and the token
  expires after TOKEN_DAYS or when the user logs out.
- Tokens use the real clock, not the demo clock: the demo replays October 2024.
- Five wrong passwords for one email within 15 minutes locks that email for 15 minutes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from harbor.models import AuthToken, Credential, User

TOKEN_DAYS = 30
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
MAX_FAILURES, FAILURE_WINDOW_S = 5, 15 * 60


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        check = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                               dklen=len(base64.b64decode(digest)))
        return hmac.compare_digest(check, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


# A real hash to compare against when the email is unknown, so both cases take the same time.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def _token_id(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_token(session: Session, user: User) -> tuple[str, datetime]:
    raw = "hbr_" + secrets.token_urlsafe(32)
    now = utcnow()
    expires = now + timedelta(days=TOKEN_DAYS)
    session.add(AuthToken(id=_token_id(raw), user_id=user.id, created_at=now, expires_at=expires))
    return raw, expires


def user_for_token(session: Session, raw: str) -> User | None:
    tok = session.get(AuthToken, _token_id(raw))
    if tok is None or tok.revoked_at is not None or (tok.expires_at and tok.expires_at <= utcnow()):
        return None
    return session.get(User, tok.user_id)


def revoke_token(session: Session, raw: str) -> None:
    tok = session.get(AuthToken, _token_id(raw))
    if tok is not None and tok.revoked_at is None:
        tok.revoked_at = utcnow()
        session.add(tok)


def check_login(session: Session, email: str, password: str) -> User | None:
    cred = session.exec(select(Credential).where(Credential.email == normalize_email(email))).first()
    if cred is None:
        verify_password(password, _DUMMY_HASH)
        return None
    return session.get(User, cred.user_id) if verify_password(password, cred.password_hash) else None


class LoginLimiter:
    """In-memory: good enough for one process (Harbor runs one worker)."""

    def __init__(self, max_failures: int = MAX_FAILURES, window_s: int = FAILURE_WINDOW_S, clock=time.monotonic):
        self.max_failures, self.window_s, self.clock = max_failures, window_s, clock
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str) -> list[float]:
        now = self.clock()
        kept = [t for t in self._failures.get(key, []) if now - t < self.window_s]
        self._failures[key] = kept
        return kept

    def locked(self, email: str) -> bool:
        with self._lock:
            return len(self._recent(normalize_email(email))) >= self.max_failures

    def failed(self, email: str) -> None:
        with self._lock:
            self._recent(normalize_email(email)).append(self.clock())

    def succeeded(self, email: str) -> None:
        with self._lock:
            self._failures.pop(normalize_email(email), None)
