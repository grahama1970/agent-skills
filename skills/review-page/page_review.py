#!/usr/bin/env python3
"""review-page skill: build fail-closed page review packets for $ask webgpt."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import typer

app = typer.Typer(help="review-page: WebGPT-centered page review.")

SKILL_DIR = Path(__file__).resolve().parent
import os

def _sparta_root() -> Path:
    return Path(os.environ.get("SPARTA_ROOT", "/home/graham/workspace/experiments/sparta")).resolve()

REPO_ROOT = _sparta_root()
PHASE63 = REPO_ROOT / ".plan-iterate/phase-63-sparta-explorer-review-repair-and-report"
TI_MANIFESTS = PHASE63 / "test-interactions" / "manifests"
TI_CAPTURES = PHASE63 / "test-interactions" / "captures"
PAGE_CONTRACTS = PHASE63 / "page-contracts"
API_PROOFS = PHASE63 / "api-proofs"
TI_RUN = Path("/home/graham/workspace/experiments/agent-skills/skills/test-interactions/run.sh")


PERSONA_LENSES = {
    "nico-bailon": {"name": "Nico Bailon", "role": "Data quality and corpus readiness reviewer.", "questions": (
        "What would Nico need to trust monitor closure and source caveats on this page?",
        "What reconciled vs raw ops-arango state is visually hidden or under-explained?",
        "What would make calling this page pass unsafe?",
    )},
    "brandon-bailey": {"name": "Brandon Bailey", "role": "Compliance and evidence-gated workflow reviewer.", "questions": (
        "What would Brandon need to trust citations, evidence binding, and deflection behavior?",
        "What compliance risk is visually hidden or under-explained?",
        "What would make calling this page pass unsafe?",
    )},
    "rob-armstrong": {"name": "Rob Armstrong", "role": "Formal relationship and posture traceability reviewer.", "questions": (
        "What would Rob need to trust formal claims and graph semantics on this page?",
        "What false certainty or threshold overclaim is visible or hidden?",
        "What would make calling this page pass unsafe?",
    )},
    "margaret-chen": {"name": "Margaret Chen", "role": "Operator workflow and navigation usability reviewer.", "questions": (
        "What would Margaret need to trust navigation, orientation, and degraded-state handling?",
        "What operator burden or hidden failure state remains?",
        "What would make calling this page pass unsafe?",
    )},
}

@dataclass(frozen=True)
class PageConfig:
    page_id: str
    title: str
    persona_id: str
    route: str
    tab_qid: str
    page_purpose_qid: str
    manifest: str
    contract_markdown: str | None = None
    default_capture_dir: str | None = None
    api_proof_json: str | None = None
    api_live_path: str | None = None

PAGES = {
    "coverage": PageConfig("coverage", "Coverage + embedded monitor-status", "nico-bailon",
        "http://127.0.0.1:3002/#sparta-explorer", "sparta:button:tab-coverage", "sparta:page-purpose:coverage",
        "coverage-webgpt-page-review.json", "coverage-monitor.md", "coverage-webgpt-canary",
        "coverage-health-current.json", "/api/sparta/coverage-health"),
    "chat": PageConfig("chat", "Sparta Chat + Evidence workspace", "brandon-bailey",
        "http://127.0.0.1:3002/#sparta-explorer", "sparta:button:tab-chat", "sparta:page-purpose:chat",
        "chat-gate1.json", "sparta-chat.md", "chat-gate1", "chat-evidence-run-current.json", None),
    "qras": PageConfig("qras", "QRAs", "brandon-bailey",
        "http://127.0.0.1:3002/#sparta-explorer", "sparta:button:tab-qras", "sparta:page-purpose:qras",
        "", "evidence-workspace.md"),
    "controls": PageConfig("controls", "Controls", "brandon-bailey",
        "http://127.0.0.1:3002/#sparta-explorer", "sparta:button:tab-controls", "sparta:page-purpose:controls",
        "", "contract-matrix.md"),
    "sources": PageConfig("sources", "Sources", "nico-bailon",
        "http://127.0.0.1:3002/#sparta-explorer", "sparta:button:tab-sources", "sparta:page-purpose:sources",
        "corpus-provenance-p1.json", "corpus-provenance-pages.md", "corpus-provenance-p1"),
    "urls": PageConfig("urls", "URLs", "nico-bailon",
        "http://127.0.0.1:3002/#sparta-explorer", "sparta:button:tab-urls", "sparta:page-purpose:urls",
        "corpus-provenance-p1.json", "corpus-provenance-pages.md", "corpus-provenance-p1"),
    "threat-matrix": PageConfig("threat-matrix", "Threat Matrix", "rob-armstrong",
        "http://127.0.0.1:3002/#sparta-explorer", "sparta:button:tab-threat-matrix", "sparta:page-purpose:threat-matrix",
        "risk-posture-supply-p1.json", "risk-matrix-posture-supply-chain.md", "risk-posture-supply-p1"),
    "posture": PageConfig("posture", "Posture", "rob-armstrong",
        "http://127.0.0.1:3002/#sparta-explorer", "sparta:button:tab-posture", "sparta:page-purpose:posture",
        "risk-posture-supply-p1.json", "risk-matrix-posture-supply-chain.md", "risk-posture-supply-p1"),
    "supply-chain": PageConfig("supply-chain", "Supply Chain", "margaret-chen",
        "http://127.0.0.1:3002/#sparta-explorer", "sparta:button:tab-supply-chain", "sparta:page-purpose:supply-chain",
        "risk-posture-supply-p1.json", "risk-matrix-posture-supply-chain.md", "risk-posture-supply-p1"),
    "explorer-nav": PageConfig("explorer-nav", "Explorer tab shell / navigation", "margaret-chen",
        "http://127.0.0.1:3002/#sparta-explorer", "sparta:button:tab-coverage", "",
        "explorer-tabs-p0.json", None, "explorer-tabs-p0"),
}
REVIEW_ORDER = [
    "coverage", "chat", "qras", "controls", "sources", "urls",
    "threat-matrix", "posture", "supply-chain", "explorer-nav",
]
QID_RE = re.compile(r"\[data-qid='([^']+)'\]")

@dataclass
class PreflightFinding:
    grade: str
    check: str
    message: str

@dataclass
class GateResult:
    verdict: str
    reason: str
    findings: list[PreflightFinding] = field(default_factory=list)
    next_iteration_plan: list[str] = field(default_factory=list)

def _page(page_id: str) -> PageConfig:
    key = page_id.strip().lower()
    if key not in PAGES:
        typer.echo(f"Unknown page {page_id!r}. Known: {', '.join(REVIEW_ORDER)}", err=True)
        raise typer.Exit(2)
    return PAGES[key]

def _resolve_paths(page, ti_results=None, out_dir=None, capture_dir=None):
    out = out_dir or (PHASE63 / "webgpt-page-reviews" / page.page_id)
    out.mkdir(parents=True, exist_ok=True)
    if ti_results:
        results = ti_results
    elif capture_dir:
        results = capture_dir / "results.json"
    elif page.default_capture_dir:
        candidates = sorted((p / "results.json" for p in TI_CAPTURES.glob(f"{page.default_capture_dir}*") if p.is_dir()),
            key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            raise typer.BadParameter(f"No results.json under captures matching {page.default_capture_dir}*")
        results = candidates[0]
    else:
        raise typer.BadParameter("Provide --ti-results or --capture-dir")
    return out, results

def _load_results(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def _qids_from_interaction(row):
    found = []
    for assertion in row.get("assertions") or []:
        found.extend(QID_RE.findall(str(assertion.get("check") or "")))
    return list(dict.fromkeys(found))

def _cots_note(row):
    parts = []
    for assertion in row.get("assertions") or []:
        if assertion.get("status") != "PASS":
            parts.append(f"{assertion.get('check')}: {assertion.get('message')}")
        if str(assertion.get("check", "")).startswith("assert_min_size"):
            parts.append("touch target check")
    return "; ".join(parts) if parts else "none"

def _screenshot_label(row, index, page_id):
    desc = (row.get("description") or row.get("element") or "").lower()
    action = (row.get("action") or "").lower()
    explicit = row.get("label")
    if explicit:
        return f"{explicit}.png" if not str(explicit).endswith(".png") else str(explicit)
    if action == "screenshot" or "screenshot" in desc:
        if "closure" in desc or "monitor" in desc:
            return "coverage-monitor-closure-panel.png" if page_id == "coverage" else f"crop-monitor-closure-{index:02d}.png"
        if "purpose" in desc:
            return "coverage-page-purpose-strip.png" if page_id == "coverage" else f"crop-page-purpose-{index:02d}.png"
        if "refresh" in desc or "after-refresh" in desc:
            return "coverage-after-refresh.png" if page_id == "coverage" else f"workflow-after-refresh-{index:02d}.png"
        if "full" in desc:
            return "coverage-full-page.png" if page_id == "coverage" else f"full-page-{index:02d}.png"
        return f"evidence-state-{index:02d}.png"
    if index == 1 or "open" in desc:
        return "coverage-full-page.png" if page_id == "coverage" else f"full-page-{index:02d}.png"
    return f"crop-{index:02d}.png"

def _build_ti_table(results, page_id):
    lines = ["## Deterministic test-interactions summary", "",
        "| # | qid | Element / state | Action | Expected result | Actual result | Verdict | COTS / caveat | Screenshot label |",
        "|---:|---|---|---|---|---|---|---|---|"]
    for idx, row in enumerate(results.get("interactions") or [], start=1):
        qids = _qids_from_interaction(row)
        qid = qids[0] if qids else row.get("element", "")
        label = _screenshot_label(row, idx, page_id) if row.get("screenshot") else ""
        lines.append(f"| {idx} | `{qid}` | {row.get('element', '')} | {row.get('action', '')} | {row.get('description') or row.get('element', '')} | {row.get('status', '')} | {row.get('status', '')} | {_cots_note(row)} | `{label}` |")
    lines += ["", f"Totals: passed={results.get('passed', 0)} failed={results.get('failed', 0)} warned={results.get('warned', 0)} total={results.get('total', 0)}", ""]
    return "\n".join(lines)


def _qid_compliance_section(results) -> str:
    rows = [r for r in (results.get("interactions") or []) if r.get("action") == "qid_compliance"]
    if not rows:
        return "## QID compliance scan\n\nNo qid_compliance rows in TI results (manifest may have qid_compliance disabled).\n"
    lines = ["## QID compliance scan", "",
        "| qid | check | status | message |",
        "|---|---|---|---|"]
    fail = 0
    for row in rows:
        status = row.get("status", "")
        if status == "FAIL":
            fail += 1
        lines.append(f"| `{row.get('element', '')}` | {row.get('description') or row.get('element', '')} | {status} | {row.get('message', '')} |")
    lines += ["", f"Summary: total={len(rows)} failed={fail}", ""]
    return "\n".join(lines)


def _pipeline_contract_section() -> str:
    return """## Review pipeline contract (authoritative)

1. **test-interactions run** — deterministic gate; FAIL cannot be upgraded by any reviewer.
2. **review-page package** — REVIEW_PACKET.md, contact-sheet.png, review-bundle.zip, qid_compliance summary.
3. **Optional oc-kimi VLM pre-review** — non-authoritative; run `review-page prepare-vlm` then `$ask oc-kimi` with contact sheet. Replaces deprecated `test-interactions review --persona` for visual commentary.
4. **$ask webgpt** — product/policy tech-lead adjudication; one page per call.

Do not use `test-interactions review --persona` as an authoritative gate.
"""


def build_contact_sheet_png(out_dir: Path, labeled_shots: list[tuple[str, Path]], page_id: str) -> Path | None:
    """Compose a labeled PNG grid index for WebGPT attach limits."""
    if not labeled_shots:
        return None
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        typer.echo("Pillow not installed; skipping contact-sheet.png", err=True)
        return None

    thumb_w, thumb_h, pad, label_h = 480, 270, 16, 28
    cols = 2 if len(labeled_shots) <= 4 else 3
    rows_n = (len(labeled_shots) + cols - 1) // cols
    sheet_w = cols * (thumb_w + pad) + pad
    sheet_h = rows_n * (thumb_h + label_h + pad) + pad + 36
    sheet = Image.new("RGB", (sheet_w, sheet_h), color=(18, 22, 28))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
        title_font = font
    draw.text((pad, pad // 2), f"{page_id} screenshot contact sheet", fill=(220, 230, 240), font=title_font)
    y0 = 36
    for idx, (label, src) in enumerate(labeled_shots):
        if not src.exists():
            continue
        col = idx % cols
        row_i = idx // cols
        x = pad + col * (thumb_w + pad)
        y = y0 + row_i * (thumb_h + label_h + pad)
        try:
            img = Image.open(src).convert("RGB")
            img.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            ox = x + (thumb_w - img.width) // 2
            oy = y + (thumb_h - img.height) // 2
            sheet.paste(img, (ox, oy))
        except OSError:
            draw.rectangle([x, y, x + thumb_w, y + thumb_h], outline=(200, 80, 80), width=2)
        draw.text((x, y + thumb_h + 4), label, fill=(180, 200, 220), font=font)
    out = out_dir / "contact-sheet.png"
    sheet.save(out, format="PNG")
    return out

def _screenshot_inventory(results, page_id):
    rows = ["## Screenshot inventory", "", "| Label | Role | Present |", "|---|---|---|"]
    labeled = []
    seen = set()
    for idx, row in enumerate(results.get("interactions") or [], start=1):
        shot = row.get("screenshot")
        if not shot:
            continue
        path = Path(str(shot))
        label = _screenshot_label(row, idx, page_id)
        if label in seen:
            label = f"{Path(label).stem}-{idx}{Path(label).suffix or '.png'}"
        seen.add(label)
        role = "full-page" if "full-page" in label else "crop/evidence"
        if "after-refresh" in label:
            role = "workflow-primary"
        if "closure" in label or "purpose" in label:
            role = "evidence-state"
        rows.append(f"| `{label}` | {role} | yes |")
        labeled.append((label, path))
    rows.append("")
    return "\n".join(rows), labeled

def _zip_attach_section(page_id, labeled_shots):
    selected = _select_zip_shots(page_id, labeled_shots)
    lines = ["## WebGPT attach set (zip, max 4 images)", "", "| Label | In zip |", "|---|---|"]
    selected_labels = {label for label, _ in selected}
    for label, _ in labeled_shots:
        lines.append(f"| `{label}` | {'yes' if label in selected_labels else 'no (local TI only)'} |")
    lines.append("")
    return "\n".join(lines), selected

def _json_excerpt(data, max_chars=6000):
    text = json.dumps(data, indent=2, ensure_ascii=True)
    return text if len(text) <= max_chars else text[: max_chars - 80] + "\n... (truncated) ...\n"

def _load_state_json(page):
    if page.api_proof_json:
        proof = API_PROOFS / page.api_proof_json
        if proof.exists():
            return {"source": proof.name, "snapshot": json.loads(proof.read_text(encoding="utf-8"))}
    if page.api_live_path:
        try:
            resp = httpx.get(f"http://127.0.0.1:3002{page.api_live_path}", params={"force": "1", "wait": "1"}, timeout=45.0)
            resp.raise_for_status()
            return {"source": "live_api", "snapshot": resp.json()}
        except Exception as exc:
            return {"source": "live_api", "error": str(exc)}
    return {"source": "none", "note": "no api proof configured"}

def _summarize_coverage_state(state):
    snap = state.get("snapshot") if isinstance(state.get("snapshot"), dict) else state
    mc = snap.get("monitorClosure") or {}
    raw = mc.get("raw_ops_arango") or {}
    return {"generated_at": snap.get("generated_at") or mc.get("generated_at"), "stale": snap.get("stale"),
        "monitor_closure_status": mc.get("status"), "monitor_closure_passed": mc.get("passed"), "monitor_closure_total": mc.get("total"),
        "data_integrity_reconciled": mc.get("data_integrity_reconciled"),
        "raw_ops_arango_summary": {"passed": raw.get("passed"), "warnings": raw.get("warnings"), "failed": raw.get("failed")},
        "artifact_id": mc.get("artifact_id")}

def _evidence_source_summary(page, state):
    lines = ["## Evidence-source summary", "", "| Claim | Source | Status |", "|---|---|---|"]
    if page.page_id == "coverage":
        summary = _summarize_coverage_state(state)
        lines += [f"| Monitor closure rollup | {state.get('source', 'missing')} | {summary.get('monitor_closure_status', 'missing')} |",
            f"| Raw vs reconciled caveat | monitorClosure.raw_ops_arango | warnings={summary.get('raw_ops_arango_summary', {}).get('warnings')} failed={summary.get('raw_ops_arango_summary', {}).get('failed')} |",
            "| Page-purpose strip | test-interactions wait on page-purpose qid | see TI table |",
            "| Visual proof | screenshot inventory | required |"]
    else:
        lines += [f"| Page contract | {page.contract_markdown or 'missing'} | configured |",
            "| Deterministic TI | test-interactions results | see TI table |"]
    lines.append("")
    return "\n".join(lines)

def _persona_section(persona_id):
    lens = PERSONA_LENSES[persona_id]
    questions = "\n".join(f"{i}. {q}" for i, q in enumerate(lens["questions"], start=1))
    return f"## Persona lens: {lens['name']}\n\nRole:\n- {lens['role']}\n\nMust judge:\n- Layout hierarchy\n- Workflow fit\n- Evidence clarity\n- Failure/degraded state visibility\n- Overclaim/dashboard-theater risk\n\nPersona-specific questions:\n{questions}\n"

def build_review_md(page, results, ti_results_name, round_label="1", contact_sheet_name: str | None = None):
    state = _load_state_json(page)
    contract_excerpt = _summarize_coverage_state(state) if page.page_id == "coverage" else state
    ti_table = _build_ti_table(results, page.page_id)
    qid_md = _qid_compliance_section(results)
    inventory_md, labeled_all = _screenshot_inventory(results, page.page_id)
    zip_attach_md, _ = _zip_attach_section(page.page_id, labeled_all)
    contract_path = PAGE_CONTRACTS / page.contract_markdown if page.contract_markdown else None
    parts = [f"# REVIEW_REQUEST.md\n",
        f"- **Page**: {page.title}\n- **Page id**: `{page.page_id}`\n- **Lead persona**: {PERSONA_LENSES[page.persona_id]['name']}\n- **Review round**: {round_label}\n- **Requested verdict enum**: `pass | degraded | fail | insufficient_evidence`\n- **TI artifact**: `{ti_results_name}`\n",
        "## Page identity\n", f"- Route/hash: `{page.route}`\n- Tab qid: `{page.tab_qid}`\n- Page-purpose qid: `{page.page_purpose_qid or '(shell/navigation)'}`\n",
        "## Review focus\n", "Adjudicate this page only. Return VERDICT, PAGE_VERDICT, NEXT_STEP, CODE_RUNNER_ACTIONS (max 3), CLARIFYING_QUESTIONS (max 3). Do not propose code patches.\n",
        ti_table, qid_md, inventory_md,
        ("## Contact sheet\n\n- PNG index: `" + contact_sheet_name + "` (labeled grid for WebGPT attach)\n\n" if contact_sheet_name else ""),
        zip_attach_md, _pipeline_contract_section(), "## Contract/state JSON (inlined excerpt)\n\n```json\n", _json_excerpt(contract_excerpt), "\n```\n\n",
        _evidence_source_summary(page, state),
        "## Known caveats\n\n- Packet uses labeled API snapshot; live API may differ.\n- WebGPT cannot override deterministic TI FAIL to PASS.\n- Prior plan-iterate acceptance is not product readiness.\n",
        _persona_section(page.persona_id)]
    if contract_path and contract_path.exists():
        parts += ["## Code / contract context excerpt\n\n```markdown\n", "\n".join(contract_path.read_text(encoding="utf-8").splitlines()[:40]), "\n```\n"]
    parts += ["## Non-claims\n\n- Does not prove backend correctness beyond inlined snapshot.\n- Does not replace full regression.\n- Text-only review cannot prove pixels without attached screenshots.\n"]
    return "\n".join(parts)

def preflight(page, results, labeled_shots):
    findings = []
    interactions = results.get("interactions") or []
    if not interactions:
        findings.append(PreflightFinding("FAIL", "ti_results", "No interactions in results.json"))
    if int(results.get("failed") or 0):
        findings.append(PreflightFinding("FAIL", "ti_pass", f"Deterministic failures: {results.get('failed')}"))
    if not labeled_shots:
        findings.append(PreflightFinding("FAIL", "screenshots", "No screenshots in TI results"))
    labels = {label for label, _ in labeled_shots}
    if page.page_id == "coverage":
        missing = sorted({"coverage-full-page.png", "coverage-page-purpose-strip.png", "coverage-monitor-closure-panel.png"} - labels)
        if missing:
            findings.append(PreflightFinding("FAIL", "screenshot_labels", f"Missing required Coverage labels: {', '.join(missing)}"))
    state = _load_state_json(page)
    if state.get("error"):
        findings.append(PreflightFinding("WARN", "api_state", f"Live API unavailable: {state['error']}"))
    fail_count = sum(1 for f in findings if f.grade == "FAIL")
    warn_count = sum(1 for f in findings if f.grade == "WARN")
    if fail_count:
        return GateResult("INSUFFICIENT_EVIDENCE", "preflight_failed", findings, [f"{f.check}: {f.message}" for f in findings if f.grade == "FAIL"])
    if warn_count:
        return GateResult("NEEDS_CHANGES", "preflight_warnings", findings, [f"{f.check}: {f.message}" for f in findings if f.grade == "WARN"])
    return GateResult("PASS", "preflight_ready_for_webgpt", findings, ["Hand REVIEW_PACKET.md or review-bundle.zip to $ask webgpt"])

def write_gate(out_dir, page, gate, ti_results):
    payload = {"schema": "review_page.gate.v1", "page": page.page_id, "title": page.title, "verdict": gate.verdict, "reason": gate.reason,
        "findings": [{"grade": f.grade, "check": f.check, "message": f.message} for f in gate.findings],
        "next_iteration_plan": gate.next_iteration_plan, "evidence": {"test_interactions": ti_results.name}, "ask_blocked": gate.verdict != "PASS"}
    path = out_dir / "review_page.gate.v1.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path

def write_summary(out_dir, page, gate, ti_results, review_md):
    payload = {"schema": "sparta.explorer.webgpt_page_review.v1", "page": page.page_id,
        "page_verdict": "insufficient_evidence" if gate.verdict != "PASS" else "pending_webgpt",
        "overall_verdict": gate.verdict, "evidence": {"test_interactions": str(ti_results), "review_packet": str(review_md), "gate": str(out_dir / "review_page.gate.v1.json")},
        "code_runner_actions": gate.next_iteration_plan[:3], "human_required": []}
    path = out_dir / "page_review_summary.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path

def _select_zip_shots(page_id, labeled_shots, max_images=4, contact_sheet: Path | None = None):
    if not labeled_shots and not contact_sheet:
        return []
    picked: list[tuple[str, Path]] = []
    if contact_sheet and contact_sheet.exists():
        picked.append(("contact-sheet.png", contact_sheet))
        max_images = max(1, max_images - 1)
    if page_id == "coverage":
        priority = [
            "coverage-full-page.png",
            "coverage-page-purpose-strip.png",
            "coverage-monitor-closure-panel.png",
            "coverage-after-refresh.png",
        ]
        by_label = {label: src for label, src in labeled_shots}
        for label in priority:
            if label in by_label and len(picked) < max_images + (1 if contact_sheet else 0):
                item = (label, by_label[label])
                if item not in picked:
                    picked.append(item)
        if len(picked) < max_images + (1 if contact_sheet and contact_sheet.exists() else 0):
            for label, src in labeled_shots:
                if (label, src) not in picked:
                    picked.append((label, src))
                if len(picked) >= max_images + (1 if contact_sheet and contact_sheet.exists() else 0):
                    break
        cap = max_images + (1 if contact_sheet and contact_sheet.exists() else 0)
        return picked[:cap]
    extra = labeled_shots[:max_images]
    if contact_sheet and contact_sheet.exists():
        return [("contact-sheet.png", contact_sheet)] + extra[: max(0, max_images - 1)]
    return extra[:max_images]

def build_zip(out_dir, review_md, labeled_shots, page_id="", contact_sheet: Path | None = None):
    zip_path = out_dir / "review-bundle.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(review_md, arcname="REVIEW_PACKET.md")
        for label, src in _select_zip_shots(page_id, labeled_shots, contact_sheet=contact_sheet):
            if src.exists():
                zf.write(src, arcname=label)
    return zip_path


def _finalize_review_outputs(page, results, results_path, out, round_label, skip_zip=False):
    _, labeled = _screenshot_inventory(results, page.page_id)
    contact_sheet = build_contact_sheet_png(out, labeled, page.page_id)
    cs_name = contact_sheet.name if contact_sheet else None
    review_md_path = out / "REVIEW_PACKET.md"
    review_md_path.write_text(build_review_md(page, results, results_path.name, round_label, cs_name), encoding="utf-8")
    shutil.copy2(results_path, out / "test-interactions-results.json")
    gate = preflight(page, results, labeled)
    write_gate(out, page, gate, results_path)
    write_summary(out, page, gate, results_path, review_md_path)
    zip_path = None
    if not skip_zip and labeled:
        zip_path = build_zip(out, review_md_path, labeled, page.page_id, contact_sheet=contact_sheet)
    return review_md_path, gate, labeled, contact_sheet, zip_path

def run_ti(page, capture_dir):
    manifest = TI_MANIFESTS / page.manifest
    if not manifest.exists():
        raise typer.BadParameter(f"Manifest not found: {manifest}")
    capture_dir.mkdir(parents=True, exist_ok=True)
    cmd = [str(TI_RUN), "run", "--manifest", str(manifest), "--output-dir", str(capture_dir)]
    typer.echo(f"Running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if proc.returncode != 0:
        raise typer.Exit(proc.returncode)
    return capture_dir / "results.json"



def _package_payload(out_dir: Path, page, gate_path: Path, review_md: Path, zip_path: Path | None) -> dict:
    gate = json.loads(gate_path.read_text(encoding="utf-8")) if gate_path.exists() else {}
    attach = str(zip_path) if zip_path and zip_path.exists() else str(review_md)
    return {
        "schema": "review_page.package.v1",
        "page": page.page_id,
        "title": page.title,
        "persona_id": page.persona_id,
        "out_dir": str(out_dir),
        "review_packet": str(review_md),
        "review_bundle_zip": str(zip_path) if zip_path and zip_path.exists() else "",
        "gate": gate,
        "ask_blocked": bool(gate.get("ask_blocked")),
        "contact_sheet_png": str(out_dir / "contact-sheet.png") if (out_dir / "contact-sheet.png").exists() else "",
        "vlm_pre_review": {
            "authoritative": False,
            "deprecated_authoritative_path": "test-interactions review --persona",
            "recommended": "review-page prepare-vlm then $ask oc-kimi --oracle-image contact-sheet.png",
        },
        "webgpt_attach": attach,
        "ask_prompt_hint": (
            "Adjudicate the attached SPARTA Explorer page review packet. "
            "Return VERDICT, PAGE_VERDICT, NEXT_STEP, CODE_RUNNER_ACTIONS (max 3), "
            "CLARIFYING_QUESTIONS (max 3). Do not implement fixes."
        ),
    }


@app.command("package")
def package_cmd(
    page_id: str = typer.Option(..., "--page"),
    ti_results: Path | None = None,
    capture_dir: Path | None = None,
    out_dir: Path | None = None,
    round_label: str = "1",
    skip_zip: bool = False,
):
    """Emit JSON manifest for $ask webgpt (packet paths + gate state)."""
    page = _page(page_id)
    out, results_path = _resolve_paths(page, ti_results, out_dir, capture_dir)
    results = _load_results(results_path)
    _, labeled = _screenshot_inventory(results, page.page_id)
    review_md_path = out / "REVIEW_PACKET.md"
    if not review_md_path.exists():
        review_md_path, gate, labeled, _, zip_path = _finalize_review_outputs(
            page, results, results_path, out, round_label, skip_zip=skip_zip)
    else:
        gate_path = out / "review_page.gate.v1.json"
        gate = json.loads(gate_path.read_text(encoding="utf-8")) if gate_path.exists() else preflight(page, results, labeled)
        zip_path = out / "review-bundle.zip"
        if not zip_path.exists() and labeled and not skip_zip:
            zip_path = build_zip(out, review_md_path, labeled, page.page_id)
        elif not zip_path.exists():
            zip_path = None
    gate_path = out / "review_page.gate.v1.json"
    payload = _package_payload(out, page, gate_path, review_md_path, zip_path if zip_path and Path(zip_path).exists() else None)
    typer.echo(json.dumps(payload, indent=2))
    raise typer.Exit(0 if not payload.get("ask_blocked") else 2)





def _slug(s: str, max_len: int = 48) -> str:
    out = re.sub(r"[^a-zA-Z0-9]+", "-", (s or "step").strip()).strip("-").lower()
    return (out or "step")[:max_len]


def _interaction_id(row: dict, ti_index: int, page_id: str) -> str:
    surface = _slug(str(row.get("surface") or page_id))
    element = _slug(str(row.get("element") or "element"))
    action = _slug(str(row.get("action") or "act"))
    return f"{surface}-{ti_index:04d}-{element}-{action}"


def _expected_result(row: dict) -> str:
    return str(row.get("description") or row.get("element") or "expected state visible")


def _actual_result(row: dict) -> str:
    parts = [str(row.get("status") or "")]
    if row.get("evidence"):
        parts.append(str(row.get("evidence")))
    if row.get("message"):
        parts.append(str(row.get("message")))
    return " — ".join(p for p in parts if p)


def _build_step_brief(
    page: PageConfig,
    row: dict,
    *,
    step_index: int,
    total_steps: int,
    ti_index: int,
    interaction_id: str,
) -> str:
    qids = _qids_from_interaction(row)
    qid = qids[0] if qids else str(row.get("element") or "")
    assertions = []
    for assertion in row.get("assertions") or []:
        assertions.append(
            f"- {assertion.get('check', 'check')}: {assertion.get('status', '')} — {assertion.get('message', '')}"
        )
    assertion_block = "\n".join(assertions) if assertions else "- none recorded"
    return (
        f"# SPARTA Explorer step review ({page.page_id})\n\n"
        f"Step {step_index} of {total_steps} in the per-interaction WebGPT loop.\n\n"
        f"| Field | Value |\n|---|---|\n"
        f"| interaction_id | `{interaction_id}` |\n"
        f"| ti_row | {ti_index} |\n"
        f"| surface | {row.get('surface', '')} |\n"
        f"| element | {row.get('element', '')} |\n"
        f"| action | {row.get('action', '')} |\n"
        f"| qid | `{qid}` |\n"
        f"| expected_result | {_expected_result(row)} |\n"
        f"| ti_status | {row.get('status', '')} |\n"
        f"| ti_actual | {_actual_result(row)} |\n"
        f"| cots_caveat | {_cots_note(row)} |\n\n"
        f"## Assertions\n\n{assertion_block}\n\n"
        "Judge ONLY this step from the attached screenshot plus the table above.\n"
        "Do not override a TI FAIL to pass without citing what the screenshot shows.\n"
    )



def prepare_webgpt_steps(
    page: PageConfig,
    results: dict,
    out_dir: Path,
    *,
    require_screenshot: bool = True,
) -> dict:
    """Build one zip per TI interaction (brief + screenshot) for WebGPT step loop."""
    steps_dir = out_dir / "webgpt-steps"
    steps_dir.mkdir(parents=True, exist_ok=True)
    candidates = []
    for ti_index, row in enumerate(results.get("interactions") or [], start=1):
        if row.get("action") == "qid_compliance":
            continue
        shot = row.get("screenshot")
        if require_screenshot and (not shot or not Path(str(shot)).exists()):
            continue
        candidates.append((ti_index, row))

    steps: list[dict] = []
    total = len(candidates)
    for step_index, (ti_index, row) in enumerate(candidates, start=1):
        interaction_id = _interaction_id(row, ti_index, page.page_id)
        brief_text = _build_step_brief(
            page,
            row,
            step_index=step_index,
            total_steps=total,
            ti_index=ti_index,
            interaction_id=interaction_id,
        )
        brief_path = steps_dir / f"step-{step_index:03d}-brief.md"
        brief_path.write_text(brief_text, encoding="utf-8")
        zip_path = steps_dir / f"step-{step_index:03d}.zip"
        png_name = f"step-{step_index:03d}.png"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("STEP_BRIEF.md", brief_text)
            shot = Path(str(row.get("screenshot")))
            if shot.exists():
                zf.write(shot, arcname=png_name)
        steps.append(
            {
                "step_index": step_index,
                "ti_index": ti_index,
                "interaction_id": interaction_id,
                "surface": row.get("surface", ""),
                "element": row.get("element", ""),
                "action": row.get("action", ""),
                "expected": _expected_result(row),
                "ti_status": row.get("status", ""),
                "ti_evidence": _actual_result(row),
                "screenshot": str(row.get("screenshot") or ""),
                "brief_md": str(brief_path),
                "zip": str(zip_path.resolve()),
            }
        )

    manifest = {
        "schema": "review_page.webgpt_steps.v1",
        "page": page.page_id,
        "title": page.title,
        "persona_id": page.persona_id,
        "total_steps": total,
        "steps": steps,
        "ask_command_hint": (
            f"$ask webgpt /review-page {page.page_id} --step-loop "
            f"(after review-page prepare-webgpt-steps or package in same out_dir)"
        ),
    }
    manifest_path = steps_dir / "webgpt_steps_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    manifest["steps_dir"] = str(steps_dir)
    return manifest


@app.command("prepare-webgpt-steps")
def prepare_webgpt_steps_cmd(
    page_id: str = typer.Option(..., "--page"),
    ti_results: Path | None = None,
    capture_dir: Path | None = None,
    out_dir: Path | None = None,
    allow_no_screenshot: bool = typer.Option(False, "--allow-no-screenshot"),
):
    """Emit per-interaction step zips (brief + screenshot) for WebGPT step loop."""
    page = _page(page_id)
    out, results_path = _resolve_paths(page, ti_results, out_dir, capture_dir)
    copied = out / "test-interactions-results.json"
    if not copied.exists() and results_path.exists():
        shutil.copy2(results_path, copied)
    if copied.exists():
        results = _load_results(copied)
    else:
        results = _load_results(results_path)
    manifest = prepare_webgpt_steps(
        page,
        results,
        out,
        require_screenshot=not allow_no_screenshot,
    )
    typer.echo(json.dumps(manifest, indent=2))
    if not manifest.get("total_steps"):
        raise typer.Exit(2)
    raise typer.Exit(0)


ASK_RUN = Path(os.environ.get("ASK_RUN", "/home/graham/workspace/experiments/agent-skills/skills/ask/run.sh"))


@app.command("prepare-vlm")
def prepare_vlm_cmd(
    page_id: str = typer.Option(..., "--page"),
    ti_results: Path | None = None,
    capture_dir: Path | None = None,
    out_dir: Path | None = None,
    round_label: str = "1",
):
    """Prepare optional oc-kimi VLM pre-review (non-authoritative). Does not call WebGPT."""
    page = _page(page_id)
    out, results_path = _resolve_paths(page, ti_results, out_dir, capture_dir)
    results = _load_results(results_path)
    _finalize_review_outputs(page, results, results_path, out, round_label, skip_zip=False)
    contact = out / "contact-sheet.png"
    req = out / "vlm-adjudication-request.md"
    ti_rows = []
    for idx, row in enumerate(results.get("interactions") or [], start=1):
        if row.get("action") == "qid_compliance":
            continue
        qids = _qids_from_interaction(row)
        qid = qids[0] if qids else row.get("element", "")
        ti_rows.append(f"| {idx} | `{qid}` | {row.get('description') or row.get('element','')} | {row.get('status','')} |")
    req.write_text(
        f"# VLM pre-review ({page.page_id})\n\nNon-authoritative. TI FAIL cannot be upgraded.\n\n"
        + "| # | qid | expected | TI |\n|---:|---|---|---|\n"
        + "\n".join(ti_rows)
        + "\n\nReturn JSON array: qid, expected, observed, agrees_with_ti, notes.\n",
        encoding="utf-8",
    )
    payload = {
        "schema": "review_page.vlm_prepare.v1",
        "page": page.page_id,
        "contact_sheet": str(contact) if contact.exists() else "",
        "request_md": str(req),
        "ask_command_hint": (
            (
                f"{ASK_RUN} ask oc-kimi "
                f"'VLM pre-review for {page.page_id}. Read {req}. "
                f"Return structured per-row qid|expected|observed|agrees_with_ti. Non-authoritative.' "
                f"--oracle --oracle-image {contact} --once"
            )
            if contact.exists()
            else "Run build first to create contact-sheet.png"
        ),
    }
    (out / "vlm_prepare.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    typer.echo(json.dumps(payload, indent=2))



@app.command("list-pages")
def list_pages():
    for idx, page_id in enumerate(REVIEW_ORDER, start=1):
        page = PAGES[page_id]
        typer.echo(f"{idx:02d}. {page_id:16} persona={page.persona_id:16} manifest={page.manifest or '-'}")

@app.command("preflight")
def preflight_cmd(page_id: str = typer.Option(..., "--page"), ti_results: Path | None = None, capture_dir: Path | None = None, out_dir: Path | None = None):
    page = _page(page_id)
    out, results_path = _resolve_paths(page, ti_results, out_dir, capture_dir)
    results = _load_results(results_path)
    _, labeled = _screenshot_inventory(results, page.page_id)
    gate = preflight(page, results, labeled)
    write_gate(out, page, gate, results_path)
    typer.echo(json.dumps({"verdict": gate.verdict, "reason": gate.reason}, indent=2))
    raise typer.Exit(0 if gate.verdict == "PASS" else 2)

@app.command("build")
def build_cmd(page_id: str = typer.Option(..., "--page"), ti_results: Path | None = None, capture_dir: Path | None = None,
    out_dir: Path | None = None, round_label: str = "1", skip_zip: bool = False):
    page = _page(page_id)
    out, results_path = _resolve_paths(page, ti_results, out_dir, capture_dir)
    results = _load_results(results_path)
    review_md_path, gate, _, contact_sheet, zip_path = _finalize_review_outputs(
        page, results, results_path, out, round_label, skip_zip=skip_zip)
    if contact_sheet:
        typer.echo(f"Contact sheet: {contact_sheet}")
    if zip_path:
        typer.echo(f"Zip: {zip_path}")
    typer.echo(f"Wrote {review_md_path}\nGate: {gate.verdict} ({gate.reason})")

@app.command("run-ti")
def run_ti_cmd(page_id: str = typer.Option(..., "--page"), capture_suffix: str = ""):
    page = _page(page_id)
    base = page.default_capture_dir or f"{page.page_id}-webgpt"
    capture_dir = TI_CAPTURES / f"{base}{capture_suffix}"
    typer.echo(f"results: {run_ti(page, capture_dir)}")


if __name__ == "__main__":
    app()
