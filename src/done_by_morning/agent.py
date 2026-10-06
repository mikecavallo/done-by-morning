"""The research pipeline: plan -> gather -> synthesize -> validate citations."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

from .llm import LLMProvider
from .models import DEPTHS, Report, ResearchRequest, Source
from .search import SearchError, SearchProvider

log = logging.getLogger(__name__)

PLAN_SYSTEM = (
    "You are the planning step of an overnight business research service. "
    "Break the client's question into focused, independently searchable sub-questions "
    "that together answer it. Each sub-question must make sense on its own as a web "
    "search query. Reply with a numbered list only, one sub-question per line."
)

SYNTH_SYSTEM = (
    "You are the writing step of an overnight business research service. Write a clear, "
    "decision-oriented research report in Markdown using ONLY the numbered sources provided. "
    "Cite sources inline with their number in square brackets, e.g. [3]. Every factual claim "
    "needs a citation. Never cite a number that is not in the source list and never invent "
    "facts, figures, companies or quotes. If the sources do not answer something, say so. "
    "Use this structure: '## Executive summary', '## Findings' with a '### <n>. <sub-question>' "
    "subsection per sub-question, then '## Limitations and open questions'. Do not add a "
    "references section; it is appended automatically."
)

_LIST_ITEM = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+(.+?)\s*$")
_CITATION = re.compile(r"\[(\d+)\](?!\()")
_REFS_HEADING = re.compile(r"^#{1,6}\s*(references|sources|bibliography)\b.*$", re.I | re.M)


def parse_sub_questions(text: str, limit: int, fallback: str) -> list[str]:
    seen: list[str] = []
    for line in text.splitlines():
        match = _LIST_ITEM.match(line)
        if not match:
            continue
        item = match.group(1).strip().strip('"').strip()
        if item and item.lower() not in {s.lower() for s in seen}:
            seen.append(item)
    return seen[:limit] or [fallback]


def _one_line(text: str) -> str:
    return " ".join((text or "").split())


def _norm_url(url: str) -> str:
    return url.strip().rstrip("/").lower()


def validate_citations(body: str, valid_ids: set[int]) -> tuple[str, list[str]]:
    """Drop citations that point at sources we never gave the model."""
    bad: set[int] = set()

    def fix(match: re.Match) -> str:
        n = int(match.group(1))
        if n in valid_ids:
            return match.group(0)
        bad.add(n)
        return ""

    cleaned = _CITATION.sub(fix, body)
    cleaned = re.sub(r"[ \t]+([.,;:])", r"\1", cleaned)
    warnings = [f"Removed citation [{n}] that matched no gathered source." for n in sorted(bad)]
    return cleaned, warnings


class ResearchAgent:
    def __init__(
        self,
        llm: LLMProvider,
        search: SearchProvider,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self.llm = llm
        self.search = search
        self.progress = progress or (lambda msg: log.info(msg))

    def plan(self, request: ResearchRequest) -> list[str]:
        n = DEPTHS[request.depth]["sub_questions"]
        prompt = (
            f"Question: {_one_line(request.question)}\n"
            f"Client context: {_one_line(request.context) or 'none provided'}\n"
            f"Number of sub-questions: {n}\n"
        )
        raw = self.llm.complete(PLAN_SYSTEM, prompt, task="plan")
        return parse_sub_questions(raw, n, request.question)

    def gather(self, request: ResearchRequest, sub_questions: list[str]) -> list[Source]:
        k = DEPTHS[request.depth]["results_per_query"]
        sources: list[Source] = []
        seen: set[str] = set()
        for i, sq in enumerate(sub_questions, 1):
            self.progress(f"searching ({i}/{len(sub_questions)}): {sq}")
            try:
                results = self.search.search(sq, k)
            except SearchError as exc:
                self.progress(f"search failed for sub-question {i}: {exc}")
                continue
            for r in results:
                key = _norm_url(r.url)
                if not key or key in seen:
                    continue
                seen.add(key)
                sources.append(
                    Source(
                        id=len(sources) + 1,
                        title=_one_line(r.title) or r.url,
                        url=r.url.strip(),
                        snippet=_one_line(r.snippet),
                        found_for=f"SQ{i}",
                    )
                )
        return sources

    def synthesize(
        self, request: ResearchRequest, sub_questions: list[str], sources: list[Source]
    ) -> str:
        sq_block = "\n".join(f"SQ{i}: {q}" for i, q in enumerate(sub_questions, 1))
        src_block = "\n\n".join(
            f"[{s.id}] {s.title}\nURL: {s.url}\nFound for: {s.found_for}\nExcerpt: {s.snippet}"
            for s in sources
        )
        prompt = (
            f"Question: {_one_line(request.question)}\n"
            f"Client context: {_one_line(request.context) or 'none provided'}\n\n"
            f"Sub-questions:\n{sq_block}\n\n"
            f"Sources:\n{src_block or '(no sources were found)'}\n"
        )
        return self.llm.complete(SYNTH_SYSTEM, prompt, task="synthesize")

    def run(self, request: ResearchRequest) -> Report:
        self.progress(f"planning: {request.question}")
        sub_questions = self.plan(request)
        sources = self.gather(request, sub_questions)
        self.progress(f"gathered {len(sources)} sources; synthesizing")
        body = self.synthesize(request, sub_questions, sources)

        heading = _REFS_HEADING.search(body)
        if heading:
            body = body[: heading.start()].rstrip()
        body, warnings = validate_citations(body.strip(), {s.id for s in sources})
        if not sources:
            warnings.append("No sources were found; the report has nothing to cite.")

        return Report(
            request=request,
            sub_questions=sub_questions,
            sources=sources,
            body_markdown=body,
            llm_provider=self.llm.name,
            search_provider=self.search.name,
            is_sample=self.search.name == "mock" or self.llm.name == "mock",
            warnings=warnings,
        )
