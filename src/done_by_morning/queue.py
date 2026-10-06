"""File-based overnight queue.

Layout under the queue root (default ``./queue``)::

    inbox/      submitted requests: one JSON object or a JSON list of objects per file
    done/       request files whose requests all completed
    failed/     request files with at least one failure, plus ``<file>.error.txt``
    reports/<request-id>/report.{md,html,json}  plus status.json

``run_queue`` is safe to call from cron: a lock file prevents overlapping runs, and
requests that already have a report are skipped, so a re-run only retries failures.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .agent import ResearchAgent
from .models import ResearchRequest, utcnow
from .render import write_report

STALE_LOCK_SECONDS = 12 * 3600


class QueueLocked(RuntimeError):
    pass


@dataclass
class QueueResult:
    request_id: str
    source_file: str
    status: str  # "done" | "skipped" | "failed"
    detail: str = ""


def queue_dirs(root: str | Path) -> dict[str, Path]:
    root = Path(root)
    dirs = {name: root / name for name in ("inbox", "done", "failed", "reports")}
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def enqueue(root: str | Path, request: ResearchRequest) -> Path:
    inbox = queue_dirs(root)["inbox"]
    path = inbox / f"{request.id}.json"
    path.write_text(json.dumps(request.to_dict(), indent=2), encoding="utf-8")
    return path


def import_file(root: str | Path, file: str | Path) -> list[Path]:
    """Validate a JSON file of requests and enqueue each one."""
    data = json.loads(Path(file).read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else [data]
    return [enqueue(root, ResearchRequest.from_dict(item)) for item in items]


@contextmanager
def _lock(root: Path):
    lock = root / ".lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if time.time() - lock.stat().st_mtime < STALE_LOCK_SECONDS:
            raise QueueLocked(f"Another queue run holds {lock}.") from None
        lock.unlink()
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


def _load_requests(path: Path) -> list[ResearchRequest]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else [data]
    return [ResearchRequest.from_dict(item) for item in items]


def pending(root: str | Path) -> list[Path]:
    return sorted(queue_dirs(root)["inbox"].glob("*.json"))


def run_queue(
    root: str | Path,
    agent_factory: Callable[[], ResearchAgent],
    pdf: bool = False,
    log: Callable[[str], None] = print,
) -> list[QueueResult]:
    root = Path(root)
    dirs = queue_dirs(root)
    results: list[QueueResult] = []
    with _lock(root):
        files = pending(root)
        if not files:
            log("queue: inbox is empty")
            return results
        agent = agent_factory()
        for path in files:
            errors: list[str] = []
            try:
                requests = _load_requests(path)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                errors.append(f"invalid request file: {exc}")
                results.append(QueueResult("", path.name, "failed", str(exc)))
                requests = []
            for req in requests:
                out_dir = dirs["reports"] / req.id
                if (out_dir / "report.md").exists():
                    results.append(QueueResult(req.id, path.name, "skipped", "report exists"))
                    continue
                log(f"queue: running {req.id} ({req.depth})")
                started = utcnow()
                try:
                    report = agent.run(req)
                    written = write_report(report, out_dir, pdf=pdf)
                except Exception as exc:  # one bad request must not stop the batch
                    errors.append(f"{req.id}: {exc}")
                    results.append(QueueResult(req.id, path.name, "failed", str(exc)))
                    log(f"queue: FAILED {req.id}: {exc}")
                    continue
                status = {
                    "request": req.to_dict(),
                    "started_at": started.isoformat(timespec="seconds"),
                    "finished_at": utcnow().isoformat(timespec="seconds"),
                    "files": {k: str(v.name) for k, v in written.items()},
                    "warnings": report.warnings,
                }
                (out_dir / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
                results.append(QueueResult(req.id, path.name, "done", str(out_dir)))
                log(f"queue: done {req.id} -> {out_dir}")
            target = dirs["failed" if errors else "done"] / path.name
            shutil.move(str(path), target)
            if errors:
                target.with_suffix(".error.txt").write_text("\n".join(errors) + "\n", "utf-8")
    return results
