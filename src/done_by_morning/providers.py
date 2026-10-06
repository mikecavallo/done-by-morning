"""Build providers from names and environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping

from .llm import DEFAULT_ANTHROPIC_MODEL, DEFAULT_OPENAI_MODEL, AnthropicLLM, MockLLM, OpenAILLM
from .search import BraveSearch, MockSearch, SearchError, TavilySearch

LLM_CHOICES = ("anthropic", "openai", "mock")
SEARCH_CHOICES = ("auto", "tavily", "brave", "mock")


def _truthy(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def build_llm(name: str | None = None, env: Mapping[str, str] | None = None):
    env = os.environ if env is None else env
    name = (name or env.get("DBM_LLM_PROVIDER") or "anthropic").lower()
    if name == "anthropic":
        return AnthropicLLM(
            model=env.get("DBM_ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL,
            use_fallbacks=_truthy(env.get("DBM_ANTHROPIC_FALLBACKS"), True),
        )
    if name == "openai":
        return OpenAILLM(model=env.get("DBM_OPENAI_MODEL") or DEFAULT_OPENAI_MODEL)
    if name == "mock":
        return MockLLM()
    raise ValueError(f"Unknown LLM provider {name!r}; choose from {', '.join(LLM_CHOICES)}.")


def build_search(name: str | None = None, env: Mapping[str, str] | None = None):
    env = os.environ if env is None else env
    name = (name or env.get("DBM_SEARCH_PROVIDER") or "auto").lower()
    if name == "auto":
        if env.get("TAVILY_API_KEY"):
            name = "tavily"
        elif env.get("BRAVE_API_KEY"):
            name = "brave"
        else:
            raise SearchError(
                "No search API key found. Set TAVILY_API_KEY or BRAVE_API_KEY, "
                "or run offline with --search mock (or --offline)."
            )
    if name == "tavily":
        return TavilySearch(env.get("TAVILY_API_KEY", ""))
    if name == "brave":
        return BraveSearch(env.get("BRAVE_API_KEY", ""))
    if name == "mock":
        return MockSearch(env.get("DBM_MOCK_FIXTURES") or None)
    raise ValueError(f"Unknown search provider {name!r}; choose from {', '.join(SEARCH_CHOICES)}.")
