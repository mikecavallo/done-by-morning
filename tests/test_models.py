import pytest

from done_by_morning.models import ResearchRequest, slugify


def test_request_defaults_and_validation():
    req = ResearchRequest(question="  What is X?  ")
    assert req.question == "What is X?"
    assert req.depth == "standard"
    assert req.id.endswith("what-is-x")
    with pytest.raises(ValueError):
        ResearchRequest(question="")
    with pytest.raises(ValueError):
        ResearchRequest(question="q", depth="extreme")


def test_from_dict_ignores_unknown_keys():
    req = ResearchRequest.from_dict({"question": "q", "id": "abc", "plan": "Focused"})
    assert req.id == "abc"


def test_slugify():
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("!!!") == "request"
