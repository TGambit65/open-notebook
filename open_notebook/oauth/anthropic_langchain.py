"""Claude-Code-impersonating ChatAnthropic for subscription OAuth.

Claude Pro/Max OAuth tokens are only accepted by the Anthropic Messages API
while the request looks like it came from the Claude Code CLI:

  * Bearer auth via the SDK's ``auth_token`` (NOT ``x-api-key``)
  * the oauth + claude-code beta headers (sent via ChatAnthropic's ``betas``)
  * a ``claude-cli/<version>`` user-agent and ``x-app: cli``
  * a mandatory FIRST system block: "You are Claude Code, ..."

Esperanto's ``to_langchain()`` can't express any of this (it only passes
model/max_tokens/api_key), so ModelManager routes OAuth-anthropic credentials
here instead. We subclass ``ChatAnthropic`` so all message/tool/streaming
translation is reused; only the client construction and the system block are
overridden.
"""

from __future__ import annotations

import os
from functools import cached_property
from typing import Any, Optional, Union

from langchain_anthropic import ChatAnthropic
from loguru import logger
from pydantic import Field

from open_notebook.oauth.lc_shim import LangchainPassthrough

CLAUDE_CODE_SYSTEM = "You are Claude Code, Anthropic's official CLI for Claude."

# oauth-2025-04-20 + claude-code-20250219 are the gate for subscription OAuth;
# fine-grained-tool-streaming is a harmless feature beta Claude Code also sends.
OAUTH_BETAS = [
    "claude-code-20250219",
    "oauth-2025-04-20",
    "fine-grained-tool-streaming-2025-05-14",
]

# The user-agent version should track a recent Claude Code release; a badly
# stale value can be rejected. Override with OPEN_NOTEBOOK_CLAUDE_CLI_VERSION.
DEFAULT_CLAUDE_CLI_VERSION = "2.1.74"

DEFAULT_MAX_TOKENS = 8192


def _prepend_identity(
    system: Union[str, list, None],
) -> Union[str, list]:
    """Ensure the Claude Code identity is the first system block."""
    block = {"type": "text", "text": CLAUDE_CODE_SYSTEM}
    if not system:
        return [block]
    if isinstance(system, str):
        if system.strip() == CLAUDE_CODE_SYSTEM:
            return [block]
        return [block, {"type": "text", "text": system}]
    if isinstance(system, list):
        first = system[0] if system else None
        if isinstance(first, dict) and first.get("text") == CLAUDE_CODE_SYSTEM:
            return system
        return [block, *system]
    return system


class ClaudeCodeChatAnthropic(ChatAnthropic):
    """ChatAnthropic authenticated with a Claude subscription OAuth bearer."""

    # Declared as fields (not private attrs) so they are populated BEFORE
    # ChatAnthropic's after-validator builds the SDK client from _client_params.
    # excluded from serialization since the token is a secret.
    oauth_access_token: str = Field(default="", exclude=True, repr=False)
    claude_cli_version: str = Field(default=DEFAULT_CLAUDE_CLI_VERSION, exclude=True)

    def __init__(
        self,
        *,
        oauth_access_token: str,
        claude_cli_version: Optional[str] = None,
        **kwargs: Any,
    ):
        # Placeholder api_key satisfies ChatAnthropic's required field; it is
        # dropped in _client_params in favour of auth_token.
        kwargs.setdefault("anthropic_api_key", "oauth-placeholder")
        kwargs.setdefault("betas", list(OAUTH_BETAS))
        kwargs.setdefault("anthropic_api_url", "https://api.anthropic.com")
        kwargs["oauth_access_token"] = oauth_access_token
        kwargs["claude_cli_version"] = claude_cli_version or os.getenv(
            "OPEN_NOTEBOOK_CLAUDE_CLI_VERSION", DEFAULT_CLAUDE_CLI_VERSION
        )
        super().__init__(**kwargs)

    def _impersonation_headers(self) -> dict[str, str]:
        return {
            "x-app": "cli",
            "user-agent": f"claude-cli/{self.claude_cli_version} (external, cli)",
            "anthropic-dangerous-direct-browser-access": "true",
        }

    @cached_property
    def _client_params(self) -> dict[str, Any]:
        # Start from the parent's computed params, then swap api_key -> auth_token
        # (Bearer) and add the Claude Code identity headers.
        params: dict[str, Any] = ChatAnthropic._client_params.func(self)
        params.pop("api_key", None)
        params["auth_token"] = self.oauth_access_token
        headers = dict(params.get("default_headers") or {})
        headers.update(self._impersonation_headers())
        params["default_headers"] = headers
        return params

    def _get_request_payload(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        payload = super()._get_request_payload(*args, **kwargs)
        payload["system"] = _prepend_identity(payload.get("system"))
        return payload


def build_claude_oauth_model(
    model_name: str,
    access_token: str,
    extra_kwargs: Optional[dict[str, Any]] = None,
) -> LangchainPassthrough:
    """Build the OAuth-authenticated Claude chat model (wrapped for ModelManager)."""
    kwargs: dict[str, Any] = {"model": model_name, "max_tokens": DEFAULT_MAX_TOKENS}
    for key in ("temperature", "top_p", "max_tokens"):
        if extra_kwargs and key in extra_kwargs and extra_kwargs[key] is not None:
            kwargs[key] = extra_kwargs[key]
    logger.debug(f"Building Claude OAuth model '{model_name}' (Claude Code impersonation)")
    lc_model = ClaudeCodeChatAnthropic(oauth_access_token=access_token, **kwargs)
    return LangchainPassthrough(lc_model)
