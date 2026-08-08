"""report - persona_dream_av_bakeoff.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from .io_utils import write_text


def _fmt(v: Any) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def make_markdown_report(receipt: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Persona-Dream A/V Bake-off Report")
    lines.append("")
    lines.append(f"Overall: **{receipt.get('overall')}**")
    lines.append(f"Machine verdict: **{receipt.get('machine_verdict')}**")
    compare = receipt.get("comparison", {})
    lines.append(f"Machine winner: **{compare.get('machine_winner')}**")
    lines.append("")
    lines.append("## Lanes")
    lines.append("")
    lines.append("| Lane | Verdict | Audio sim | Final sim | Audio sec | Base sec | Final sec | Final video |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for lane, lr in receipt.get("lane_receipts", {}).items():
        dialogue = lr.get("dialogue", {})
        durations = lr.get("durations_sec", {})
        urls = lr.get("urls", {})
        lines.append(
            "| "
            + " | ".join(
                [
                    lane,
                    lr.get("machine_verdict", "n/a"),
                    _fmt(dialogue.get("audio_similarity")),
                    _fmt(dialogue.get("final_video_similarity")),
                    _fmt(durations.get("audio")),
                    _fmt(durations.get("base_video")),
                    _fmt(durations.get("lipsync_video")),
                    urls.get("lipsync_video_url", ""),
                ]
            )
            + " |"
        )

    lines.append("")
    lines.append("## Manual review")
    lines.append("")
    lines.append("Score each lane:")
    lines.append("")
    lines.append("- voice_persona_fit_1_to_5")
    lines.append("- lip_sync_quality_1_to_5")
    lines.append("- mouth_visible_entire_line")
    lines.append("- visual_lore_drift")
    lines.append("- notes")
    lines.append("")
    lines.append("## No-write assertions")
    lines.append("")
    lines.append("No memory writes, Arango upserts, or Qdrant upserts are performed by this package.")
    lines.append("")
    return "\n".join(lines)


def make_html_report(receipt: dict[str, Any]) -> str:
    rows = []
    for lane, lr in receipt.get("lane_receipts", {}).items():
        dialogue = lr.get("dialogue", {})
        durations = lr.get("durations_sec", {})
        urls = lr.get("urls", {})
        rows.append(
            "<tr>"
            f"<td>{html.escape(lane)}</td>"
            f"<td>{html.escape(str(lr.get('machine_verdict', 'n/a')))}</td>"
            f"<td>{html.escape(_fmt(dialogue.get('audio_similarity')))}</td>"
            f"<td>{html.escape(_fmt(dialogue.get('final_video_similarity')))}</td>"
            f"<td>{html.escape(_fmt(durations.get('audio')))}</td>"
            f"<td>{html.escape(_fmt(durations.get('base_video')))}</td>"
            f"<td>{html.escape(_fmt(durations.get('lipsync_video')))}</td>"
            f"<td><a href='{html.escape(urls.get('audio_url', '#'))}'>audio</a></td>"
            f"<td><a href='{html.escape(urls.get('lipsync_video_url', '#'))}'>final video</a></td>"
            "</tr>"
        )

    compare = receipt.get("comparison", {})
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Persona-Dream A/V Bake-off Report</title>
<style>
:root {{
  color-scheme: light dark;
  --bg: #f6f7fb;
  --card: #ffffff;
  --ink: #111827;
  --muted: #5b6472;
  --line: #d9dee8;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #0d1117;
    --card: #161b22;
    --ink: #e6edf3;
    --muted: #9aa4b2;
    --line: #30363d;
  }}
}}
body {{
  margin: 0;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--bg);
  color: var(--ink);
}}
main {{
  max-width: 1100px;
  margin: 32px auto;
  padding: 0 20px;
}}
.card {{
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 20px;
  margin: 16px 0;
}}
h1 {{ margin: 0 0 8px; }}
.muted {{ color: var(--muted); }}
.kpi {{
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}}
.kpi div {{
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px;
}}
table {{
  width: 100%;
  border-collapse: collapse;
  margin-top: 12px;
}}
th, td {{
  text-align: left;
  padding: 10px;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}}
code {{
  background: color-mix(in srgb, var(--muted) 12%, transparent);
  padding: 2px 5px;
  border-radius: 6px;
}}
</style>
</head>
<body>
<main>
  <section class="card">
    <h1>Persona-Dream A/V Bake-off Report</h1>
    <p class="muted">ElevenLabs vs WavTTS using one shared base video and the same source-grounded scene contract.</p>
    <div class="kpi">
      <div><strong>Overall</strong><br>{html.escape(str(receipt.get("overall")))}</div>
      <div><strong>Machine verdict</strong><br>{html.escape(str(receipt.get("machine_verdict")))}</div>
      <div><strong>Machine winner</strong><br>{html.escape(str(compare.get("machine_winner")))}</div>
    </div>
  </section>

  <section class="card">
    <h2>Lane comparison</h2>
    <table>
      <thead>
        <tr>
          <th>Lane</th><th>Verdict</th><th>Audio sim</th><th>Final sim</th>
          <th>Audio sec</th><th>Base sec</th><th>Final sec</th><th>Audio</th><th>Final video</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
  </section>

  <section class="card">
    <h2>Manual review checklist</h2>
    <p>Machine checks do not prove visual mouth realism. Review both final videos and fill these fields in <code>bakeoff_receipt.json</code> or your own review artifact:</p>
    <ul>
      <li>voice_persona_fit_1_to_5</li>
      <li>lip_sync_quality_1_to_5</li>
      <li>mouth_visible_entire_line</li>
      <li>visual_lore_drift</li>
      <li>notes</li>
    </ul>
  </section>

  <section class="card">
    <h2>No-write assertions</h2>
    <p>No memory writes, Arango upserts, or Qdrant upserts are performed by this package.</p>
  </section>
</main>
</body>
</html>
"""


def write_reports(receipt: dict[str, Any], out_dir: str | Path) -> None:
    out = Path(out_dir)
    write_text(out / "report.md", make_markdown_report(receipt))
    write_text(out / "report.html", make_html_report(receipt))
