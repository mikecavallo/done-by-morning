"""LLM providers: Anthropic Claude (default), OpenAI (optional), and an offline mock.

Each provider exposes ``complete(system, prompt, task) -> str``. ``task`` is a hint
("plan" or "synthesize") that only the mock provider uses, so it can produce
deterministic output without a model.
"""

from __future__ import annotations

import re
from typing import Protocol

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5-5"
DEFAULT_OPENAI_MODEL = "gpt-4.1"


class LLMError(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str

    def complete(self, system: str, prompt: str, task: str) -> str: ...


class AnthropicLLM:
    name = "anthropic"

    def __init__(
        self,
        model: str = DEFAULT_ANTHROPIC_MODEL,
        max_tokens: int = 16000,
        use_fallbacks: bool = True,
        client=None,
    ) -> None:
        if client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - depends on install
                raise LLMError(
                    "The anthropic package is not installed. "
                    "Run: pip install 'done-by-morning[anthropic]'"
                ) from exc
            client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY or an `ant auth` profile
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.use_fallbacks = use_fallbacks

    def complete(self, system: str, prompt: str, task: str) -> str:
        kwargs = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        if self.use_fallbacks:
            # Server-side refusal fallback: if a safety classifier declines, the API
            # re-runs the request on Anthropic's recommended fallback model.
            kwargs["betas"] = ["server-side-fallback-2026-07-01"]
            kwargs["fallbacks"] = "default"
        response = self.client.beta.messages.create(**kwargs)
        if response.stop_reason == "refusal":
            raise LLMError("The model declined this request (stop_reason=refusal).")
        text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
        if not text.strip():
            raise LLMError("The model returned an empty response.")
        return text


class OpenAILLM:
    name = "openai"

    def __init__(self, model: str = DEFAULT_OPENAI_MODEL, client=None) -> None:
        if client is None:
            try:
                import openai
            except ImportError as exc:  # pragma: no cover - depends on install
                raise LLMError(
                    "The openai package is not installed. "
                    "Run: pip install 'done-by-morning[openai]'"
                ) from exc
            client = openai.OpenAI()  # reads OPENAI_API_KEY
        self.client = client
        self.model = model

    def complete(self, system: str, prompt: str, task: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        text = response.choices[0].message.content or ""
        if not text.strip():
            raise LLMError("The model returned an empty response.")
        return text


_ANGLES = [
    "What does adoption look like today for {topic}?",
    "What are the typical costs and pricing models for {topic}?",
    "What measurable benefits are reported for {topic}?",
    "What are the main risks, including privacy and compliance, of {topic}?",
    "How long does implementation take and what does it require for {topic}?",
    "Which vendors or alternative approaches exist for {topic}?",
    "What do staff and clients need to change to make {topic} work?",
    "What should be measured in the first 90 days of {topic}?",
]


def _first_sentence(text: str) -> str:
    text = " ".join(text.split())
    match = re.match(r"(.+?[.!?])(\s|$)", text)
    return (match.group(1) if match else text).strip()


def _cite(sentence: str, source_id: str) -> str:
    body = sentence.rstrip(".!? ")
    end = sentence[len(body) :].strip() or "."
    return f"{body} [{source_id}]{end}"


class MockLLM:
    """Deterministic stand-in for a real model. Used for tests, demos and the sample report."""

    name = "mock"

    def complete(self, system: str, prompt: str, task: str) -> str:
        if task == "plan":
            return self._plan(prompt)
        if task == "synthesize":
            return self._synthesize(prompt)
        raise LLMError(f"MockLLM does not know task {task!r}")

    @staticmethod
    def _field(prompt: str, label: str) -> str:
        match = re.search(rf"^{label}:\s*(.+)$", prompt, re.MULTILINE)
        return match.group(1).strip() if match else ""

    def _plan(self, prompt: str) -> str:
        topic = self._field(prompt, "Question").rstrip("?.")
        count = int(self._field(prompt, "Number of sub-questions") or 5)
        lines = [a.format(topic=topic) for a in _ANGLES[:count]]
        return "\n".join(f"{i}. {line}" for i, line in enumerate(lines, 1))

    def _synthesize(self, prompt: str) -> str:
        topic = self._field(prompt, "Question").rstrip("?.")
        sub_questions = re.findall(r"^SQ(\d+):\s*(.+)$", prompt, re.MULTILINE)
        sources = re.findall(
            r"^\[(\d+)\] (.+)\nURL: .+\nFound for: SQ(\d+)\nExcerpt: (.+)$", prompt, re.MULTILINE
        )
        by_sq: dict[str, list[tuple[str, str]]] = {}
        for sid, _title, sq, excerpt in sources:
            by_sq.setdefault(sq, []).append((sid, _cite(_first_sentence(excerpt), sid)))

        lead = [_cite(_first_sentence(excerpt), sid) for sid, _t, _sq, excerpt in sources[:3]]
        out = [
            "## Executive summary",
            "",
            f"This report examines {topic} from {len(sub_questions)} angles using "
            f"{len(sources)} sources. " + " ".join(lead),
            "",
            "## Findings",
            "",
        ]
        for num, question in sub_questions:
            out.append(f"### {num}. {question}")
            out.append("")
            hits = by_sq.get(num, [])
            if hits:
                out.extend(f"- {text}" for _sid, text in hits)
            else:
                out.append("- No sources were found for this sub-question. Treat it as open.")
            out.append("")
        out += [
            "## Limitations and open questions",
            "",
            "- This draft was assembled by the offline mock model, which restates source "
            "excerpts rather than reasoning over them. A real run uses an LLM for synthesis.",
            "- Every statement above is only as reliable as its cited source. Check the "
            "references before acting on any figure.",
        ]
        return "\n".join(out)
