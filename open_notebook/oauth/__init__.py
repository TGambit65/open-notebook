"""
Subscription-OAuth authentication for Open Notebook.

Lets a self-hosting user log in with their existing AI *subscription* (e.g.
SuperGrok / Claude Pro/Max / ChatGPT) via OAuth instead of a pay-as-you-go API
key. The OAuth access token is stored inside a normal `Credential` record
(encrypted at rest like any api_key) and refreshed on demand server-side; only
the initial login needs a browser.

Design (ported from the pi-ai `OAuthProviderInterface` shape, not wired to any
external tool at runtime):

    providers/base.py  - OAuthProvider + ProviderSpec + OAuthTokens
    providers/<id>.py  - one module per provider (xai, ...)
    pkce.py            - PKCE S256 helpers
    jwt_utils.py       - read `exp`/claims from a JWT access token (no verify)
    callback_server.py - localhost loopback capture for the redirect
    flow.py            - run the interactive login, return OAuthTokens
    store.py           - OAuthTokens <-> Credential, refresh-on-demand
    __main__.py        - `python -m open_notebook.oauth login <provider>`

The refresh path (store.refresh_credential_if_needed) is called by
ModelManager.get_model() right before building the Esperanto config.
"""

from open_notebook.oauth.providers import get_provider, list_providers

__all__ = ["get_provider", "list_providers"]
