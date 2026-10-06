import json
from types import SimpleNamespace

import httpx
import pytest

from done_by_morning.llm import AnthropicLLM, LLMError, MockLLM, OpenAILLM
from done_by_morning.providers import build_llm, build_search
from done_by_morning.search import BraveSearch, MockSearch, SearchError, TavilySearch


def test_build_search_auto_requires_a_key():
    with pytest.raises(SearchError):
        build_search(env={})
    assert isinstance(build_search(env={"TAVILY_API_KEY": "t"}), TavilySearch)
    assert isinstance(build_search(env={"BRAVE_API_KEY": "b"}), BraveSearch)
    assert isinstance(build_search("mock", env={}), MockSearch)


def test_build_llm_mock_and_unknown():
    assert isinstance(build_llm("mock", env={}), MockLLM)
    with pytest.raises(ValueError):
        build_llm("nope", env={})


def test_tavily_parses_results():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer key"
        body = json.loads(request.content)
        assert body["max_results"] == 2
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "T", "url": "https://example.com/t", "content": "snippet"},
                    {"title": "no url"},
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    results = TavilySearch("key", client=client).search("q", 2)
    assert [(r.title, r.url, r.snippet) for r in results] == [
        ("T", "https://example.com/t", "snippet")
    ]


def test_brave_parses_results_and_strips_markup():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Subscription-Token"] == "key"
        assert request.url.params["count"] == "3"
        return httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {
                            "title": "B",
                            "url": "https://example.com/b",
                            "description": "<strong>bold</strong>",
                        },
                    ]
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    results = BraveSearch("key", client=client).search("q", 3)
    assert results[0].snippet == "bold"


def test_search_http_error_becomes_search_error():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429)))
    with pytest.raises(SearchError):
        TavilySearch("key", client=client).search("q", 2)


class FakeAnthropic:
    def __init__(self, stop_reason="end_turn", text="hello"):
        self.calls = []
        response = SimpleNamespace(
            stop_reason=stop_reason,
            content=[
                SimpleNamespace(type="thinking", thinking=""),
                SimpleNamespace(type="text", text=text),
            ],
        )
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self._response = response

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def test_anthropic_request_shape_and_text_extraction():
    fake = FakeAnthropic()
    llm = AnthropicLLM(client=fake)
    assert llm.complete("sys", "prompt", task="plan") == "hello"
    call = fake.calls[0]
    assert call["model"] == "claude-sonnet-5-5"
    assert call["system"] == "sys"
    assert call["messages"] == [{"role": "user", "content": "prompt"}]
    assert call["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"]


def test_anthropic_fallbacks_can_be_disabled_and_refusal_raises():
    fake = FakeAnthropic(stop_reason="refusal")
    llm = AnthropicLLM(client=fake, use_fallbacks=False)
    with pytest.raises(LLMError):
        llm.complete("s", "p", task="plan")
    assert "fallbacks" not in fake.calls[0]


def test_openai_request_shape():
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    assert OpenAILLM(model="m", client=client).complete("s", "p", task="plan") == "ok"
    assert calls[0]["messages"][0] == {"role": "system", "content": "s"}
