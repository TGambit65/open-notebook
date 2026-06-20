"""Minimal JWT reading — decode claims WITHOUT signature verification.

Used only to read non-secret hints the provider embeds in its own access token
(token expiry, and provider-specific account ids). We never trust these for
authz; the provider validates the token on every request.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Optional


def _b64url_decode(segment: str) -> bytes:
    pad = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + pad)


def decode_claims(token: str) -> dict[str, Any]:
    """Return the JWT payload dict, or {} if the token isn't a readable JWT."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        return json.loads(_b64url_decode(parts[1]))
    except Exception:
        return {}


def jwt_exp(token: str) -> Optional[int]:
    """The `exp` (epoch seconds) claim if present."""
    exp = decode_claims(token).get("exp")
    return int(exp) if isinstance(exp, (int, float)) else None
