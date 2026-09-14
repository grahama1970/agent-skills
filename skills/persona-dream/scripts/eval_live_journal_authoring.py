#!/usr/bin/env python3
"""Live Persona Dream journal authoring eval: Memory -> WebGPT -> WebKimi -> journal."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
ASK = REPO / "skills" / "ask" / "run.sh"
SURF = REPO / "skills" / "surf" / "run.sh"
BROWSER_ORACLE = REPO / "skills" / "browser-oracle" / "run.sh"
OPENCODE_KIMI_MODEL = "opencode-go/kimi-k2.6"

sys.path.insert(0, str(ROOT / "scripts"))
import tau_text_reasoning_adapter as tau_adapter


def run(cmd: list[str], *, cwd: Path = REPO, timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout, check=False)
    if check and proc.returncode != 0:
        raise RuntimeError(f"command failed rc={proc.returncode}: {' '.join(cmd)}\nSTDERR:\n{proc.stderr[-4000:]}\nSTDOUT:\n{proc.stdout[-4000:]}")
    return proc


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def first_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("provider response did not contain a JSON object")
    return json.loads(text[start : end + 1])


def bind_browser_tabs(*, allow_missing_webkimi: bool = False) -> dict[str, str]:
    live_tabs = json.loads(run([str(SURF), "tab.list", "--json"], timeout=60).stdout)
    tabs: dict[str, str] = {}
    for backend, host in (("webgpt", "chatgpt.com"), ("webkimi", "kimi.ai")):
        try:
            proc = run([str(BROWSER_ORACLE), "resolve", "--project", "tau", "--backend", backend, "--json"], timeout=60)
            binding = json.loads(proc.stdout)
            tab_id = str(binding.get("tab_id") or "")
            live = next((tab for tab in live_tabs if str(tab.get("id")) == tab_id), None)
            if not live or host not in str(live.get("url") or ""):
                raise RuntimeError(f"live browser binding unavailable for {backend}")
            live_url = str(live.get("url") or "")
            if live_url != str(binding.get("conversation_url") or ""):
                run([
                    str(BROWSER_ORACLE), "bind", "tau", "--backend", backend,
                    "--tab-id", tab_id, "--url", live_url, "--manual", "--json",
                ], timeout=60)
            tabs[f"{backend}_tab"] = tab_id
        except (RuntimeError, json.JSONDecodeError):
            if backend != "webkimi" or not allow_missing_webkimi:
                raise
    return tabs


def ask_one(prompt: str, *, handler: str, target: str, goal: str, root: Path, attach: Path | None = None, lifecycle: str = "reuse-bound") -> tuple[Path, dict[str, Any]]:
    cmd = [
        str(ASK), "tau-dag", prompt,
        "--repo", "agent-skills",
        "--target", target,
        "--immutable-goal", goal,
        "--dag-template", "single-call",
        "--handler", handler,
        "--handler-project", f"{handler}=tau",
        "--browser-tab-lifecycle", lifecycle,
        "--execute",
        "--poll-timeout-seconds", "900",
        "--execution-timeout-seconds", "900",
        "--run-output-root", str(root),
        "--json",
    ]
    if attach is not None:
        cmd.extend(["--attach-file", str(attach)])
    proc = run(cmd, timeout=1200, check=False)
    (root.parent / f"{handler}.ask.stdout").write_text(proc.stdout, encoding="utf-8")
    (root.parent / f"{handler}.ask.stderr").write_text(proc.stderr, encoding="utf-8")
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ask {handler} did not emit JSON rc={proc.returncode}: {proc.stderr[-2000:]}") from exc
    ask_dirs = sorted(root.glob("ask-*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not ask_dirs:
        raise RuntimeError(f"Ask {handler} did not create an ask-* artifact directory")
    if result.get("status") != "PASS":
        execution = result.get("execution") or {}
        receipt = execution.get("receipt") or {}
        failure = receipt.get("failure_code") or receipt.get("verdict") or "unknown_failure"
        raise RuntimeError(f"Ask {handler} did not pass: {result.get('status')} {failure}")
    return ask_dirs[0], result


def require_provider_response(base: Path, handler: str, *, min_chars: int = 1000) -> tuple[dict[str, Any], str]:
    hdir = base / "node-artifacts" / f"handler-{handler}"
    receipt = load_json(hdir / "node-receipt.json")
    response_path = hdir / "response.md"
    if receipt.get("status") != "PASS" or receipt.get("handler") != handler:
        raise RuntimeError(f"{handler} receipt was not PASS: {receipt.get('status')} {receipt.get('handler')}")
    response = response_path.read_text(encoding="utf-8")
    if len(response.strip()) < min_chars:
        raise RuntimeError(f"{handler} response too small or missing: {len(response.strip())} < {min_chars}")
    return receipt, response


def humanize_with_opencode_kimi(prompt: str) -> tuple[dict[str, Any], dict[str, Any]]:
    output_contract = {
        "journal": "string",
        "arc_assessment": {"opening_state": "string", "turning_point": "string", "ending_state": "string", "unresolved_tension": "string"},
        "chatterbox_utterance_text": "string",
        "sfx_after": "array",
        "delivery_notes": {"tone": "string", "pause_strategy": "string", "sfx_strategy": "string"},
        "entity_relationships": "array",
    }
    parsed, receipt = tau_adapter.dispatch_text_reasoning(
        prompt,
        "persona-dream-journal-humanizer",
        output_contract=output_contract,
        model=OPENCODE_KIMI_MODEL,
        exact_model=True,
        timeout_s=300,
    )
    model = str(receipt.get("model") or "")
    if parsed is None or receipt.get("status") != "PASS" or receipt.get("live_call_performed") is not True or "kimi" not in model.lower():
        raise RuntimeError(f"Tau OpenCode Kimi fallback did not pass: {receipt.get('status')} {model}")
    return parsed, {
        "handler": "tau-opencode-kimi",
        "status": "PASS",
        "provider_live": True,
        "model": model,
        "route": "tau:persona-dream-text-reasoning",
        "proof_scope": "production_continuity_only",
        "browser_context_proven": False,
        "tau_receipt_schema": receipt.get("schema"),
        "prompt_sha256": receipt.get("prompt_sha256"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, default=Path("/tmp/persona-dream-live-journal-agentic-proof.json"))
    ap.add_argument("--run-root", type=Path, default=None)
    ap.add_argument("--allow-opencode-kimi-fallback", action="store_true", help="Use Tau-routed OpenCode Kimi only when the WebKimi transport cannot pass")
    args = ap.parse_args()

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_root = args.run_root or Path(f"/tmp/persona-dream-live-journal-{stamp}-{os.getpid()}-{time.time_ns()}")
    cycle_name = f"cycle_{stamp}_{os.getpid()}"
    cycle = run_root / cycle_name
    cycle.mkdir(parents=True, exist_ok=True)

    tabs = bind_browser_tabs(allow_missing_webkimi=args.allow_opencode_kimi_fallback)
    run([
        "bash", str(ROOT / "run.sh"), "build-journal-source-packet",
        "--cycle-dir", str(cycle),
        "--query", "Persona Dream journal Graham correction WebGPT WebKimi Kai safe channel live evidence",
        "--mode", "mixed",
        "--seed", f"live-journal-{stamp}",
        "--limit", "6",
        "--k", "12",
        "--collections", "persona_memory,persona_journal,agent_conversations,code_symbols,project_activity",
        "--json",
    ], timeout=180)

    source_md = run_root / "webgpt-source-packet.md"
    source_md.write_text("# Persona Dream journal source packet\n\n```json\n" + (cycle / "journal_source_packet.json").read_text(encoding="utf-8") + "\n```\n", encoding="utf-8")
    webgpt_prompt = "Draft Persona Dream journal prose from the attached source packet. Use it as dream fuel, not a report outline. Do not claim direct memory access. Return Markdown with draft journal prose, source-bound entity notes, and uncertainty/boundary notes. If a browser automation completion contract appears after the source material, append its marker exactly as instructed."
    webgpt_base, _ = ask_one(
        webgpt_prompt,
        handler="webgpt",
        target="persona-dream-live-journal-webgpt",
        goal="Return a source-bound Persona Dream journal draft from the attached source packet; do not claim direct memory access.",
        root=run_root / "ask-webgpt",
        attach=source_md,
        lifecycle="reuse-bound",
    )
    webgpt_receipt, webgpt_response = require_provider_response(webgpt_base, "webgpt")

    bundle = run_root / "webkimi-bundle.md"
    bundle.write_text(
        "# Persona Dream WebKimi journal humanization bundle\n\n"
        "## Source context\n" + (cycle / "journal_source_context.md").read_text(encoding="utf-8") + "\n"
        "## Entity relationships\n```json\n" + (cycle / "journal_entity_relationships.json").read_text(encoding="utf-8") + "\n```\n"
        "## WebGPT draft\n" + webgpt_response + "\n",
        encoding="utf-8",
    )
    webkimi_prompt = (
        "Humanize this Persona Dream bundle. Return ONLY JSON with fields: journal, "
        "arc_assessment {opening_state, turning_point, ending_state, unresolved_tension}, "
        "chatterbox_utterance_text, sfx_after, delivery_notes {tone, pause_strategy, sfx_strategy}, "
        "entity_relationships. Use only the source and WebGPT draft below; keep named entities source-bound.\n\n"
        + bundle.read_text(encoding="utf-8")
    )
    fallback_receipt: dict[str, Any] | None = None
    webkimi_summary: dict[str, Any]
    webkimi_response_path: Path | None = None
    webkimi_transport_error: RuntimeError | None = None
    try:
        if "webkimi_tab" not in tabs:
            raise RuntimeError("live browser binding unavailable for webkimi")
        webkimi_base, _ = ask_one(
            webkimi_prompt,
            handler="webkimi",
            target="persona-dream-live-journal-webkimi",
            goal="Return only final Persona Dream journal-authoring JSON humanized from the attached source packet and WebGPT draft.",
            root=run_root / "ask-webkimi",
            attach=None,
            lifecycle="reuse-bound",
        )
    except RuntimeError as exc:
        webkimi_transport_error = exc

    if webkimi_transport_error is not None:
        if not args.allow_opencode_kimi_fallback:
            raise webkimi_transport_error
        humanized, fallback_receipt = humanize_with_opencode_kimi(webkimi_prompt)
        webkimi_summary = {"handler": "webkimi", "status": "BLOCKED", "provider_live": False, "failure": str(webkimi_transport_error)[:500]}
    else:
        _, webkimi_response = require_provider_response(webkimi_base, "webkimi")
        webkimi_meta = load_json(webkimi_base / "node-artifacts" / "handler-webkimi" / "response.meta.json")
        if webkimi_meta.get("submitted_to_kimi") is not True:
            raise RuntimeError("WebKimi submission was not proven")
        humanized = first_json_object(webkimi_response)
        webkimi_response_path = webkimi_base / "node-artifacts" / "handler-webkimi" / "response.md"
        webkimi_summary = {"handler": "webkimi", "status": "PASS", "provider_live": True}

    for field in ("journal", "arc_assessment", "chatterbox_utterance_text", "delivery_notes", "entity_relationships"):
        if humanized.get(field) in (None, "", [], {}):
            raise RuntimeError(f"journal humanizer response missing {field}")
    source_sha = "sha256:" + hashlib.sha256((cycle / "journal_source_packet.json").read_bytes()).hexdigest()
    authoring_receipt = {
        "schema": "persona_dream.journal_authoring_receipt.v1",
        "source_packet_sha256": source_sha,
        "provider_packet": {
            "source": "ask_tau_live_browser_receipts" if fallback_receipt is None else "ask_tau_webgpt_with_opencode_kimi_fallback",
            "boundary": "local proof paths are retained in this proof, not sent as provider prose",
        },
        "webgpt": {"handler": "webgpt", "status": "PASS", "provider_live": True},
        "webkimi": webkimi_summary,
        "humanized_journal": humanized,
    }
    if fallback_receipt is not None:
        authoring_receipt["opencode_kimi_fallback"] = fallback_receipt
    (cycle / "journal_authoring.json").write_text(json.dumps(authoring_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    selected = load_json(cycle / "journal_source_packet.json").get("selection", {}).get("selected", [])
    seed_ids = [(row.get("source_id") or row.get("_key") or f"live-source-{i+1}") for i, row in enumerate(selected[:3])]
    (cycle / "residue_links.json").write_text(json.dumps({"items": [{"source_id": sid} for sid in seed_ids]}, indent=2) + "\n", encoding="utf-8")
    (cycle / "storyboard_plan.json").write_text(json.dumps({"dream_synopsis": "Embry dreamed of question labels, memory expansion, Kai as an unresolved source-bound flicker, and a lock that kept curiosity safe."}) + "\n", encoding="utf-8")
    (cycle / "selection_receipt.v1.json").write_text('{"chosen":{"valence_emphasis":"trust"}}\n', encoding="utf-8")
    (cycle / "phase14_tom.json").write_text('{"accepted_tom_candidates":[{"tom_state_type":"uncertainty","statement":"Embry wants to help without turning source hints into invented memory."}]}\n', encoding="utf-8")
    (cycle / "voice_weights").mkdir(exist_ok=True)
    (cycle / "voice_weights" / "dream_voice_weight_profile.v1.json").write_text('{"weights":[{"emotional_tag":"trust","weight":0.55},{"emotional_tag":"fear","weight":0.45}]}\n', encoding="utf-8")

    proc = run(["uv", "run", "--project", str(ROOT), "python", str(ROOT / "scripts" / "write_dream_journal.py"), "--cycle", cycle_name, "--persona", "embry", "--cycles-dir", str(run_root)], timeout=300, check=True)
    (run_root / "write-journal.stdout").write_text(proc.stdout, encoding="utf-8")
    (run_root / "write-journal.stderr").write_text(proc.stderr, encoding="utf-8")

    validation = load_json(cycle / "journal_authoring_validation.json")
    journal = load_json(cycle / "dream_journal.v1.json")
    speech = load_json(cycle / "journal_speech_plan.json")
    expected_validation = "PASS_JOURNAL_AUTHORING_FALLBACK" if fallback_receipt is not None else "PASS_JOURNAL_AUTHORING_RECEIPTS"
    if validation.get("status") != expected_validation:
        raise RuntimeError(f"journal authoring validation did not pass as {expected_validation}")
    if journal.get("schema") != "persona_dream.persona_journal.v1" or speech.get("schema") != "persona_dream.journal_speech_plan.v1":
        raise RuntimeError("journal or speech plan schema missing")

    proof = {
        "schema": "persona_dream.live_journal_authoring_e2e_proof.v1",
        "status": "PASS",
        "run_root": str(run_root),
        "tabs": tabs,
        "webgpt_response": str(webgpt_base / "node-artifacts" / "handler-webgpt" / "response.md"),
        "webkimi_response": str(webkimi_response_path) if webkimi_response_path else None,
        "webkimi_attachment_delivery_proven": webkimi_meta.get("attachment_delivery_proven") if fallback_receipt is None else False,
        "humanizer": "webkimi" if fallback_receipt is None else "tau-opencode-kimi",
        "opencode_kimi_fallback": fallback_receipt,
        "webkimi_browser_context_proven": fallback_receipt is None,
        "journal_validation": str(cycle / "journal_authoring_validation.json"),
        "journal": str(cycle / "dream_journal.v1.json"),
        "speech_plan": str(cycle / "journal_speech_plan.json"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("PERSONA_DREAM_LIVE_JOURNAL_E2E_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
