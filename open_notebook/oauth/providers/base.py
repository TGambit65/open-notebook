"""OAuth provider abstraction.

`ProviderSpec` holds the (mostly static) constants for one subscription
provider; `OAuthProvider` runs the generic OIDC-style Authorization Code + PKCE
machinery over those constants. Provider-specific quirks are expressed as data
on the spec (extra authorize params, token-body style, challenge re-echo) so the
common code stays small.

HTTP is synchronous (httpx.Client) so the same methods serve both the
interactive CLI and the server-side refresh (which wraps them in a thread).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from loguru import logger

from open_notebook.oauth.jwt_utils import jwt_exp

_HTTP_TIMEOUT = 30.0


class OAuthError(Exception):
    """OAuth login/refresh failure."""


@dataclass
class OAuthTokens:
    """Result of a login or refresh."""

    access_token: str
    refresh_token: Optional[str]
    expires_at: float  # epoch seconds
    token_type: str = "Bearer"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderSpec:
    """Static configuration for one subscription-OAuth provider."""

    id: str
    display_name: str
    client_id: str
    scope: str
    redirect_uri: str
    redirect_port: int
    redirect_path: str
    # How Open Notebook should call this provider for inference once we hold a
    # token: the Esperanto provider name + the base URL it should target.
    esperanto_provider: str
    inference_base_url: str
    # Endpoints: either hardcoded, or discovered from an OIDC document.
    authorize_url: Optional[str] = None
    token_url: Optional[str] = None
    discovery_url: Optional[str] = None
    # Quirks.
    extra_authorize_params: dict[str, str] = field(default_factory=dict)
    token_request_style: str = "form"  # "form" | "json"
    echo_challenge_in_token: bool = False  # xAI re-validates the challenge
    uses_loopback: bool = True
    # Inference wire format, so the integration layer knows whether the OAuth
    # bearer can ride Esperanto's normal client ("openai_chat") or needs a
    # custom adapter ("anthropic_messages", "openai_responses").
    wire_format: str = "openai_chat"


class OAuthProvider:
    """Authorization Code + PKCE (S256) flow driven by a ProviderSpec."""

    def __init__(self, spec: ProviderSpec):
        self.spec = spec
        self._endpoints_resolved = False

    # -- endpoint resolution -------------------------------------------------
    def _resolve_endpoints(self) -> None:
        if self._endpoints_resolved:
            return
        if self.spec.discovery_url and not (
            self.spec.authorize_url and self.spec.token_url
        ):
            with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
                resp = client.get(self.spec.discovery_url)
                resp.raise_for_status()
                doc = resp.json()
            self.spec.authorize_url = self.spec.authorize_url or doc["authorization_endpoint"]
            self.spec.token_url = self.spec.token_url or doc["token_endpoint"]
        if not (self.spec.authorize_url and self.spec.token_url):
            raise OAuthError(f"{self.spec.id}: could not resolve OAuth endpoints")
        self._endpoints_resolved = True

    # -- authorize -----------------------------------------------------------
    def build_authorize_url(self, challenge: str, state: str) -> str:
        self._resolve_endpoints()
        params = {
            "response_type": "code",
            "client_id": self.spec.client_id,
            "redirect_uri": self.spec.redirect_uri,
            "scope": self.spec.scope,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
        params.update(self.spec.extra_authorize_params)
        return f"{self.spec.authorize_url}?{urlencode(params)}"

    # -- token exchange / refresh -------------------------------------------
    def exchange_code(self, code: str, verifier: str, challenge: str) -> OAuthTokens:
        self._resolve_endpoints()
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.spec.redirect_uri,
            "client_id": self.spec.client_id,
            "code_verifier": verifier,
        }
        if self.spec.echo_challenge_in_token:
            body["code_challenge"] = challenge
            body["code_challenge_method"] = "S256"
        return self._token_request(body)

    def refresh(self, refresh_token: str) -> OAuthTokens:
        self._resolve_endpoints()
        body = {
            "grant_type": "refresh_token",
            "client_id": self.spec.client_id,
            "refresh_token": refresh_token,
        }
        return self._token_request(body, old_refresh=refresh_token)

    def _token_request(
        self, body: dict[str, str], old_refresh: Optional[str] = None
    ) -> OAuthTokens:
        assert self.spec.token_url
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            if self.spec.token_request_style == "json":
                resp = client.post(self.spec.token_url, json=body)
            else:
                resp = client.post(
                    self.spec.token_url,
                    data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        if resp.status_code >= 400:
            raise OAuthError(
                f"{self.spec.id}: token endpoint returned {resp.status_code}: "
                f"{resp.text[:300]}"
            )
        return self._tokens_from_response(resp.json(), old_refresh)

    def _tokens_from_response(
        self, data: dict[str, Any], old_refresh: Optional[str]
    ) -> OAuthTokens:
        access = data.get("access_token")
        if not access:
            raise OAuthError(f"{self.spec.id}: response missing access_token")
        # Most of these providers rotate the refresh token; keep the old one only
        # if the server didn't return a new one.
        refresh = data.get("refresh_token") or old_refresh
        expires_at = self._compute_expiry(access, data.get("expires_in"))
        reserved = {"access_token", "refresh_token", "expires_in"}
        extra = {k: v for k, v in data.items() if k not in reserved}
        logger.debug(
            f"{self.spec.id}: token ok (expires_at={expires_at:.0f}, "
            f"rotated_refresh={bool(data.get('refresh_token'))})"
        )
        return OAuthTokens(
            access_token=access,
            refresh_token=refresh,
            expires_at=expires_at,
            token_type=data.get("token_type", "Bearer"),
            extra=extra,
        )

    def _compute_expiry(self, access: str, expires_in: Any) -> float:
        exp = jwt_exp(access)
        if exp:
            return float(exp)
        if expires_in:
            try:
                return time.time() + float(expires_in)
            except (TypeError, ValueError):
                pass
        return time.time() + 3600.0
