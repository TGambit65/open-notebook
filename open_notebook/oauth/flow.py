"""Interactive login flow: PKCE + authorize + (loopback | manual paste).

`loopback` mode auto-captures the redirect and only works when the browser can
reach this process on 127.0.0.1 (native installs). `paste` mode prints the
authorize URL and asks the user to paste the redirected URL back — this is the
default inside Docker, where the browser is on the host and the redirect to
127.0.0.1:<port> never reaches the container.
"""

from __future__ import annotations

import sys
import webbrowser
from urllib.parse import parse_qs, urlparse

from loguru import logger

from open_notebook.oauth import pkce
from open_notebook.oauth.providers import OAuthError, get_provider
from open_notebook.oauth.providers.base import OAuthTokens


def _parse_redirect(pasted: str, expected_state: str) -> str:
    """Extract `code` from a pasted redirect URL (or a bare code), checking state."""
    pasted = pasted.strip()
    if pasted.startswith("http://") or pasted.startswith("https://"):
        qs = parse_qs(urlparse(pasted).query)
        if qs.get("error"):
            raise OAuthError(f"Authorization returned error: {qs['error'][0]}")
        code = (qs.get("code") or [None])[0]
        state = (qs.get("state") or [None])[0]
        if not code:
            raise OAuthError("Pasted URL has no ?code= parameter")
        if state and state != expected_state:
            raise OAuthError("State mismatch — possible CSRF; aborting")
        return code
    # Anthropic returns `<code>#<state>` for manual paste.
    if "#" in pasted:
        code, _, state = pasted.partition("#")
        if not code:
            raise OAuthError("No code in pasted value")
        if state and state != expected_state:
            raise OAuthError("State mismatch — possible CSRF; aborting")
        return code
    # Fallback: user pasted just the code.
    if not pasted:
        raise OAuthError("No code provided")
    return pasted


def run_login(provider_id: str, *, paste: bool = False, timeout: float = 300.0) -> OAuthTokens:
    """Run the browser login and return tokens. Blocks on user/browser action."""
    provider = get_provider(provider_id)
    spec = provider.spec

    verifier = pkce.generate_verifier()
    challenge = pkce.challenge_from_verifier(verifier)
    state = pkce.generate_state()
    authorize_url = provider.build_authorize_url(challenge, state)

    use_loopback = spec.uses_loopback and not paste

    if use_loopback:
        from open_notebook.oauth.callback_server import CallbackServer

        try:
            with CallbackServer(spec.redirect_port, spec.redirect_path) as server:
                _present_url(authorize_url, open_browser=True)
                logger.info(f"Waiting for redirect on {spec.redirect_uri} ...")
                captured = server.wait(timeout=timeout)
                if captured.get("error"):
                    raise OAuthError(f"Authorization error: {captured['error']}")
                if captured.get("state") != state:
                    raise OAuthError("State mismatch — possible CSRF; aborting")
                code = captured["code"]
                if not code:
                    raise OAuthError("Redirect carried no authorization code")
        except OSError as exc:
            # Port busy / no permission -> fall back to paste.
            logger.warning(f"Loopback capture unavailable ({exc}); using paste mode.")
            code = _paste_flow(authorize_url, state)
    else:
        code = _paste_flow(authorize_url, state)

    return provider.exchange_code(code, verifier, challenge, state=state)


def _present_url(url: str, *, open_browser: bool) -> None:
    print("\nOpen this URL in your browser to authorize:\n", file=sys.stderr)
    print(url + "\n", file=sys.stderr)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass


def _paste_flow(authorize_url: str, state: str) -> str:
    _present_url(authorize_url, open_browser=False)
    print(
        "After authorizing, your browser is redirected to a 127.0.0.1 URL that "
        "won't load.\nCopy that FULL address bar URL and paste it here.",
        file=sys.stderr,
    )
    pasted = input("Paste redirect URL (or just the code): ")
    return _parse_redirect(pasted, state)
