import json

import pytest

from done_by_morning.cli import main
from done_by_morning.models import ResearchRequest
from done_by_morning.queue import QueueLocked, enqueue, run_queue
from done_by_morning.render import SAMPLE_NOTICE, to_html, to_markdown, write_report

from .conftest import QUESTION


def test_markdown_and_html_contain_notice_plan_and_linked_citations(agent):
    report = agent.run(ResearchRequest(question=QUESTION, depth="quick"))
    text = to_markdown(report)
    assert SAMPLE_NOTICE in text
    assert "## Research plan" in text and "## References" in text
    page = to_html(report, back_link=("../", "Back"))
    assert 'href="#ref-1"' in page and 'id="ref-1"' in page
    assert "<script" not in page
    assert 'href="../"' in page


def test_html_escapes_untrusted_source_text(agent):
    report = agent.run(ResearchRequest(question="<b>x</b> pricing", depth="quick"))
    report.sources[0].title = "<script>alert(1)</script>"
    page = to_html(report)
    assert "<script>alert(1)</script>" not in page


def test_write_report_files(agent, tmp_path):
    report = agent.run(ResearchRequest(question=QUESTION, depth="quick"))
    paths = write_report(report, tmp_path / "out")
    assert {"markdown", "html", "json"} <= paths.keys()
    data = json.loads(paths["json"].read_text())
    assert data["cited_source_ids"]


def test_queue_processes_inbox_and_is_rerunnable(agent, tmp_path):
    root = tmp_path / "q"
    enqueue(root, ResearchRequest(question=QUESTION, depth="quick", id="one"))
    (root / "inbox" / "batch.json").write_text(
        json.dumps(
            [
                {"question": "pricing models", "depth": "quick", "id": "two"},
                {"question": "", "id": "bad"},
            ]
        )
    )
    results = run_queue(root, lambda: agent, log=lambda _m: None)
    statuses = sorted((r.source_file, r.status) for r in results)
    assert ("one.json", "done") in statuses
    assert ("batch.json", "failed") in statuses  # empty question invalidates the file
    assert (root / "reports" / "one" / "report.html").exists()
    assert (root / "reports" / "one" / "status.json").exists()
    assert (root / "done" / "one.json").exists()
    assert (root / "failed" / "batch.error.txt").exists()
    assert not list((root / "inbox").glob("*.json"))
    assert not (root / ".lock").exists()

    # Retry a failed file after fixing it: finished requests are skipped.
    (root / "inbox" / "retry.json").write_text(
        json.dumps(
            [
                {"question": QUESTION, "depth": "quick", "id": "one"},
                {"question": "pricing models", "depth": "quick", "id": "two"},
            ]
        )
    )
    results = run_queue(root, lambda: agent, log=lambda _m: None)
    assert sorted(r.status for r in results) == ["done", "skipped"]


def test_queue_lock_blocks_overlapping_runs(agent, tmp_path):
    root = tmp_path / "q"
    enqueue(root, ResearchRequest(question=QUESTION, depth="quick"))
    (root / ".lock").write_text("123")
    with pytest.raises(QueueLocked):
        run_queue(root, lambda: agent, log=lambda _m: None)


def test_cli_research_offline(tmp_path, capsys):
    out = tmp_path / "r"
    assert (
        main(["research", QUESTION, "--depth", "quick", "--offline", "-q", "--out", str(out)]) == 0
    )
    assert (out / "report.md").exists()
    assert "html:" in capsys.readouterr().out


def test_cli_queue_round_trip(tmp_path, capsys):
    root = str(tmp_path / "q")
    req_file = tmp_path / "reqs.json"
    req_file.write_text(json.dumps([{"question": QUESTION, "depth": "quick"}]))
    assert main(["queue", "add", "--from-file", str(req_file), "--root", root]) == 0
    assert main(["queue", "add", "pricing models", "--depth", "quick", "--root", root]) == 0
    assert main(["queue", "status", "--root", root]) == 0
    assert main(["queue", "run", "--offline", "-q", "--root", root]) == 0
    assert "done: 2" in capsys.readouterr().out


def test_cli_reports_missing_search_key(tmp_path, capsys):
    code = main(["research", "q", "--llm", "mock", "--out", str(tmp_path / "x")])
    assert code == 1
    assert "TAVILY_API_KEY" in capsys.readouterr().err
