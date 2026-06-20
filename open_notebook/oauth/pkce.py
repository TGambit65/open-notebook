"""PKCE (RFC 7636) helpers — S256 only."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets


def _b64url(raw: bytes) -> str:
    """base64url without padding."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate_verifier() -> str:
    """High-entropy code_verifier (<=128 chars)."""
    return _b64url(os.urandom(64))[:128]


def challenge_from_verifier(verifier: str) -> str:
    """S256 code_challenge for a verifier."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return _b64url(digest)


def generate_state() -> str:
    """Opaque CSRF state value."""
    return secrets.token_urlsafe(32)
