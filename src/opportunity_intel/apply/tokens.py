"""Expiring, single-use HMAC approval tokens bound to a payload checksum."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class IssuedToken:
    token: str
    token_hash: str
    expires_at_unix: int


def issue_token(
    *, secret: str, application_id: int, payload_sha256: str, ttl_seconds: int
) -> IssuedToken:
    if ttl_seconds < 30 or ttl_seconds > 86_400:
        raise ValueError("Token TTL must be between 30 seconds and 1 day")
    expires = int(time.time()) + ttl_seconds
    nonce = secrets.token_hex(8)
    sig = _sign(secret, application_id, payload_sha256, expires, nonce)
    token = f"{application_id}.{expires}.{nonce}.{sig}"
    return IssuedToken(token=token, token_hash=_hash_token(token), expires_at_unix=expires)


def parse_and_verify(
    *,
    secret: str,
    token: str,
    application_id: int,
    payload_sha256: str,
    now: int | None = None,
) -> None:
    parts = (token or "").split(".")
    if len(parts) != 4:
        raise ValueError("Malformed approval token")
    try:
        token_app_id = int(parts[0])
        expires = int(parts[1])
    except ValueError as exc:
        raise ValueError("Malformed approval token") from exc
    nonce, sig = parts[2], parts[3]
    if token_app_id != application_id:
        raise ValueError("Token does not match this application")
    expected = _sign(secret, application_id, payload_sha256, expires, nonce)
    if not hmac.compare_digest(expected, sig):
        raise ValueError("Invalid approval token")
    current = int(time.time()) if now is None else now
    if current >= expires:
        raise ValueError("Approval token expired")


def hash_token(token: str) -> str:
    return _hash_token(token)


def _sign(secret: str, application_id: int, payload_sha256: str, expires: int, nonce: str) -> str:
    message = f"{application_id}|{payload_sha256}|{expires}|{nonce}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
