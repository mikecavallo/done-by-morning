"""Plain data types shared across the pipeline."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

DEPTHS: dict[str, dict[str, int]] = {
    # sub_questions: how many angles to investigate
    # results_per_query: search hits kept per sub-question
    "quick": {"sub_questions": 3, "results_per_query": 3},
    "standard": {"sub_questions": 5, "results_per_query": 4},
    "deep": {"sub_questions": 8, "results_per_query": 6},
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def slugify(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug[:max_len].rstrip("-")) or "request"


@dataclass
class ResearchRequest:
    question: str
    depth: str = "standard"
    id: str = ""
    email: str = ""
    context: str = ""
    submitted_at: str = ""

    def __post_init__(self) -> None:
        self.question = (self.question or "").strip()
        if not self.question:
            raise ValueError("A research request needs a non-empty question.")
        if self.depth not in DEPTHS:
            raise ValueError(f"Unknown depth {self.depth!r}; choose from {', '.join(DEPTHS)}.")
        if not self.submitted_at:
            self.submitted_at = utcnow().isoformat(timespec="seconds")
        if not self.id:
            stamp = utcnow().strftime("%Y%m%d-%H%M%S")
            self.id = f"{stamp}-{slugify(self.question)}"

    @classmethod
    def from_dict(cls, data: dict) -> ResearchRequest:
        known = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        return cls(**known)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Source:
    id: int
    title: str
    url: str
    snippet: str
    found_for: str = ""


@dataclass
class Report:
    request: ResearchRequest
    sub_questions: list[str]
    sources: list[Source]
    body_markdown: str
    llm_provider: str
    search_provider: str
    generated_at: str = field(default_factory=lambda: utcnow().isoformat(timespec="seconds"))
    is_sample: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def cited_ids(self) -> set[int]:
        return {int(n) for n in re.findall(r"\[(\d+)\]", self.body_markdown)}
