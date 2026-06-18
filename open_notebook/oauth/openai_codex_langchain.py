"""Codex (ChatGPT subscription) OAuth inference via the OpenAI Responses API.

langchain_openai's ChatOpenAI already supports the Responses API + a custom
``openai_api_base`` + ``default_headers``, and the OpenAI SDK sends the api_key
as ``Authorization: Bearer``. But the ChatGPT *codex backend* has three quirks
ChatOpenAI doesn't satisfy out of the box:

  1. it requires a top-level ``instructions`` field — ChatOpenAI instead puts
     the system prompt into ``input``;
  2. it is streaming-only (``stream: true``);
  3. it rejects ``max_output_tokens``.

CodexChatOpenAI fixes (1) and (3) by overriding the payload, and (2) is handled
by constructing with ``streaming=True``. Auth is the OAuth bearer plus the
``chatgpt-account-id`` (from the access-token JWT) and the codex_cli_rs
Cloudflare fingerprint.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from langchain_core.language_models import LanguageModelInput
from langchain_openai import ChatOpenAI
from loguru import logger

from open_notebook.oauth.jwt_utils import decode_claims
from open_notebook.oauth.lc_shim import LangchainPassthrough

CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
CODEX_ORIGINATOR = "codex_cli_rs"
# Must be codex_cli_rs/-prefixed to pass the chatgpt.com edge; override with
# OPEN_NOTEBOOK_CODEX_USER_AGENT if OpenAI bumps the accepted client version.
DEFAULT_CODEX_USER_AGENT = "codex_cli_rs/0.21.0 (open-notebook)"
# Used only when a request carries no system prompt (the backend still requires
# a non-empty `instructions`).
DEFAULT_CODEX_INSTRUCTIONS = "You are a helpful assistant."


def account_id_from_token(access_token: str) -> Optional[str]:
    """Read chatgpt_account_id from the access-token JWT (claim path
    ``https://api.openai.com/auth``)."""
    claims = decode_claims(access_token)
    auth = claims.get("https://api.openai.com/auth")
    if isinstance(auth, dict):
        return auth.get("chatgpt_account_id")
    return None


def _system_text(messages) -> str:
    parts: list[str] = []
    for m in messages:
        if getattr(m, "type", None) != "system":
            continue
        content = m.content
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("text"):
                    parts.append(block["text"])
                elif isinstance(block, str):
                    parts.append(block)
    return "\n\n".join(p for p in parts if p).strip()


class CodexChatOpenAI(ChatOpenAI):
    """ChatOpenAI adapted to the ChatGPT codex Responses backend."""

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        # The codex backend wants the system prompt as top-level `instructions`,
        # not as a system item in `input`.
        messages = self._convert_input(input_).to_messages()
        payload["instructions"] = _system_text(messages) or DEFAULT_CODEX_INSTRUCTIONS
        if isinstance(payload.get("input"), list):
            payload["input"] = [
                item
                for item in payload["input"]
                if not (
                    isinstance(item, dict)
                    and item.get("role") in ("system", "developer")
                )
            ]
        # The codex backend rejects max_output_tokens.
        payload.pop("max_output_tokens", None)
        return payload


def build_codex_oauth_model(
    model_name: str,
    access_token: str,
    extra_kwargs: Optional[dict[str, Any]] = None,
) -> LangchainPassthrough:
    """Build the OAuth-authenticated Codex chat model (wrapped for ModelManager)."""
    account_id = account_id_from_token(access_token)
    headers: dict[str, str] = {
        "originator": CODEX_ORIGINATOR,
        "OpenAI-Beta": "responses=experimental",
        "User-Agent": os.getenv(
            "OPEN_NOTEBOOK_CODEX_USER_AGENT", DEFAULT_CODEX_USER_AGENT
        ),
    }
    if account_id:
        headers["chatgpt-account-id"] = account_id
    else:
        logger.warning(
            "Codex OAuth: no chatgpt_account_id in token JWT; the backend may 403."
        )

    kwargs: dict[str, Any] = {
        "model": model_name,
        "openai_api_key": access_token,
        "openai_api_base": CODEX_BASE_URL,
        "use_responses_api": True,
        "streaming": True,  # codex backend is streaming-only
        "default_headers": headers,
        "extra_body": {"store": False},
    }
    if extra_kwargs and extra_kwargs.get("temperature") is not None:
        kwargs["temperature"] = extra_kwargs["temperature"]

    logger.debug(
        f"Building Codex OAuth model '{model_name}' "
        f"(account_id={'set' if account_id else 'MISSING'})"
    )
    return LangchainPassthrough(CodexChatOpenAI(**kwargs))
