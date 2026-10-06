"""Turn a Report into Markdown, standalone HTML, JSON and (optionally) PDF files."""

from __future__ import annotations

import html
import json
import re
from dataclasses import asdict
from pathlib import Path

import markdown as md

from .models import Report

SAMPLE_NOTICE = (
    "Sample output generated from fixture data. The sources are fictional fixtures bundled "
    "with the engine and the text was assembled by the offline mock model. Nothing in this "
    "report describes real companies, prices or results."
)


def _title(report: Report) -> str:
    return f"Research report: {report.request.question}"


def _meta_rows(report: Report) -> list[tuple[str, str]]:
    return [
        ("Request ID", report.request.id),
        ("Depth", report.request.depth),
        ("Generated", report.generated_at),
        ("Language model", report.llm_provider),
        ("Search provider", report.search_provider),
        ("Sources", str(len(report.sources))),
    ]


def to_markdown(report: Report) -> str:
    lines = [f"# {_title(report)}", ""]
    if report.is_sample:
        lines += [f"> **{SAMPLE_NOTICE}**", ""]
    lines += ["| | |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in _meta_rows(report)]
    lines += ["", "## Research plan", ""]
    lines += [f"{i}. {q}" for i, q in enumerate(report.sub_questions, 1)]
    lines += ["", report.body_markdown.strip(), "", "## References", ""]
    for s in report.sources:
        lines.append(f"{s.id}. [{s.title}]({s.url})")
    if not report.sources:
        lines.append("No sources were gathered.")
    if report.warnings:
        lines += ["", "## Pipeline warnings", ""]
        lines += [f"- {w}" for w in report.warnings]
    return "\n".join(lines).rstrip() + "\n"


_CSS = """
:root{--bg:#fbfaf7;--fg:#1d2330;--muted:#5b6475;--line:#e3e0d8;--accent:#3b5bdb;--note:#fff4d6;--note-fg:#5c4400}
@media (prefers-color-scheme:dark){:root{--bg:#12151c;--fg:#e6e8ee;--muted:#9aa3b5;--line:#2a2f3b;--accent:#8ea4ff;--note:#3a3115;--note-fg:#f5dfa0}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.65 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:760px;margin:0 auto;padding:40px 16px 80px}
h1{font-size:1.9rem;line-height:1.25;margin:0 0 20px}
h2{font-size:1.35rem;margin:40px 0 12px;padding-top:12px;border-top:1px solid var(--line)}
h3{font-size:1.05rem;margin:28px 0 8px}
a{color:var(--accent)}
a.cite{text-decoration:none;font-size:.85em;vertical-align:super;line-height:0}
table{border-collapse:collapse;font-size:.9rem;margin:8px 0 16px}
td,th{border-bottom:1px solid var(--line);padding:4px 16px 4px 0;text-align:left}
td:first-child{color:var(--muted)}
.notice{background:var(--note);color:var(--note-fg);border-radius:8px;padding:12px 16px;font-weight:600}
ol.refs li{margin:6px 0;word-break:break-word}
ol.refs .url{color:var(--muted);font-size:.85rem}
.back{font-size:.9rem;margin-bottom:24px;display:inline-block}
"""


def _link_citations(body_html: str) -> str:
    return re.sub(r"\[(\d+)\]", r'<a class="cite" href="#ref-\1">[\1]</a>', body_html)


def to_html(report: Report, back_link: tuple[str, str] | None = None) -> str:
    meta = "".join(
        f"<tr><td>{html.escape(k)}</td><td>{html.escape(v)}</td></tr>"
        for k, v in _meta_rows(report)
    )
    plan = "".join(f"<li>{html.escape(q)}</li>" for q in report.sub_questions)
    body = _link_citations(md.markdown(report.body_markdown, extensions=["tables", "sane_lists"]))
    refs = (
        "".join(
            f'<li id="ref-{s.id}"><a href="{html.escape(s.url, quote=True)}" rel="noopener">'
            f'{html.escape(s.title)}</a><br><span class="url">{html.escape(s.url)}</span></li>'
            for s in report.sources
        )
        or "<li>No sources were gathered.</li>"
    )
    warnings = ""
    if report.warnings:
        items = "".join(f"<li>{html.escape(w)}</li>" for w in report.warnings)
        warnings = f"<h2>Pipeline warnings</h2><ul>{items}</ul>"
    notice = f'<p class="notice">{html.escape(SAMPLE_NOTICE)}</p>' if report.is_sample else ""
    back = ""
    if back_link:
        href, label = back_link
        back = f'<a class="back" href="{html.escape(href, quote=True)}">{html.escape(label)}</a>'
    title = html.escape(_title(report))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{_CSS}</style>
</head>
<body>
<main>
{back}
<h1>{title}</h1>
{notice}
<table>{meta}</table>
<h2>Research plan</h2>
<ol>{plan}</ol>
{body}
<h2>References</h2>
<ol class="refs">{refs}</ol>
{warnings}
</main>
</body>
</html>
"""


def to_json(report: Report) -> str:
    data = asdict(report)
    data["cited_source_ids"] = sorted(report.cited_ids)
    return json.dumps(data, indent=2)


def write_report(
    report: Report,
    out_dir: str | Path,
    pdf: bool = False,
    back_link: tuple[str, str] | None = None,
) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "markdown": out / "report.md",
        "html": out / "report.html",
        "json": out / "report.json",
    }
    paths["markdown"].write_text(to_markdown(report), encoding="utf-8")
    html_text = to_html(report, back_link=back_link)
    paths["html"].write_text(html_text, encoding="utf-8")
    paths["json"].write_text(to_json(report), encoding="utf-8")
    if pdf:
        try:
            from weasyprint import HTML  # optional dependency
        except ImportError as exc:
            raise RuntimeError(
                "PDF output needs WeasyPrint: pip install 'done-by-morning[pdf]'"
            ) from exc
        paths["pdf"] = out / "report.pdf"
        HTML(string=html_text, base_url=str(out)).write_pdf(paths["pdf"])
    return paths
