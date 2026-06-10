#!/usr/bin/env python3
"""Build a static human-facing HTML page review report from review.json.

This script intentionally has no third-party dependencies. It fills the supplied
HTML template with escaped content and relative screenshot links.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def badge_class(value: str) -> str:
    lowered = (value or "").lower()
    if lowered in {"pass", "safe"}:
        return "pass"
    if lowered in {"degraded", "needs_changes", "safe_with_conditions"}:
        return "degraded"
    if lowered in {"fail", "not_safe"}:
        return "fail"
    return "blocked"


def row(cells: list[Any]) -> str:
    return "<tr>" + "".join(f"<td>{esc(cell)}</td>" for cell in cells) + "</tr>"


def screenshot_cards(shots: list[dict[str, Any]]) -> str:
    cards = []
    for shot in shots:
        path = esc(shot.get("path", ""))
        label = esc(shot.get("label", path))
        expected = esc(shot.get("expected", ""))
        observed = esc(shot.get("observed", ""))
        verdict = esc(shot.get("verdict", ""))
        cards.append(
            f"""<article class="interaction-card">
  <div>
    <h3>{label} <span class="badge {badge_class(verdict)}">{verdict}</span></h3>
    <p><strong>Expected:</strong> {expected}</p>
    <p><strong>Observed:</strong> {observed}</p>
  </div>
  <figure>
    <a href="{path}"><img src="{path}" alt="{label}"></a>
    <figcaption>{path}</figcaption>
  </figure>
</article>"""
        )
    return "\n".join(cards)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-json", default="review.json")
    parser.add_argument("--template", default="templates/HUMAN_REPORT.html")
    parser.add_argument("--out", default="report.html")
    args = parser.parse_args()

    data = json.loads(Path(args.review_json).read_text(encoding="utf-8"))
    template = Path(args.template).read_text(encoding="utf-8")

    research_rows = "\n".join(row([
        item.get("pattern", ""),
        item.get("benchmark_behavior", ""),
        item.get("implication", ""),
    ]) for item in data.get("research", {}).get("benchmark_findings", []))

    persona_rows = "\n".join(row([
        item.get("area", ""),
        item.get("finding", ""),
        item.get("verdict", ""),
    ]) for item in data.get("persona_evaluation", []))

    interaction_rows = "\n".join(row([
        idx + 1,
        item.get("qid", ""),
        item.get("action", ""),
        item.get("expected", ""),
        item.get("observed", ""),
        item.get("verdict", ""),
        item.get("screenshot", ""),
    ]) for idx, item in enumerate(data.get("interactions", [])))

    theater_rows = "\n".join(row([
        item.get("risk", ""),
        item.get("finding", ""),
        item.get("required_behavior", ""),
    ]) for item in data.get("dashboard_theater_audit", []))

    blocker_rows = "\n".join(row([
        item.get("finding", item if isinstance(item, str) else ""),
        item.get("severity", "") if isinstance(item, dict) else "",
        item.get("owner", "") if isinstance(item, dict) else "",
        item.get("why_blocks", "") if isinstance(item, dict) else "",
    ]) for item in data.get("blocking_findings", []))

    action_rows = "\n".join(f"<li>{esc(item)}</li>" for item in data.get("code_runner_actions", []))
    non_claims = "\n".join(f"<li>{esc(item)}</li>" for item in data.get("non_claims", []))

    replacements = {
        "{{PAGE_NAME}}": esc(data.get("page", "")),
        "{{PAGE_VERDICT}}": esc(data.get("page_verdict", "")),
        "{{PAGE_VERDICT_CLASS}}": badge_class(data.get("page_verdict", "")),
        "{{OVERALL_VERDICT}}": esc(data.get("overall_verdict", "")),
        "{{OVERALL_VERDICT_CLASS}}": badge_class(data.get("overall_verdict", "")),
        "{{PERSONA}}": esc(data.get("lead_persona", "")),
        "{{ROUND_ID}}": esc(data.get("round_id", "")),
        "{{EXECUTIVE_SUMMARY}}": esc(data.get("executive_summary", "")),
        "{{BENCHMARK_ROWS}}": research_rows,
        "{{PERSONA_ROWS}}": persona_rows,
        "{{INTERACTION_ROWS}}": interaction_rows,
        "{{SCREENSHOT_CARDS}}": screenshot_cards(data.get("evidence", {}).get("screenshots", [])),
        "{{THEATER_ROWS}}": theater_rows,
        "{{BLOCKER_ROWS}}": blocker_rows,
        "{{ACTION_ROWS}}": action_rows,
        "{{NON_CLAIMS}}": non_claims,
    }

    output = template
    for key, value in replacements.items():
        output = output.replace(key, value)

    Path(args.out).write_text(output, encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
