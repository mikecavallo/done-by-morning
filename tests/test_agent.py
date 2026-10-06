from done_by_morning.agent import ResearchAgent, parse_sub_questions, validate_citations
from done_by_morning.models import DEPTHS, ResearchRequest
from done_by_morning.search import MockSearch, SearchError, SearchResult

from .conftest import QUESTION


def test_parse_sub_questions_handles_numbered_and_bulleted_lists():
    text = "Here is the plan:\n1. First?\n2) Second?\n- Third?\n* first?\nnot a list item"
    assert parse_sub_questions(text, 10, "fallback") == ["First?", "Second?", "Third?"]


def test_parse_sub_questions_caps_and_falls_back():
    assert parse_sub_questions("1. a\n2. b\n3. c", 2, "q") == ["a", "b"]
    assert parse_sub_questions("no list here", 3, "the question") == ["the question"]


def test_validate_citations_drops_unknown_ids_but_keeps_links():
    body = "Known [1]. Unknown [7]. A [link](https://example.com) stays [2]."
    cleaned, warnings = validate_citations(body, {1, 2})
    assert "[7]" not in cleaned
    assert "Unknown." in cleaned
    assert "[link](https://example.com)" in cleaned
    assert warnings == ["Removed citation [7] that matched no gathered source."]


def test_run_produces_cited_report_with_depth_limits(agent):
    for depth, cfg in DEPTHS.items():
        report = agent.run(ResearchRequest(question=QUESTION, depth=depth))
        assert len(report.sub_questions) == cfg["sub_questions"]
        assert report.sources, depth
        ids = {s.id for s in report.sources}
        assert report.cited_ids <= ids
        assert report.cited_ids, "mock synthesis should cite sources"
        assert report.is_sample
        assert len({s.url for s in report.sources}) == len(report.sources)


class ScriptedLLM:
    name = "scripted"

    def __init__(self, synthesis):
        self.synthesis = synthesis

    def complete(self, system, prompt, task):
        if task == "plan":
            return "1. Alpha question\n2. Beta question"
        return self.synthesis


class FlakySearch:
    name = "flaky"

    def search(self, query, max_results):
        if "Beta" in query:
            raise SearchError("rate limited")
        return [
            SearchResult("A", "https://example.com/a", "alpha"),
            SearchResult("A again", "https://example.com/a/", "dupe"),
        ]


def test_run_strips_model_reference_section_and_bad_citations():
    synthesis = "## Executive summary\nClaim [1]. Made up [9].\n\n## References\n1. fake"
    agent = ResearchAgent(ScriptedLLM(synthesis), FlakySearch(), progress=lambda _m: None)
    report = agent.run(ResearchRequest(question="q?"))
    assert len(report.sources) == 1  # duplicate URL collapsed, failing search skipped
    assert "## References" not in report.body_markdown
    assert "[9]" not in report.body_markdown
    assert any("[9]" in w for w in report.warnings)
    assert not report.is_sample


def test_mock_search_returns_only_fixture_urls():
    results = MockSearch().search("pricing models per seat", 3)
    assert results
    assert all(r.url.startswith("https://example.") for r in results)
    assert MockSearch().search("zzzz qqqq", 3) == []
