import pytest

from done_by_morning.agent import ResearchAgent
from done_by_morning.llm import MockLLM
from done_by_morning.search import MockSearch

QUESTION = "AI document intake for small accounting firms"


@pytest.fixture
def agent():
    return ResearchAgent(MockLLM(), MockSearch(), progress=lambda _m: None)


@pytest.fixture(autouse=True)
def _no_real_keys(monkeypatch):
    # Tests must never reach paid APIs, even if a developer has keys exported.
    for var in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "TAVILY_API_KEY",
        "BRAVE_API_KEY",
        "DBM_LLM_PROVIDER",
        "DBM_SEARCH_PROVIDER",
    ):
        monkeypatch.delenv(var, raising=False)
