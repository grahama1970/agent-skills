#!/usr/bin/env python3
"""Deterministic clean-room review bundle and WebGPT loop helper."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", text.strip()).strip("-").lower() or "target"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_project_state(target: Path, dest: Path) -> dict:
    env = {**dict(**__import__("os").environ), "PROJECT_STATE_ROOT": str(target)}
    result = subprocess.run(
        [str(ROOT / "run.sh"), "report", "--json"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    if result.returncode != 0:
        return {
            "schema": "project_state.report.v1",
            "project": target.name,
            "project_root": str(target),
            "project_state_error": result.stderr[-4000:],
        }
    dest.write_text(result.stdout, encoding="utf-8")
    return json.loads(result.stdout)


def inventory(target: Path) -> str:
    files = []
    ignored = {".git", ".venv", "__pycache__", "node_modules", ".ask", ".pytest_cache", ".ruff_cache", ".mypy_cache", "build", "dist"}
    for path in sorted(p for p in target.rglob("*") if p.is_file()):
        rel = path.relative_to(target)
        if any(part in ignored for part in rel.parts):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        files.append(f"- `{rel}` ({size} bytes)")
        if len(files) >= 200:
            files.append("- ... inventory truncated at 200 files")
            break
    return "# Inventory\n\n" + "\n".join(files) + "\n"


def source_excerpts(target: Path) -> str:
    wanted_suffixes = {".py", ".md", ".sh", ".toml", ".yaml", ".yml", ".json"}
    priority_names = {"SKILL.md", "README.md", "PROJECT_KNOWLEDGE.md", "run.sh", "pyproject.toml"}
    ignored = {".git", ".venv", "__pycache__", "node_modules", ".ask", ".pytest_cache", ".ruff_cache", ".mypy_cache", "build", "dist"}
    paths = []
    for path in sorted(p for p in target.rglob("*") if p.is_file()):
        rel = path.relative_to(target)
        if any(part in ignored for part in rel.parts):
            continue
        if path.name in priority_names or path.suffix in wanted_suffixes:
            paths.append(path)
    paths.sort(key=lambda p: (0 if p.name in priority_names else 1, str(p.relative_to(target))))
    chunks = ["# Source excerpts", ""]
    for path in paths[:25]:
        rel = path.relative_to(target)
        text = path.read_text(errors="ignore")
        lines = text.splitlines()[:220]
        if len(text.splitlines()) > 220:
            lines.append("... excerpt truncated at 220 lines")
        chunks.extend([f"## `{rel}`", "", "```", "\n".join(lines), "```", ""])
    if len(paths) > 25:
        chunks.append(f"- ... source excerpts truncated at 25 files of {len(paths)} candidates")
    return "\n".join(chunks) + "\n"


def failures(report: dict) -> str:
    out = ["# Failures and gaps", ""]
    for gap in report.get("phase_6_gaps", {}).get("gaps", []):
        out.append(f"- {gap.get('severity','unknown')}: {gap.get('gap')} — {gap.get('action')}")
    for item in report.get("phase_3_doc_drift", {}).get("drift_items", [])[:50]:
        out.append(f"- doc-drift: {item.get('file')} — {item.get('issue')} — {item.get('line')}")
    for item in report.get("phase_4_best_practices", {}).get("findings", [])[:50]:
        out.append(f"- best-practice: {item.get('severity')} {item.get('file')} — {item.get('issue')}")
    if len(out) == 2:
        out.append("- No machine-readable failures found; reviewer should still assess coherence and over-engineering.")
    return "\n".join(out) + "\n"


def contradictions(target: Path) -> str:
    patterns = re.compile(r"\b(TODO|FIXME|not yet|future|planned|deprecated|removed|fail closed|WebGPT|ChatGPT)\b", re.I)
    rows = ["# Potential contradictions and stale claims", ""]
    for name in ("SKILL.md", "README.md", "PROJECT_KNOWLEDGE.md"):
        path = target / name
        if not path.exists():
            continue
        for i, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
            if patterns.search(line):
                rows.append(f"- `{name}:{i}` {line.strip()[:240]}")
                if len(rows) >= 80:
                    rows.append("- ... contradictions scan truncated")
                    return "\n".join(rows) + "\n"
    if len(rows) == 2:
        rows.append("- No obvious contradiction keywords found in SKILL/README/PROJECT_KNOWLEDGE.")
    return "\n".join(rows) + "\n"


def display_target(target: Path) -> str:
    try:
        return str(target.resolve().relative_to(REPO))
    except ValueError:
        return target.name


def prompt(target: Path, tab_id: str, conversation_url: str) -> str:
    return f"""# Clean-room redesign request

You are reviewing a project from scratch. Ignore current implementation inertia. Use the attached bundle only.

Target: `{display_target(target)}`
Existing WebGPT tab id: `{tab_id or 'unbound'}`
Conversation URL: `{conversation_url or 'unbound'}`

Return exactly one classification line:

`CLASSIFICATION: ready-to-deploy`

or

`CLASSIFICATION: not-ready`

If not ready, provide focused tickets in this exact shape:

```text
FOCUSED_TICKETS:
- title: <short actionable title>
  target: <repo path>
  observed: <current failure or overbuilt behavior>
  expected: <desired behavior>
  proof: <deterministic local proof command>
```

WebGPT is advisory only. Not-ready findings become `$ticket` items for `$project-watchdog`; local repair and closure require deterministic proof. Judge whether the clean-room direction is coherent, smaller, and deployable. Prefer deletion and simpler boundaries over patching around contradictions.
"""


def classify_response(text: str) -> str:
    m = re.search(r"^\s*CLASSIFICATION:\s*(ready-to-deploy|not-ready)\s*$", text, re.I | re.M)
    return m.group(1).lower() if m else "not-ready"


def parse_tickets(text: str) -> list[dict[str, str]]:
    tickets: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        title = re.match(r"^-\s*title:\s*(.+)$", line, re.I)
        field = re.match(r"^(target|observed|expected|proof):\s*(.+)$", line, re.I)
        if title:
            if current:
                tickets.append(current)
            current = {"title": title.group(1).strip()}
        elif field and current is not None:
            current[field.group(1).lower()] = field.group(2).strip()
    if current:
        tickets.append(current)
    if tickets:
        return tickets
    return [
        {"title": m.strip()}
        for m in re.findall(r"^\s*TICKET:\s*(.+?)\s*$", text, re.I | re.M)
    ]


LIVE_PROOF_MARKERS = (
    "sanity-live",
    "sanity-e2e",
    "live_e2e",
    "--live",
    "--apply",
    "--allow-live",
    "e2e",
    "curl ",
    "gh ",
    "run.sh",
    "screenshot",
    "cdp",
    "browser",
    "readback",
    "read-back",
    "receipt",
)


def ensure_watchdog_proof(proof: str, receipt_path: Path) -> str:
    parts = [proof]
    norm = proof.lower().replace("_", "-")
    if "agentic-eval" not in norm:
        parts.append(
            "cd skills/agentic-evals && ./run.sh run ../project-state/fixtures/agentic_eval.json "
            "--only-category agentic-evals:agent-skills:clean-room-webgpt-loop "
            "--map ../project-state/fixtures/category_map.json must report readiness READY"
        )
    joined = "; ".join(parts)
    if "readback" not in joined.lower() and "read-back" not in joined.lower():
        readback = f"python3 -c {json.dumps('import json; print(json.load(open(' + repr(str(receipt_path)) + '))[\"schema\"])')} # readback receipt"
        joined = f"{joined}; {readback}"
    return joined


def triage_error_classify(text: str, layer: str = "project-state") -> dict[str, object]:
    triage = Path(__file__).resolve().parents[2] / "triage-error" / "run.sh"
    if not triage.exists():
        return {"code": "triage_error_unavailable", "cause": text, "next_command": None, "ambiguous": True}
    result = subprocess.run(
        [str(triage), "classify", "--text", text, "--layer", layer],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    if result.returncode != 0:
        return {"code": "triage_error_classify_failed", "cause": result.stderr.strip() or text, "next_command": None, "ambiguous": True}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"code": "triage_error_invalid_json", "cause": result.stdout.strip() or text, "next_command": None, "ambiguous": True}


def ticket_preview(
    tickets: list[dict[str, str]],
    target: Path,
    tab_id: str,
    conversation_url: str,
    *,
    source_round: int,
    bundle_zip: Path,
    webgpt_response: Path | None,
    watchdog_project: str,
) -> str:
    if not tickets:
        tickets = [{"title": "Resolve clean-room not-ready finding"}]
    rows = ["# Focused ticket previews", ""]
    for ticket in tickets:
        title = ticket.get("title", "Resolve clean-room not-ready finding")
        ticket_target = ticket.get("target") or str(target)
        observed = ticket.get("observed") or "Clean-room WebGPT classified the direction as not-ready."
        expected = ticket.get("expected") or "Implement the smallest focused fix for this blocking clean-room finding."
        raw_proof = ticket.get("proof") or "cd skills/agentic-evals && ./run.sh run ../project-state/fixtures/agentic_eval.json --only-category agentic-evals:agent-skills:clean-room-webgpt-loop --map ../project-state/fixtures/category_map.json shows READY"
        proof = ensure_watchdog_proof(raw_proof, bundle_zip.parent / "manifest.json")
        triage = triage_error_classify(observed)
        workflow = (
            f"Continue in WebGPT tab {tab_id or '<tab-id>'} at {conversation_url or '<conversation-url>'}; "
            f"source_round={source_round}; bundle_zip={bundle_zip}; "
            f"webgpt_response={webgpt_response or '<webgpt-response>'}; "
            f"triage_error_code={triage.get('code')}; "
            f"watchdog_tick=skills/project-watchdog/run.sh tick --apply --project {watchdog_project} --max-tickets 1; "
            "preserve the same clean-room context and implement only this finding."
        )
        rows += [
            f"## {title}",
            "",
            f"- target: `{ticket_target}`",
            f"- observed: {observed}",
            f"- expected: {expected}",
            f"- proof: `{proof}`",
            f"- source_round: {source_round}",
            f"- controlled_tab_id: {tab_id or '<missing>'}",
            f"- conversation_url: {conversation_url or '<missing>'}",
            f"- bundle_zip: `{bundle_zip}`",
            f"- webgpt_response: `{webgpt_response or '<missing>'}`",
            f"- triage_error_code: `{triage.get('code')}`",
            f"- project_watchdog_tick: `skills/project-watchdog/run.sh tick --apply --project {watchdog_project} --max-tickets 1`",
            "",
            "```bash",
            f"skills/ticket/run.sh feature {json.dumps(title)} \\",
            f"  --target {json.dumps(ticket_target)} \\",
            f"  --limitation {json.dumps(observed)} \\",
            f"  --capability {json.dumps(expected)} \\",
            f"  --workflow {json.dumps(workflow)} \\",
            f"  --acceptance {json.dumps(expected)} \\",
            f"  --proof {json.dumps(proof)} \\",
            "  --route backend_python_or_skill_runtime \\",
            "  --lane be \\",
            "  --agent coder \\",
            "  --required-skill project-watchdog \\",
            "  --required-skill triage-error \\",
            f"  --label {json.dumps('executor:local')}",
            "```",
            "",
        ]
    return "\n".join(rows)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def write_zip(round_dir: Path, files: list[Path]) -> Path:
    zip_path = round_dir / "clean-room-bundle.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, arcname=path.name)
    return zip_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--project-state-json", type=Path)
    parser.add_argument("--webgpt-response", type=Path)
    parser.add_argument("--tab-id", default="")
    parser.add_argument("--conversation-url", default="")
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--watchdog-project", default="agent-skills")
    args = parser.parse_args(argv)

    target = args.target.resolve()
    round_dir = args.output_dir.resolve() / f"round-{args.round:02d}"
    round_dir.mkdir(parents=True, exist_ok=True)

    project_state_path = round_dir / "project_state.json"
    if args.project_state_json:
        shutil.copy2(args.project_state_json, project_state_path)
        report = read_json(project_state_path)
    else:
        report = run_project_state(target, project_state_path)
        if not project_state_path.exists():
            project_state_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    review_context = round_dir / "review_context.md"
    review_context.write_text(
        "\n\n".join([
            inventory(target),
            failures(report),
            contradictions(target),
            "# Acceptance\n\n- WebGPT returns `CLASSIFICATION: ready-to-deploy`.\n- Otherwise each not-ready blocker becomes one focused ticket preview for `$ticket`/`$project-watchdog`.\n- The same tab id/conversation URL is retained across rounds.\n- Boundary failures carry a `$triage-error` classification code.\n",
        ]),
        encoding="utf-8",
    )
    source_excerpt_path = round_dir / "source_excerpts.md"
    source_excerpt_path.write_text(source_excerpts(target), encoding="utf-8")
    prompt_path = round_dir / "prompt.md"
    prompt_path.write_text(prompt(target, args.tab_id, args.conversation_url), encoding="utf-8")
    generated = [project_state_path, review_context, source_excerpt_path, prompt_path]

    status = "needs_webgpt"
    status_reason = "bundle_created_waiting_for_webgpt"
    classification = None
    tickets: list[dict[str, str]] = []
    response_path: Path | None = None
    triage_error: dict[str, object] | None = None
    bundle_zip = round_dir / "clean-room-bundle.zip"
    if args.webgpt_response:
        response_path = round_dir / "webgpt_response.md"
        shutil.copy2(args.webgpt_response, response_path)
        generated.append(response_path)
        text = response_path.read_text(encoding="utf-8")
        classification = classify_response(text)
        if classification == "ready-to-deploy" and args.tab_id and args.conversation_url:
            status = "ready-to-deploy"
            status_reason = "webgpt_classified_ready_with_same_tab_binding"
        else:
            status = "not-ready"
            status_reason = (
                "missing_same_tab_binding"
                if classification == "ready-to-deploy"
                else "webgpt_classified_not_ready_or_malformed"
            )
        if status == "not-ready":
            triage_error = triage_error_classify(f"clean-room {status_reason}: {text[:1000]}")
            tickets = parse_tickets(text)
            preview = round_dir / "ticket_previews.md"
            preview.write_text(
                ticket_preview(
                    tickets,
                    target,
                    args.tab_id,
                    args.conversation_url,
                    source_round=args.round,
                    bundle_zip=bundle_zip,
                    webgpt_response=response_path,
                    watchdog_project=args.watchdog_project,
                ),
                encoding="utf-8",
            )
            generated.append(preview)

    manifest = {
        "schema": "clean_room.loop_receipt.v1",
        "target": str(target),
        "round": args.round,
        "status": status,
        "status_reason": status_reason,
        "classification": classification,
        "controlled_tab_id": args.tab_id,
        "conversation_url": args.conversation_url,
        "created_at": now(),
        "files": [p.name for p in generated],
        "file_sha256": {p.name: sha256(p) for p in generated},
        "ticket_count": len(tickets),
        "tickets": tickets,
        "iteration_driver": "project-watchdog",
        "project_watchdog": {
            "project": args.watchdog_project,
            "ticket_mode": "preview_only_until_ticket_apply",
            "eligible_route": "ticket_repair",
            "tick_command": f"skills/project-watchdog/run.sh tick --apply --project {args.watchdog_project} --max-tickets 1",
        },
        "triage_error": triage_error,
        "zip_path": str(bundle_zip),
    }
    manifest_path = round_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    generated.append(manifest_path)
    if response_path and tickets:
        bundle_members = [project_state_path, review_context, manifest_path, response_path, round_dir / "ticket_previews.md"]
    else:
        bundle_members = [project_state_path, review_context, source_excerpt_path, manifest_path, prompt_path]
    manifest["bundle_files"] = [p.name for p in bundle_members]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    zip_path = write_zip(round_dir, bundle_members)
    manifest["zip_sha256"] = sha256(zip_path)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(manifest, indent=2))
    return 0 if status == "ready-to-deploy" else 2


if __name__ == "__main__":
    raise SystemExit(main())
