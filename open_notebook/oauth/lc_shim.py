"""Tiny Esperanto-shaped wrapper around a ready LangChain chat model.

ModelManager returns one of these for OAuth providers that need a custom client;
callers do ``.to_langchain()`` to get the underlying model.
"""

from __future__ import annotations

from typing import Any


class LangchainPassthrough:
    def __init__(self, lc_model: Any):
        self._lc_model = lc_model

    def to_langchain(self) -> Any:
        return self._lc_model
