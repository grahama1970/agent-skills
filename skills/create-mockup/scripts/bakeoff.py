#!/usr/bin/env python3
"""bakeoff - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

SCILLM = "http://localhost:4001"
HEADERS = {
    "Authorization": "Bearer sk-dev-proxy-123",
    "X-Caller-Skill": "create-mockup",
    "Content-Type": "application/json",
}

DEFAULT_LANES: dict[str, dict[str, str]] = {
    "claude": {"model": "text-claude", "role": "visual hierarchy, editorial tone, and restraint"},
    "openai": {"model": "gpt-5.5", "role": "implementation-realistic product workflow and interaction details"},
    "gemini": {"model": "text-gemini-oauth", "role": "alternate visual direction and modern interaction patterns"},
    "deepseek": {"model": "opencode-go/deepseek-v4-pro", "role": "edge cases, state mechanics, and failure modes"},
    "opencode-kimi": {"model": "opencode-go/kimi-k2.6", "role": "information architecture, state model, and structural critique"},
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "mockup"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def append_event(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": now(), **payload}, sort_keys=True) + "\n")


def read_text(path: Path | None) -> str:
    if not path:
        return ""
    return path.read_text(encoding="utf-8")


def load_lanes(model_csv: str, count: int | None) -> dict[str, dict[str, str]]:
    names = [name.strip() for name in model_csv.split(",") if name.strip()] if model_csv else list(DEFAULT_LANES)
    if count:
        names = names[:count]
    lanes: dict[str, dict[str, str]] = {}
    for name in names:
        if name in DEFAULT_LANES:
            lanes[name] = DEFAULT_LANES[name]
            continue
        lane = slug(name)
        lanes[lane] = {"model": name, "role": "independent product UI candidate"}
    return lanes


def extract_sections(text: str) -> tuple[str, str]:
    rationale = ""
    html_doc = ""
    rationale_match = re.search(r"BEGIN_RATIONALE\s*(.*?)\s*END_RATIONALE", text, re.S | re.I)
    html_match = re.search(r"BEGIN_HTML\s*(.*?)\s*END_HTML", text, re.S | re.I)
    if rationale_match:
        rationale = rationale_match.group(1).strip()
    if html_match:
        html_doc = html_match.group(1).strip()
    if not html_doc:
        fence = re.search(r"```html\s*(.*?)```", text, re.S | re.I)
        if fence:
            html_doc = fence.group(1).strip()
    if not html_doc:
        doc = re.search(r"<!doctype html.*?</html>", text, re.S | re.I)
        if doc:
            html_doc = doc.group(0).strip()
    if not html_doc:
        doc = re.search(r"<html.*?</html>", text, re.S | re.I)
        if doc:
            html_doc = "<!doctype html>\n" + doc.group(0).strip()
    return rationale or "No rationale section extracted.", html_doc


def candidate_score(lane_dir: Path, constraints: list[str]) -> dict[str, Any]:
    html_path = lane_dir / "index.html"
    rationale_path = lane_dir / "rationale.md"
    if not html_path.exists():
        return {"score": 0, "reasons": ["missing index.html"], "failed": True}
    text = (html_path.read_text(encoding="utf-8", errors="replace") + "\n" + rationale_path.read_text(encoding="utf-8", errors="replace") if rationale_path.exists() else html_path.read_text(encoding="utf-8", errors="replace")).lower()
    checks = {
        "complete_html": "<html" in text and "</html>" in text,
        "queue_navigation": any(term in text for term in ["queue", "table", "list", "filter"]),
        "selected_detail": any(term in text for term in ["selected", "detail", "decision"]),
        "actions": sum(term in text for term in ["approve", "reject", "rerun", "escalate", "export"]) >= 3,
        "chat_or_review_lane": any(term in text for term in ["chat", "conversation", "assistant"]),
        "non_dashboard": "dashboard" not in text or "not dashboard" in text or "not a dashboard" in text,
        "constraints": all(term.lower() in text for term in constraints[:6]),
    }
    score = sum(1 for passed in checks.values() if passed) * 10
    score += min(30, max(0, len(text) // 1200))
    if not checks["complete_html"]:
        score = min(score, 20)
    return {"score": min(score, 100), "checks": checks, "failed": not checks["complete_html"]}


def build_prompt(args: argparse.Namespace, lane: str, spec: dict[str, str]) -> str:
    brief = read_text(args.brief)
    failure = read_text(args.failure_analysis)
    refs = "\n\n".join(read_text(path) for path in args.reference_takeaways)
    constraints = ", ".join(args.constraints)
    screenshots = []
    if args.baseline_url:
        screenshots.append(f"Baseline URL: {args.baseline_url}")
    for ref in args.reference_url:
        screenshots.append(f"Reference URL: {ref}")
    for shot in args.screenshot:
        screenshots.append(f"Screenshot/reference path: {shot}")
    visual_context = "\n".join(screenshots) or "No screenshot URL/path supplied; rely on the brief."
    return f"""
You are creating one candidate in a multi-model UI mockup bakeoff.

Lane: {lane}
Model role: {spec['role']}
Persona: {args.persona or 'product reviewer'}
Constraints: {constraints or 'none supplied'}

Brief:
{brief}

Baseline failure analysis:
{failure or 'No separate failure analysis supplied.'}

Reference takeaways:
{refs or 'No separate reference takeaways supplied.'}

Visual context:
{visual_context}

Return exactly this structure:

BEGIN_RATIONALE
Design thesis:
Strengths:
Risks:
Implementation notes:
Why this should win:
END_RATIONALE

BEGIN_HTML
<!doctype html>
...
</html>
END_HTML

Hard rules:
- Static HTML/CSS in one file; a small inline script is acceptable for interactions.
- Produce a real usable product surface, not a marketing page.
- Do not expose model names, bakeoff labels, score matrices, or winner labels in the product UI.
- Do not clone any known product chrome.
- Avoid dashboard theater unless the brief explicitly asks for a dashboard.
- Include hover/focus affordances for unfamiliar terms when the surface is operational or compliance-related.
- Make the primary user decision obvious in the first viewport.
""".strip()


async def call_lane(client: httpx.AsyncClient, args: argparse.Namespace, lane: str, spec: dict[str, str]) -> dict[str, Any]:
    model = spec["model"]
    lane_dir = args.output / "candidates" / lane
    state_dir = args.output / "run-state" / lane
    lane_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    status_path = state_dir / "status.json"
    event_path = state_dir / "events.jsonl"
    partial_path = state_dir / "partial.txt"
    response_path = lane_dir / "response.md"
    rationale_path = lane_dir / "rationale.md"
    html_path = lane_dir / "index.html"
    started = time.time()
    write_json(status_path, {"lane": lane, "model": model, "state": "running", "started_at": now(), "partial_chars": 0})
    append_event(event_path, {"event": "started", "lane": lane, "model": model})
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a senior product UI designer. Return complete static HTML/CSS and concise rationale. Follow the requested output markers exactly."},
            {"role": "user", "content": build_prompt(args, lane, spec)},
        ],
        "temperature": args.temperature,
        "stream": True,
        "stream_progress_events": True,
        "stream_heartbeat_s": 5,
        "timeout": args.timeout,
    }
    content: list[str] = []
    last_write = time.time()
    sse_event: str | None = None
    try:
        async with client.stream("POST", f"{SCILLM}/v1/chat/completions", headers=HEADERS, json=payload, timeout=httpx.Timeout(connect=10, read=None, write=30, pool=30)) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                raise RuntimeError(f"HTTP {resp.status_code}: {body.decode('utf-8', 'replace')[:1200]}")
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if line.startswith("event:"):
                    sse_event = line[6:].strip()
                    append_event(event_path, {"event": "sse_event", "data": sse_event})
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    append_event(event_path, {"event": "done_signal"})
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    append_event(event_path, {"event": "non_json_data", "data": data[:180]})
                    continue
                if sse_event == "error" or "error" in chunk:
                    append_event(event_path, {"event": "sse_error_payload", "data": chunk})
                    error_payload = chunk.get("error", chunk)
                    message = error_payload.get("message") if isinstance(error_payload, dict) else None
                    raise RuntimeError(message or json.dumps(error_payload)[:1200])
                if sse_event in {"started", "heartbeat", "done"}:
                    append_event(event_path, {"event": f"sse_{sse_event}_payload", "data": chunk})
                    sse_event = None
                    continue
                sse_event = None
                choice = (chunk.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                token = delta.get("content") or choice.get("text") or ""
                if not token:
                    continue
                content.append(token)
                if time.time() - last_write > 2:
                    partial = "".join(content)
                    partial_path.write_text(partial, encoding="utf-8")
                    write_json(status_path, {"lane": lane, "model": model, "state": "running", "started_at": datetime.fromtimestamp(started, timezone.utc).isoformat(), "updated_at": now(), "partial_chars": len(partial)})
                    last_write = time.time()
        full = "".join(content)
        response_path.write_text(full, encoding="utf-8")
        rationale, html_doc = extract_sections(full)
        if not html_doc:
            raise RuntimeError("No HTML document extracted from response")
        rationale_path.write_text(rationale + "\n", encoding="utf-8")
        html_path.write_text(html_doc + "\n", encoding="utf-8")
        result = {"lane": lane, "model": model, "state": "completed", "duration_s": round(time.time() - started, 2), "response_chars": len(full), "html": str(html_path), "rationale": str(rationale_path)}
        write_json(status_path, {**result, "completed_at": now()})
        append_event(event_path, {"event": "completed", **result})
        return result
    except Exception as exc:
        partial = "".join(content)
        partial_path.write_text(partial, encoding="utf-8")
        result = {"lane": lane, "model": model, "state": "failed", "duration_s": round(time.time() - started, 2), "error": repr(exc), "partial_chars": len(partial)}
        write_json(status_path, {**result, "failed_at": now()})
        append_event(event_path, {"event": "failed", **result})
        return result


def write_board(args: argparse.Namespace, scores: dict[str, Any], winner: str | None) -> None:
    cards = []
    for lane, result in scores.items():
        html_path = Path("candidates") / lane / "index.html"
        rationale = Path(args.output / "candidates" / lane / "rationale.md")
        rationale_text = rationale.read_text(encoding="utf-8", errors="replace")[:700] if rationale.exists() else ""
        badge = "Winner" if lane == winner else ("Failed" if result.get("failed") else "Candidate")
        cards.append(f"""
        <button class="card {'winner' if lane == winner else ''}" onclick="openCandidate('{html_path.as_posix()}')" title="Open {html.escape(lane)} candidate">
          <span class="badge">{html.escape(badge)}</span>
          <h2>{html.escape(lane)}</h2>
          <strong>{result.get('score', 0)}/100</strong>
          <p>{html.escape(rationale_text)}</p>
        </button>
        """)
    matrix_rows = "\n".join(
        f"<tr><td>{html.escape(lane)}</td><td>{payload.get('score', 0)}</td><td>{html.escape(json.dumps(payload.get('checks', {})))}</td></tr>"
        for lane, payload in scores.items()
    )
    board = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mockup Bakeoff</title>
  <style>
    body {{ margin:0; font-family:Inter,system-ui,sans-serif; background:#0b0f17; color:#e5edf7; }}
    header {{ padding:18px 22px; border-bottom:1px solid #243044; display:flex; justify-content:space-between; gap:18px; align-items:center; }}
    h1 {{ margin:0; font-size:18px; }}
    main {{ padding:20px; }}
    .summary {{ border:1px solid #2f4363; background:#101827; border-radius:10px; padding:16px; margin-bottom:18px; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:14px; }}
    .card {{ text-align:left; min-height:210px; border:1px solid #243044; background:#111823; color:#e5edf7; border-radius:10px; padding:14px; cursor:pointer; }}
    .card:hover,.card:focus-visible {{ border-color:#60a5fa; outline:2px solid #60a5fa55; }}
    .winner {{ border-color:#fbbf24; box-shadow:0 0 0 1px #fbbf2444 inset; }}
    .badge {{ display:inline-flex; padding:3px 8px; border-radius:999px; background:#22304a; color:#a7c7ff; font-size:12px; font-weight:800; }}
    .winner .badge {{ background:#3a2b08; color:#fbbf24; }}
    h2 {{ margin:12px 0 8px; font-size:17px; }}
    p {{ color:#a8b3c7; line-height:1.45; }}
    iframe {{ width:100%; height:76vh; border:1px solid #243044; border-radius:10px; background:white; margin-top:18px; }}
    table {{ width:100%; border-collapse:collapse; margin-top:18px; color:#cbd5e1; }}
    td,th {{ border:1px solid #243044; padding:8px; vertical-align:top; }}
  </style>
</head>
<body>
  <header>
    <h1>Mockup Bakeoff</h1>
    <span>{'winner: ' + html.escape(winner) if winner else 'no winner selected'}</span>
  </header>
  <main>
    <section class="summary">
      <strong>{'Winner selected: ' + html.escape(winner) if winner else 'Bakeoff completed without a winner.'}</strong>
      <p>Each card opens its candidate. Scores are deterministic completeness checks; use design review before shipping.</p>
    </section>
    <section class="grid">{''.join(cards)}</section>
    <iframe id="preview" title="Candidate preview"></iframe>
    <table><thead><tr><th>Candidate</th><th>Score</th><th>Checks</th></tr></thead><tbody>{matrix_rows}</tbody></table>
  </main>
  <script>
    function openCandidate(path) {{ document.getElementById('preview').src = path; }}
    const first = document.querySelector('.winner') || document.querySelector('.card');
    if (first) first.click();
  </script>
</body>
</html>
"""
    (args.output / "index.html").write_text(board, encoding="utf-8")


async def run(args: argparse.Namespace) -> int:
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    lanes = load_lanes(args.models, args.count)
    write_json(args.output / "run-state" / "status.json", {"state": "running", "started_at": now(), "lanes": lanes})
    append_event(args.output / "run-state" / "events.jsonl", {"event": "bakeoff_started", "lanes": list(lanes)})
    async with httpx.AsyncClient() as client:
        tasks = [asyncio.create_task(call_lane(client, args, lane, spec)) for lane, spec in lanes.items()]
        results = []
        for task in asyncio.as_completed(tasks):
            result = await task
            results.append(result)
            append_event(args.output / "run-state" / "events.jsonl", {"event": "lane_finished", **result})
            write_json(args.output / "run-state" / "status.json", {"state": "running", "updated_at": now(), "results": results, "remaining": len(tasks) - len(results)})
    scores = {lane: candidate_score(args.output / "candidates" / lane, args.constraints) for lane in lanes}
    completed_scores = {lane: score for lane, score in scores.items() if not score.get("failed")}
    winner = max(completed_scores, key=lambda lane: completed_scores[lane]["score"]) if completed_scores else None
    write_json(args.output / "scores.json", scores)
    if winner:
        (args.output / "winner.md").write_text(f"# Winner\n\n{winner}\n\nScore: {scores[winner]['score']}/100\n", encoding="utf-8")
    else:
        (args.output / "winner.md").write_text("# Winner\n\nNo winner selected.\n", encoding="utf-8")
    write_board(args, scores, winner)
    final_state = "completed" if winner else "failed"
    write_json(args.output / "run-state" / "status.json", {"state": final_state, "completed_at": now(), "results": results, "scores": scores, "winner": winner})
    append_event(args.output / "run-state" / "events.jsonl", {"event": "bakeoff_finished", "state": final_state, "winner": winner})
    print(json.dumps({"state": final_state, "output": str(args.output), "board": str(args.output / "index.html"), "winner": winner}, indent=2))
    return 0 if winner else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a shared create-mockup bakeoff.")
    parser.add_argument("--brief", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models", default="claude,openai,gemini,deepseek,opencode-kimi")
    parser.add_argument("--count", type=int)
    parser.add_argument("--persona", default="")
    parser.add_argument("--constraints", default="")
    parser.add_argument("--baseline-url", default="")
    parser.add_argument("--reference-url", action="append", default=[])
    parser.add_argument("--screenshot", action="append", type=Path, default=[])
    parser.add_argument("--failure-analysis", type=Path)
    parser.add_argument("--reference-takeaways", action="append", type=Path, default=[])
    parser.add_argument("--temperature", type=float, default=0.55)
    parser.add_argument("--timeout", type=float, default=900)
    args = parser.parse_args()
    args.constraints = [item.strip() for item in args.constraints.split(",") if item.strip()]
    return args


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
