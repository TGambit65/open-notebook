"""Persist OAuth tokens inside a Credential record, and refresh on demand.

Storage layout on a `Credential`:
  * provider   = spec.esperanto_provider   (e.g. "xai")
  * base_url   = spec.inference_base_url    (e.g. https://api.x.ai/v1)
  * api_key    = the OAuth ACCESS token     (Fernet-encrypted by Credential)
  * config["oauth"] = {
        provider_id, refresh_token (Fernet-encrypted), expires_at,
        wire_format, scope, obtained_at
    }

The access token rides Esperanto's normal client as the bearer. The refresh
token is the long-lived secret, so it is encrypted with the same Fernet key as
api_key rather than left plaintext in the config bag.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from loguru import logger
from pydantic import SecretStr

from open_notebook.domain.credential import Credential
from open_notebook.oauth.providers import OAuthProvider, get_spec
from open_notebook.oauth.providers.base import OAuthTokens, ProviderSpec
from open_notebook.utils.encryption import decrypt_value, encrypt_value

OAUTH_CONFIG_KEY = "oauth"
# Refresh this many seconds before the token actually expires.
REFRESH_SKEW_SECONDS = 300


def _build_oauth_meta(spec: ProviderSpec, tokens: OAuthTokens) -> dict[str, Any]:
    return {
        "provider_id": spec.id,
        "refresh_token": encrypt_value(tokens.refresh_token) if tokens.refresh_token else None,
        "expires_at": tokens.expires_at,
        "wire_format": spec.wire_format,
        "scope": spec.scope,
        "obtained_at": time.time(),
    }


def get_oauth_meta(credential: Credential) -> Optional[dict[str, Any]]:
    """Return the oauth metadata bag for a credential, or None if not an OAuth cred."""
    config = credential.config or {}
    meta = config.get(OAUTH_CONFIG_KEY)
    return meta if isinstance(meta, dict) else None


async def find_oauth_credential(provider_id: str) -> Optional[Credential]:
    """Find the existing OAuth credential for a provider id, if any."""
    spec = get_spec(provider_id)
    for cred in await Credential.get_by_provider(spec.esperanto_provider):
        meta = get_oauth_meta(cred)
        if meta and meta.get("provider_id") == provider_id:
            return cred
    return None


async def save_oauth_credential(
    provider_id: str, tokens: OAuthTokens, name: Optional[str] = None
) -> Credential:
    """Create or update the Credential that holds this provider's OAuth tokens."""
    spec = get_spec(provider_id)
    meta = _build_oauth_meta(spec, tokens)

    credential = await find_oauth_credential(provider_id)
    if credential is None:
        credential = Credential(
            name=name or f"{spec.display_name} (OAuth)",
            provider=spec.esperanto_provider,
            modalities=["language"],
        )
    config = dict(credential.config or {})
    config[OAUTH_CONFIG_KEY] = meta
    credential.config = config
    credential.base_url = spec.inference_base_url
    object.__setattr__(credential, "api_key", SecretStr(tokens.access_token))
    await credential.save()
    logger.info(
        f"Saved OAuth credential '{credential.name}' ({credential.id}) for {provider_id}"
    )
    return credential


def _seconds_to_expiry(meta: dict[str, Any]) -> float:
    return float(meta.get("expires_at", 0)) - time.time()


async def refresh_credential_if_needed(
    credential: Credential, *, skew: int = REFRESH_SKEW_SECONDS
) -> bool:
    """Refresh the OAuth access token if it's expired/near-expiry. Returns True if refreshed.

    Safe to call on any credential — no-ops for non-OAuth credentials. HTTP runs
    in a thread so it doesn't block the event loop.
    """
    meta = get_oauth_meta(credential)
    if not meta:
        return False
    if _seconds_to_expiry(meta) > skew:
        return False

    enc_refresh = meta.get("refresh_token")
    if not enc_refresh:
        logger.warning(
            f"OAuth credential {credential.id} has no refresh token; re-login required."
        )
        return False

    provider_id = meta.get("provider_id")
    spec = get_spec(provider_id)
    provider = OAuthProvider(spec)
    refresh_token = decrypt_value(enc_refresh)

    logger.info(f"Refreshing OAuth token for {provider_id} (credential {credential.id})")
    tokens = await asyncio.to_thread(provider.refresh, refresh_token)

    new_meta = _build_oauth_meta(spec, tokens)
    config = dict(credential.config or {})
    config[OAUTH_CONFIG_KEY] = new_meta
    credential.config = config
    object.__setattr__(credential, "api_key", SecretStr(tokens.access_token))
    await credential.save()
    return True
