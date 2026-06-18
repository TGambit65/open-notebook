"""CLI: log a subscription provider in via OAuth and store it as a Credential.

Inside Docker (browser on the host), use paste mode:

    docker compose exec open_notebook \\
        uv run python -m open_notebook.oauth login xai --paste

Native installs can use the auto-capturing loopback flow (drop --paste).
After login, register a model against the new credential (UI Settings, the
REST API, or `/api/credentials/{id}/register-models`).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from open_notebook.oauth.flow import run_login
from open_notebook.oauth.providers import OAuthError, get_spec, list_providers
from open_notebook.oauth.store import (
    find_oauth_credential,
    get_oauth_meta,
    save_oauth_credential,
)


def _cmd_list(_args) -> int:
    print("Subscription-OAuth providers:\n")
    for pid in list_providers():
        spec = get_spec(pid)
        cred = asyncio.run(find_oauth_credential(pid))
        status = f"logged in ({cred.id})" if cred else "not logged in"
        print(f"  {pid:8s} {spec.display_name}\n           -> {status}")
    return 0


def _cmd_login(args) -> int:
    pid = args.provider
    get_spec(pid)  # validate early
    try:
        tokens = run_login(pid, paste=args.paste)
    except OAuthError as exc:
        print(f"Login failed: {exc}", file=sys.stderr)
        return 1
    cred = asyncio.run(save_oauth_credential(pid, tokens, name=args.name))
    print(f"\n✓ Logged in to {pid}. Credential: {cred.id}")
    print(
        "  Next: register a model against this credential "
        "(UI Settings → Models, or POST /api/models with "
        f'provider="{cred.provider}", type="language", credential="{cred.id}").'
    )
    return 0


def _cmd_logout(args) -> int:
    cred = asyncio.run(find_oauth_credential(args.provider))
    if not cred:
        print(f"No OAuth credential found for {args.provider}.")
        return 0
    asyncio.run(cred.delete())
    print(f"Removed OAuth credential {cred.id} for {args.provider}.")
    return 0


def _cmd_status(args) -> int:
    cred = asyncio.run(find_oauth_credential(args.provider))
    if not cred:
        print(f"{args.provider}: not logged in")
        return 0
    meta = get_oauth_meta(cred) or {}
    import time

    secs = float(meta.get("expires_at", 0)) - time.time()
    print(
        f"{args.provider}: logged in ({cred.id}); access token "
        f"{'valid' if secs > 0 else 'EXPIRED'}, ~{int(secs / 60)} min left "
        f"(auto-refreshes)."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m open_notebook.oauth")
    sub = parser.add_subparsers(dest="command", required=True)

    p_login = sub.add_parser("login", help="Authorize a provider via OAuth")
    p_login.add_argument("provider", choices=list_providers())
    p_login.add_argument(
        "--paste",
        action="store_true",
        help="Manual paste mode (required inside Docker)",
    )
    p_login.add_argument("--name", default=None, help="Credential display name")
    p_login.set_defaults(func=_cmd_login)

    p_list = sub.add_parser("list", help="List providers and login status")
    p_list.set_defaults(func=_cmd_list)

    p_logout = sub.add_parser("logout", help="Remove a provider's OAuth credential")
    p_logout.add_argument("provider", choices=list_providers())
    p_logout.set_defaults(func=_cmd_logout)

    p_status = sub.add_parser("status", help="Show token status for a provider")
    p_status.add_argument("provider", choices=list_providers())
    p_status.set_defaults(func=_cmd_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
