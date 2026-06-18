"""Provider registry.

Each entry maps a provider id to its ProviderSpec. Add a provider by dropping a
module next to this one that exposes a `SPEC` and registering it below.
"""

from __future__ import annotations

from open_notebook.oauth.providers import anthropic, xai
from open_notebook.oauth.providers.base import (
    OAuthError,
    OAuthProvider,
    OAuthTokens,
    ProviderSpec,
)

_SPECS: dict[str, ProviderSpec] = {
    xai.SPEC.id: xai.SPEC,
    anthropic.SPEC.id: anthropic.SPEC,
}


def list_providers() -> list[str]:
    return sorted(_SPECS)


def get_spec(provider_id: str) -> ProviderSpec:
    try:
        return _SPECS[provider_id]
    except KeyError:
        raise OAuthError(
            f"Unknown OAuth provider '{provider_id}'. "
            f"Available: {', '.join(list_providers())}"
        )


def get_provider(provider_id: str) -> OAuthProvider:
    return OAuthProvider(get_spec(provider_id))


__all__ = [
    "OAuthError",
    "OAuthProvider",
    "OAuthTokens",
    "ProviderSpec",
    "get_provider",
    "get_spec",
    "list_providers",
]
