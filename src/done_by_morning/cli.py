"""Command-line entry point: ``dbm``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .agent import ResearchAgent
from .llm import LLMError
from .models import DEPTHS, ResearchRequest, slugify
from .providers import LLM_CHOICES, SEARCH_CHOICES, build_llm, build_search
from .queue import QueueLocked, enqueue, import_file, pending, run_queue
from .render import write_report
from .search import SearchError


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _add_provider_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--llm", choices=LLM_CHOICES, help="LLM provider (env DBM_LLM_PROVIDER, default anthropic)"
    )
    p.add_argument(
        "--search",
        choices=SEARCH_CHOICES,
        help="search provider (env "
        "DBM_SEARCH_PROVIDER, default auto: Tavily or Brave by available key)",
    )
    p.add_argument(
        "--offline",
        action="store_true",
        help="use the mock LLM and mock search (no network, no API keys)",
    )
    p.add_argument("--pdf", action="store_true", help="also write report.pdf (needs WeasyPrint)")
    p.add_argument("-q", "--quiet", action="store_true", help="only print output paths")


def _agent_factory(args: argparse.Namespace):
    llm_name = "mock" if args.offline else args.llm
    search_name = "mock" if args.offline else args.search
    progress = (lambda _m: None) if args.quiet else (lambda m: _err(f"  {m}"))

    def factory() -> ResearchAgent:
        return ResearchAgent(build_llm(llm_name), build_search(search_name), progress=progress)

    return factory


def cmd_research(args: argparse.Namespace) -> int:
    request = ResearchRequest(question=args.question, depth=args.depth, context=args.context or "")
    out_dir = Path(args.out) if args.out else Path("reports") / slugify(request.question)
    agent = _agent_factory(args)()
    report = agent.run(request)
    back = (args.back_href, args.back_label) if args.back_href else None
    paths = write_report(report, out_dir, pdf=args.pdf, back_link=back)
    for w in report.warnings:
        _err(f"warning: {w}")
    for kind, path in paths.items():
        print(f"{kind}: {path}")
    return 0


def cmd_queue_add(args: argparse.Namespace) -> int:
    if args.from_file:
        for path in import_file(args.root, args.from_file):
            print(f"queued: {path}")
        return 0
    if not args.question:
        _err("Give a question or --from-file.")
        return 2
    request = ResearchRequest(
        question=args.question, depth=args.depth, email=args.email or "", context=args.context or ""
    )
    print(f"queued: {enqueue(args.root, request)}")
    return 0


def cmd_queue_run(args: argparse.Namespace) -> int:
    log = (lambda _m: None) if args.quiet else _err
    results = run_queue(args.root, _agent_factory(args), pdf=args.pdf, log=log)
    failed = [r for r in results if r.status == "failed"]
    done = [r for r in results if r.status == "done"]
    print(
        f"done: {len(done)}  skipped: {len(results) - len(done) - len(failed)}  "
        f"failed: {len(failed)}"
    )
    return 1 if failed else 0


def cmd_queue_status(args: argparse.Namespace) -> int:
    files = pending(args.root)
    print(f"{len(files)} request file(s) waiting in {Path(args.root) / 'inbox'}")
    for f in files:
        print(f"  {f.name}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dbm", description="Done By Morning: overnight research agent."
    )
    parser.add_argument("--version", action="version", version=f"dbm {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    r = sub.add_parser("research", help="research one question now")
    r.add_argument("question")
    r.add_argument("--depth", choices=list(DEPTHS), default="standard")
    r.add_argument("--context", help="background the agent should know (audience, constraints)")
    r.add_argument("--out", help="output directory (default reports/<slug>)")
    r.add_argument("--back-href", help=argparse.SUPPRESS)
    r.add_argument("--back-label", default="Back", help=argparse.SUPPRESS)
    _add_provider_args(r)
    r.set_defaults(func=cmd_research)

    q = sub.add_parser("queue", help="overnight batch queue")
    qsub = q.add_subparsers(dest="queue_command", required=True)

    qa = qsub.add_parser("add", help="add a request to the inbox")
    qa.add_argument("question", nargs="?")
    qa.add_argument("--depth", choices=list(DEPTHS), default="standard")
    qa.add_argument("--email", help="where the finished report should go (stored only)")
    qa.add_argument("--context")
    qa.add_argument("--from-file", help="JSON file with one request object or a list of them")
    qa.add_argument("--root", default="queue")
    qa.set_defaults(func=cmd_queue_add)

    qr = qsub.add_parser("run", help="process every request in the inbox")
    qr.add_argument("--root", default="queue")
    _add_provider_args(qr)
    qr.set_defaults(func=cmd_queue_run)

    qs = qsub.add_parser("status", help="list waiting requests")
    qs.add_argument("--root", default="queue")
    qs.set_defaults(func=cmd_queue_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (SearchError, LLMError, QueueLocked, ValueError, RuntimeError) as exc:
        _err(f"error: {exc}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
