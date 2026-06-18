"""xAI / Grok subscription OAuth (SuperGrok / X Premium).

Flow: Authorization Code + PKCE (S256) with an OIDC-discovered authorize/token
endpoint at https://auth.x.ai. Two non-standard quirks are required or login
fails with misleading errors:
  * the authorize request must carry `plan=generic`
  * the token exchange must re-echo `code_challenge` + `code_challenge_method`

Inference: the OAuth bearer is accepted by xAI's OpenAI-compatible API at
https://api.x.ai/v1, so the token rides Esperanto's normal `xai` client as the
api_key (verified working). Refresh tokens rotate on every refresh.
"""

from __future__ import annotations

from open_notebook.oauth.providers.base import ProviderSpec

# Grok-CLI's public OAuth client id (xAI gates subscription scopes on it).
XAI_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"

SPEC = ProviderSpec(
    id="xai",
    display_name="xAI Grok (SuperGrok subscription)",
    client_id=XAI_CLIENT_ID,
    scope="openid profile email offline_access grok-cli:access api:access",
    redirect_uri="http://127.0.0.1:56121/callback",
    redirect_port=56121,
    redirect_path="/callback",
    esperanto_provider="xai",
    inference_base_url="https://api.x.ai/v1",
    discovery_url="https://auth.x.ai/.well-known/openid-configuration",
    # `plan=generic` is required by xAI's authorize endpoint. `referrer` is
    # telemetry; we identify Open Notebook here.
    extra_authorize_params={"plan": "generic", "referrer": "open-notebook"},
    token_request_style="form",
    echo_challenge_in_token=True,
    uses_loopback=True,
    wire_format="openai_chat",
)
