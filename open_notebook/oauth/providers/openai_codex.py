"""OpenAI Codex subscription OAuth (ChatGPT Plus / Pro).

Login: Authorization Code + PKCE (S256) with a localhost callback on :1455
(auth.openai.com). In Docker the loopback page won't load, so the two-step
paste flow is used: approve, then paste the redirected localhost URL (which
carries ?code=&state=).

Inference: the ChatGPT backend's OpenAI **Responses API** at
https://chatgpt.com/backend-api/codex (NOT chat/completions). The OAuth bearer
rides OpenAI's SDK auth (Authorization: Bearer), but the request also needs
``store: false``, a ``chatgpt-account-id`` derived from the access-token JWT,
and a first-party Cloudflare fingerprint (originator + user-agent). See
oauth/openai_codex_langchain.py. wire_format routes ModelManager to that
custom builder.
"""

from __future__ import annotations

from open_notebook.oauth.providers.base import ProviderSpec

CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"

SPEC = ProviderSpec(
    id="openai-codex",
    display_name="OpenAI Codex (ChatGPT Plus/Pro subscription)",
    client_id=CODEX_CLIENT_ID,
    scope="openid profile email offline_access",
    redirect_uri="http://localhost:1455/auth/callback",
    redirect_port=1455,
    redirect_path="/auth/callback",
    esperanto_provider="openai",
    inference_base_url="https://chatgpt.com/backend-api/codex",
    authorize_url="https://auth.openai.com/oauth/authorize",
    token_url="https://auth.openai.com/oauth/token",
    extra_authorize_params={
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "originator": "codex_cli_rs",
    },
    token_request_style="form",
    echo_challenge_in_token=False,
    include_state_in_token=False,
    uses_loopback=True,
    wire_format="openai_responses_codex",
)
