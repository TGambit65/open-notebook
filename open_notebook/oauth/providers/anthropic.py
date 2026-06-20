"""Anthropic / Claude subscription OAuth (Claude Pro / Max).

Login: Authorization Code + PKCE (S256) with a REMOTE redirect and manual
paste. Anthropic's authorize page shows an authorization value of the form
`<code>#<state>`; the user pastes that back (no localhost callback, so this
works identically inside Docker). Token exchange/refresh use a JSON body.

Inference: Anthropic Messages API at https://api.anthropic.com — but the
subscription OAuth bearer is only accepted while impersonating the Claude Code
CLI (see oauth/anthropic_langchain.py). So wire_format is "anthropic_messages",
which routes ModelManager to a custom client instead of plain Esperanto.
"""

from __future__ import annotations

from open_notebook.oauth.providers.base import ProviderSpec

ANTHROPIC_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"

SPEC = ProviderSpec(
    id="anthropic",
    display_name="Claude (Pro/Max subscription)",
    client_id=ANTHROPIC_CLIENT_ID,
    scope="org:create_api_key user:profile user:inference",
    redirect_uri="https://console.anthropic.com/oauth/code/callback",
    redirect_port=0,
    redirect_path="",
    esperanto_provider="anthropic",
    inference_base_url="https://api.anthropic.com",
    authorize_url="https://claude.ai/oauth/authorize",
    token_url="https://console.anthropic.com/v1/oauth/token",
    # `code=true` makes Anthropic render the code#state for manual paste.
    extra_authorize_params={"code": "true"},
    token_request_style="json",
    echo_challenge_in_token=False,
    include_state_in_token=True,
    uses_loopback=False,
    wire_format="anthropic_messages",
)
