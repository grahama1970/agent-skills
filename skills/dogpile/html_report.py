#!/usr/bin/env python3
"""Generate a self-contained HTML report for Dogpile search runs."""
from __future__ import annotations

import html
import os
import re
import tempfile
import webbrowser
from pathlib import Path
from typing import Any, Iterable, Optional


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "report"


def _escape(value: Any) -> str:
    return html.escape(str(value or ""))


def _extract_links(markdown_report: str) -> list[tuple[str, str]]:
    seen: set[str] = set()
    links: list[tuple[str, str]] = []
    for label, url in re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", markdown_report):
        if url in seen:
            continue
        seen.add(url)
        links.append((label, url))
    return links[:24]


def _split_sections(markdown_report: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    current_title = "Overview"
    current_lines: list[str] = []

    for line in markdown_report.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections.append({"title": current_title, "body": "\n".join(current_lines).strip()})
            current_title = line[3:].strip()
            current_lines = []
            continue
        if line.startswith("# "):
            continue
        current_lines.append(line)

    if current_lines:
        sections.append({"title": current_title, "body": "\n".join(current_lines).strip()})
    return [section for section in sections if section["body"]]


def _count_results(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        if "results" in value and isinstance(value["results"], list):
            return len(value["results"])
        if "items" in value and isinstance(value["items"], list):
            return len(value["items"])
        if "repos" in value and isinstance(value["repos"], list):
            return len(value["repos"])
    return 0


def _provider_cards(
    brave_res: dict[str, Any],
    github_res: dict[str, Any],
    arxiv_res: dict[str, Any],
    youtube_res: list[dict[str, Any]],
    readarr_res: list[dict[str, Any]],
    wayback_res: dict[str, Any],
    codex_src_res: str | dict[str, Any],
    perp_res: dict[str, Any],
) -> list[dict[str, str]]:
    cards = [
        {
            "label": "Brave",
            "value": str(_count_results(brave_res.get("web", {}).get("results", []) or brave_res.get("results", []))),
            "detail": brave_res.get("error", "web hits"),
            "state": "error" if brave_res.get("error") else "ok",
        },
        {
            "label": "GitHub",
            "value": str(_count_results(github_res.get("repos", []))),
            "detail": github_res.get("error", "repos found"),
            "state": "error" if github_res.get("error") else "ok",
        },
        {
            "label": "ArXiv",
            "value": str(_count_results(arxiv_res.get("items", []))),
            "detail": arxiv_res.get("error", "papers found"),
            "state": "error" if arxiv_res.get("error") else "ok",
        },
        {
            "label": "YouTube",
            "value": str(_count_results(youtube_res)),
            "detail": "videos found",
            "state": "ok",
        },
        {
            "label": "Readarr",
            "value": str(_count_results(readarr_res)),
            "detail": readarr_res[0].get("error", "books found") if readarr_res else "no results",
            "state": "error" if readarr_res and readarr_res[0].get("error") else "ok",
        },
        {
            "label": "Wayback",
            "value": "1" if wayback_res.get("available") else "0",
            "detail": wayback_res.get("error", "snapshot available" if wayback_res.get("available") else "no snapshot"),
            "state": "error" if wayback_res.get("error") else "ok",
        },
        {
            "label": "Codex",
            "value": "1",
            "detail": codex_src_res.get("error", "technical overview") if isinstance(codex_src_res, dict) else "technical overview",
            "state": "error" if isinstance(codex_src_res, dict) and codex_src_res.get("error") else "ok",
        },
        {
            "label": "Perplexity",
            "value": "1" if perp_res and not perp_res.get("skipped") else "0",
            "detail": perp_res.get("error") or perp_res.get("skipped", "answer included"),
            "state": "error" if perp_res.get("error") else "ok",
        },
    ]
    return cards


def _render_links(links: Iterable[tuple[str, str]]) -> str:
    items = []
    for label, url in links:
        items.append(
            f'<a class="source-link" href="{_escape(url)}" target="_blank" rel="noreferrer">'
            f"<span>{_escape(label)}</span><span>{_escape(url)}</span></a>"
        )
    return "\n".join(items) or '<div class="empty-state">No external links found in this run.</div>'


def _render_sections(sections: Iterable[dict[str, str]]) -> tuple[str, str]:
    nav_items: list[str] = []
    section_items: list[str] = []
    for index, section in enumerate(sections):
        section_id = f"section-{index}"
        title = _escape(section["title"])
        nav_items.append(f'<a href="#{section_id}">{title}</a>')
        section_items.append(
            f'<section class="report-section" id="{section_id}">'
            f"<header><h2>{title}</h2></header>"
            f'<pre>{_escape(section["body"])}</pre>'
            f"</section>"
        )
    return "\n".join(nav_items), "\n".join(section_items)


def _render_cards(cards: Iterable[dict[str, str]]) -> str:
    chunks = []
    for card in cards:
        state_class = "is-error" if card["state"] == "error" else "is-ok"
        chunks.append(
            f'<article class="provider-card {state_class}">'
            f'<div class="provider-label">{_escape(card["label"])}</div>'
            f'<div class="provider-value">{_escape(card["value"])}</div>'
            f'<div class="provider-detail">{_escape(card["detail"])}</div>'
            f"</article>"
        )
    return "\n".join(chunks)


def write_html_report(
    query: str,
    markdown_report: str,
    brave_res: dict[str, Any],
    github_res: dict[str, Any],
    arxiv_res: dict[str, Any],
    youtube_res: list[dict[str, Any]],
    readarr_res: list[dict[str, Any]],
    wayback_res: dict[str, Any],
    codex_src_res: str | dict[str, Any],
    perp_res: dict[str, Any],
    output_path: Optional[Path] = None,
    open_in_browser: bool = False,
) -> Path:
    """Write a styled HTML report and optionally open it in a browser."""
    links = _extract_links(markdown_report)
    sections = _split_sections(markdown_report)
    cards = _provider_cards(
        brave_res=brave_res,
        github_res=github_res,
        arxiv_res=arxiv_res,
        youtube_res=youtube_res,
        readarr_res=readarr_res,
        wayback_res=wayback_res,
        codex_src_res=codex_src_res,
        perp_res=perp_res,
    )
    nav_html, sections_html = _render_sections(sections)
    cards_html = _render_cards(cards)
    links_html = _render_links(links)

    if output_path is None:
        report_name = f"dogpile-report-{_slugify(query)[:48]}-"
        fd, temp_path = tempfile.mkstemp(prefix=report_name, suffix=".html")
        os.close(fd)
        path = Path(temp_path)
    else:
        path = output_path.expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

    html_document = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dogpile Report</title>
  <style>
    :root {{
      --bg: #0f1117;
      --panel: #171a23;
      --panel-alt: #1d212c;
      --text: #e8ecf3;
      --muted: #9ba6bb;
      --accent: #89dceb;
      --accent-2: #f4b8e4;
      --ok: #8bd5a3;
      --warn: #f4c16d;
      --error: #ee8b8b;
      --border: rgba(255, 255, 255, 0.08);
      --shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
      --mono: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
      --sans: Inter, ui-sans-serif, system-ui, sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      font-family: var(--sans);
      background:
        radial-gradient(circle at top left, rgba(137, 220, 235, 0.16), transparent 28%),
        radial-gradient(circle at top right, rgba(244, 184, 228, 0.14), transparent 24%),
        linear-gradient(180deg, #0c0e14, var(--bg));
      color: var(--text);
    }}
    a {{ color: inherit; }}
    .layout {{
      width: min(1400px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0 48px;
      display: grid;
      gap: 20px;
      grid-template-columns: 280px minmax(0, 1fr);
    }}
    .sidebar, .surface {{
      background: rgba(23, 26, 35, 0.86);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border);
      border-radius: 22px;
      box-shadow: var(--shadow);
    }}
    .sidebar {{
      position: sticky;
      top: 24px;
      align-self: start;
      padding: 20px;
    }}
    .surface {{
      padding: 24px;
      display: grid;
      gap: 20px;
    }}
    .eyebrow {{
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-size: 12px;
      margin-bottom: 10px;
    }}
    h1, h2, h3, p {{ margin: 0; }}
    h1 {{
      font-size: clamp(30px, 4vw, 48px);
      line-height: 1.02;
      max-width: 16ch;
    }}
    .hero {{
      display: grid;
      gap: 16px;
      padding: 28px;
      background: linear-gradient(135deg, rgba(137, 220, 235, 0.14), rgba(244, 184, 228, 0.08) 60%, rgba(255, 255, 255, 0.02));
      border: 1px solid var(--border);
      border-radius: 20px;
    }}
    .hero p {{ color: var(--muted); max-width: 72ch; }}
    .provider-grid {{
      display: grid;
      gap: 14px;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    }}
    .provider-card {{
      background: var(--panel-alt);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 16px;
      min-height: 120px;
    }}
    .provider-card.is-error {{ border-color: rgba(238, 139, 139, 0.55); }}
    .provider-card.is-ok {{ border-color: rgba(139, 213, 163, 0.28); }}
    .provider-label {{
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .provider-value {{
      font-size: 34px;
      font-weight: 700;
      margin-top: 10px;
    }}
    .provider-detail {{
      margin-top: 12px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }}
    .sidebar-title {{
      font-size: 12px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 12px;
    }}
    .toc, .source-list {{
      display: grid;
      gap: 8px;
    }}
    .toc a, .source-link {{
      display: block;
      text-decoration: none;
      color: var(--text);
      background: var(--panel-alt);
      border: 1px solid transparent;
      border-radius: 14px;
      padding: 12px 14px;
      transition: border-color 120ms ease, transform 120ms ease;
    }}
    .toc a:hover, .source-link:hover {{
      border-color: rgba(137, 220, 235, 0.45);
      transform: translateY(-1px);
    }}
    .source-link span {{
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .source-link span:last-child {{
      color: var(--muted);
      font-size: 12px;
      margin-top: 4px;
    }}
    .report-section {{
      border: 1px solid var(--border);
      border-radius: 20px;
      overflow: hidden;
      background: rgba(29, 33, 44, 0.72);
    }}
    .report-section header {{
      padding: 16px 18px;
      border-bottom: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.02);
    }}
    .report-section h2 {{
      font-size: 18px;
    }}
    .report-section pre {{
      margin: 0;
      padding: 18px;
      overflow-x: auto;
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.55;
      font-size: 13px;
      font-family: var(--mono);
      color: #d9e2f2;
    }}
    .empty-state {{
      color: var(--muted);
      background: var(--panel-alt);
      border: 1px dashed var(--border);
      border-radius: 14px;
      padding: 14px;
    }}
    @media (max-width: 1020px) {{
      .layout {{
        grid-template-columns: 1fr;
      }}
      .sidebar {{
        position: static;
      }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <aside class="sidebar">
      <div class="sidebar-title">Sections</div>
      <nav class="toc">{nav_html}</nav>
      <div class="sidebar-title" style="margin-top: 22px;">Sources</div>
      <div class="source-list">{links_html}</div>
    </aside>
    <main class="surface">
      <section class="hero">
        <div class="eyebrow">Dogpile HTML Report</div>
        <h1>{_escape(query)}</h1>
        <p>
          Browser view for the same Dogpile run. This keeps the full markdown payload intact while
          making sections, source links, and provider status easier to scan than the TUI output.
        </p>
      </section>
      <section class="provider-grid">{cards_html}</section>
      {sections_html}
    </main>
  </div>
</body>
</html>
"""

    path.write_text(html_document, encoding="utf-8")

    if open_in_browser:
        webbrowser.open_new_tab(path.resolve().as_uri())

    return path
