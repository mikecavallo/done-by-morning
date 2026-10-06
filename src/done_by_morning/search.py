"""Pluggable web search providers.

Every provider returns a list of ``SearchResult`` for a query. Real providers call
Tavily or Brave over HTTPS; the mock provider scores a local JSON fixture so the
whole pipeline runs offline and deterministically.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Protocol

import httpx


class SearchError(RuntimeError):
    pass


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, max_results: int) -> list[SearchResult]: ...


class TavilySearch:
    name = "tavily"
    endpoint = "https://api.tavily.com/search"

    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        if not api_key:
            raise SearchError("TAVILY_API_KEY is not set.")
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=30)

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        try:
            resp = self.client.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"query": query, "max_results": max_results, "search_depth": "basic"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise SearchError(f"Tavily search failed: {exc}") from exc
        items = resp.json().get("results", [])
        return [
            SearchResult(i.get("title", ""), i.get("url", ""), i.get("content", ""))
            for i in items[:max_results]
            if i.get("url")
        ]


class BraveSearch:
    name = "brave"
    endpoint = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        if not api_key:
            raise SearchError("BRAVE_API_KEY is not set.")
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=30)

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        try:
            resp = self.client.get(
                self.endpoint,
                params={"q": query, "count": max_results},
                headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise SearchError(f"Brave search failed: {exc}") from exc
        items = resp.json().get("web", {}).get("results", [])
        return [
            SearchResult(
                i.get("title", ""), i.get("url", ""), _strip_tags(i.get("description", ""))
            )
            for i in items[:max_results]
            if i.get("url")
        ]


_STOPWORDS = set(
    "a an and are as at be by can do does for from how in is it of on or should the to "  # noqa: SIM905
    "what when where which who why will with we our your their this that".split()
)


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS and len(t) > 2}


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


class MockSearch:
    """Keyword-overlap search over a fixture file. No network access."""

    name = "mock"

    def __init__(self, fixture_path: str | Path | None = None) -> None:
        if fixture_path:
            raw = Path(fixture_path).read_text(encoding="utf-8")
        else:
            raw = (
                resources.files("done_by_morning")
                .joinpath("fixtures/search_fixtures.json")
                .read_text(encoding="utf-8")
            )
        self.documents = json.loads(raw)["documents"]

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        q = _tokens(query)
        docs = [
            (_tokens(" ".join([d["title"], d["snippet"]])), _tokens(" ".join(d["keywords"])), d)
            for d in self.documents
        ]
        df: dict[str, int] = {}
        for text_toks, kw_toks, _ in docs:
            for t in text_toks | kw_toks:
                df[t] = df.get(t, 0) + 1
        scored = []
        for idx, (text_toks, kw_toks, doc) in enumerate(docs):
            # Keyword matches drive the score; body text only breaks ties. Rare terms
            # count more (log IDF) so words shared by every fixture barely matter.
            score = sum(math.log(len(docs) / df[t]) for t in q & kw_toks)
            score += 0.1 * sum(math.log(len(docs) / df[t]) for t in q & text_toks)
            if score:
                scored.append((-score, idx, doc))
        scored.sort()
        if not scored:
            return []
        # Drop weak partial matches so each query returns on-topic fixtures only.
        cutoff = -scored[0][0] * 0.3
        return [
            SearchResult(d["title"], d["url"], d["snippet"])
            for neg, _, d in scored[:max_results]
            if -neg >= cutoff
        ]
