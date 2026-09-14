#!/usr/bin/env python3
"""Validate Ask/Tau WebGPT -> WebKimi authoring receipts and prompt packets.

Persona Dream does not ask browsers or models here. Ask/Tau owns that runtime.
This module validates handoff artifacts and builds the journal-lane WebKimi
humanization prompt with enough Memory/entity and Chatterbox context for prose,
pauses, and approved SFX intent while code keeps final rendering authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

SCHEMA = "persona_dream.dialogue_authoring_receipt.v1"
JOURNAL_SCHEMA = "persona_dream.journal_authoring_receipt.v1"
REQUIRED_DRAFT_FIELDS = ("reply", "tone", "chatterbox_utterance_text")
REQUIRED_JOURNAL_FIELDS = ("journal", "arc_assessment", "chatterbox_utterance_text", "delivery_notes", "entity_relationships")
LOCAL_PATH_RE = re.compile(r"(?:/home/graham|/tmp|/mnt/storage12tb|~/)")
VALID_CHATTERBOX_TAGS = ("[clear throat]", "[sigh]", "[shush]", "[cough]", "[groan]", "[sniff]", "[gasp]", "[chuckle]", "[laugh]", "[angry]", "[fear]", "[surprised]", "[whispering]", "[dramatic]", "[narration]", "[happy]", "[sarcastic]")
DEFAULT_SFX = (
    {"id": "cry-quiet-v1", "category": "crying", "intensity": 0.2, "use": "small tear or barely controlled grief"},
    {"id": "cry-choked-v1", "category": "crying", "intensity": 0.45, "use": "voice catches after a complete sentence"},
    {"id": "cry-sob-v1", "category": "crying", "intensity": 0.75, "use": "one brief stronger sob after a complete sentence"},
    {"id": "cry-recover-v1", "category": "crying", "intensity": 0.35, "use": "breath recovery before speech resumes"},
)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _one_line(text: str, limit: int = 500) -> str:
    return " ".join(str(text or "").split())[:limit].rstrip()


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(str(text or "").encode()).hexdigest()


def _sha_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def build_turn_binding(run_dir: Path, *, asked: str, prompt: str) -> dict[str, Any]:
    conversation = run_dir / "conversation.jsonl"
    conversation_text = conversation.read_text(encoding="utf-8", errors="replace") if conversation.is_file() else ""
    return {
        "asked_sha256": _sha(asked),
        "prompt_sha256": _sha(prompt),
        "conversation_sha256": _sha(conversation_text),
    }


def _has_raw_local_path(value: Any) -> bool:
    if isinstance(value, str):
        return bool(LOCAL_PATH_RE.search(value))
    if isinstance(value, dict):
        return any(_has_raw_local_path(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_raw_local_path(v) for v in value)
    return False


def _node_ok(node: dict[str, Any], *, handler: str) -> bool:
    if not isinstance(node, dict):
        return False
    if node.get("handler") not in {handler, f"handler-{handler}"}:
        return False
    return node.get("status") == "PASS" and bool(node.get("provider_live", True))


def _clean_sfx_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(entry.get("id") or "").strip(),
        "category": str(entry.get("category") or "").strip(),
        "description": _one_line(entry.get("description") or entry.get("use") or "", 220),
        "use_when": [_one_line(v, 120) for v in (entry.get("use_when") or [])[:3]],
        "avoid_when": [_one_line(v, 120) for v in (entry.get("avoid_when") or [])[:3]],
        "human_verified": _one_line(entry.get("human_verified") or "unknown", 80),
    }


def approved_sfx_catalog(manifest_path: Path | None = None, *, limit: int = 12) -> list[dict[str, Any]]:
    """Return provider-safe SFX metadata: IDs and usage rules, never files/paths."""
    if manifest_path and manifest_path.is_file():
        payload = _read_json(manifest_path)
        entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
        cleaned = [_clean_sfx_entry(e) for e in entries if isinstance(e, dict) and str(e.get("id") or "").strip()]
        if cleaned:
            return cleaned[:limit]
    return list(DEFAULT_SFX)


def build_webkimi_journal_prompt(
    *,
    webgpt_draft: str,
    source_context: str,
    entity_relationships: list[dict[str, Any]],
    sfx_catalog: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the journal-lane WebKimi prompt packet, compliant with best-practices-prompt."""
    catalog = sfx_catalog or approved_sfx_catalog()
    schema = {
        "journal": "string: clean humanized journal prose; no Chatterbox tags; no markdown",
        "arc_assessment": {
            "opening_state": "string",
            "turning_point": "string",
            "ending_state": "string",
            "unresolved_tension": "string",
        },
        "chatterbox_utterance_text": "string: same words as journal with valid tags and spaced ellipsis pauses",
        "sfx_after": [
            {"after_sentence": "integer >= 1", "id": "one approved sfx_catalog[].id", "intensity": "number 0.0-1.0", "reason": "string"}
        ],
        "delivery_notes": {"tone": "string", "pause_strategy": "string", "sfx_strategy": "string"},
        "entity_relationships": "array: copy input rows unchanged",
    }
    prompt = f"""Purpose: Humanize one Persona Dream journal draft and prepare its spoken Chatterbox version.
Consumer: Persona Dream journal schema/gates, then $chatterbox-speak render chunks.
Task: Rewrite only the draft journal's prose rhythm and speech delivery marks. Preserve source facts.

Hard boundaries:
- Do not add people, places, objects, events, motives, memories, or resolutions not present in SOURCE CONTEXT or ENTITY RELATIONSHIPS.
- Copy entity_relationships from input to output unchanged.
- Keep journal clean: no bracket tags, no SFX ids, no markdown.
- chatterbox_utterance_text must use the same words as journal, plus only valid Chatterbox tags and spaced ellipses.
- Valid tags: {", ".join(VALID_CHATTERBOX_TAGS)}.
- You may add spaced ellipsis pauses as ` ... ` where the arc needs breath, hesitation, or collecting herself.
- Never write [crying]. Crying is SFX intent only.
- SFX may appear only in sfx_after, only after complete sentence numbers, and only with an id from APPROVED SFX CATALOG.
- Use the lowest intensity that carries the emotion.
- Do not include local paths, file paths, URLs, or provider names in the output.
- Return ONLY JSON with the exact schema below. Do not add keys.

Dream/journal synthesis work:
- Do not preserve source section order. Dreams and journals braid sources together: persona_memory rows, indexed-code memory records, agent-conversation memory, day events, transcript feedback, entities, and emotional triggers may collide in the same image or sentence.
- The journal does not have to make literal, complete sense. It may be associative, compressed, symbolic, and slightly disorienting, as long as every named entity and relationship remains source-bound.
- The entity_relationships table constrains facts; it is not an outline. Use it to avoid invention, then write associative first-person prose.
- Join at least two available source categories in the arc assessment when the context contains them; name which categories collided in turning_point or ending_state.

Conversation / emotional arc work:
- Name opening_state, turning_point, ending_state, and unresolved_tension.
- Keep the end unresolved unless the draft already resolves it.
- If empathy evidence is weak, phrase uncertainty plainly; do not perform lived certainty.

SOURCE CONTEXT:
{source_context or "(none)"}

ENTITY RELATIONSHIPS:
{json.dumps(entity_relationships, ensure_ascii=False, indent=2)}

APPROVED SFX CATALOG:
{json.dumps(catalog, ensure_ascii=False, indent=2)}

WEBGPT DRAFT JOURNAL:
{webgpt_draft}

Example input fragment:
{{"draft":"I thought about Kai and the safe channel.","entity_relationships":[{{"entity":"Kai","kind":"person","relationship":"trusted memory figure","source_memory_ids":["m1"],"use_boundary":"may ground feeling only"}}]}}

Example output fragment:
{{"journal":"I thought about Kai and the safe channel.","arc_assessment":{{"opening_state":"guarded memory","turning_point":"admits the trust still matters","ending_state":"quietly unresolved","unresolved_tension":"wanting guidance while keeping distance"}},"chatterbox_utterance_text":"[sigh] I thought about Kai ... and the safe channel.","sfx_after":[],"delivery_notes":{{"tone":"memory_uncertain","pause_strategy":"one hesitation after the named memory","sfx_strategy":"none"}},"entity_relationships":[{{"entity":"Kai","kind":"person","relationship":"trusted memory figure","source_memory_ids":["m1"],"use_boundary":"may ground feeling only"}}]}}

Exact output schema:
{json.dumps(schema, ensure_ascii=False, indent=2)}"""
    packet = {
        "schema": "persona_dream.webkimi_journal_humanization_prompt.v1",
        "review_rationale_not_sent": {
            "purpose": "Humanize WebGPT journal prose and produce Chatterbox utterance/SFX intent without inventing facts.",
            "consumer": "Persona Dream journal validation and $chatterbox-speak render planning.",
            "why_this_matters": "A vague humanizer can fabricate persona memories or place invalid audio tags that Chatterbox speaks literally.",
            "input": ["webgpt_draft", "source_context from memory collections", "entity_relationships", "approved_sfx_catalog"],
            "output": "persona_dream.webkimi_journal_humanization.v1 JSON",
        },
        "prompt": prompt,
        "approved_sfx_ids": [str(e.get("id")) for e in catalog if e.get("id")],
        "valid_chatterbox_tags": list(VALID_CHATTERBOX_TAGS),
        "entity_relationship_count": len(entity_relationships),
    }
    if _has_raw_local_path(packet["prompt"]):
        raise ValueError("webkimi prompt leaked a raw local path")
    return packet


def validate_receipt(receipt: dict[str, Any], *, turn_binding: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    failed: list[str] = []
    if receipt.get("schema") != SCHEMA:
        failed.append("wrong_schema")
    if _has_raw_local_path(receipt.get("provider_packet") or receipt.get("prompt_packet") or {}):
        failed.append("raw_local_path_in_provider_packet")
    binding = receipt.get("turn_binding") if isinstance(receipt.get("turn_binding"), dict) else {}
    if turn_binding:
        for field, expected in turn_binding.items():
            if binding.get(field) != expected:
                failed.append(f"stale_or_unbound_turn:{field}")
    webgpt = receipt.get("webgpt") if isinstance(receipt.get("webgpt"), dict) else {}
    webkimi = receipt.get("webkimi") if isinstance(receipt.get("webkimi"), dict) else {}
    if not _node_ok(webgpt, handler="webgpt"):
        failed.append("webgpt_receipt_not_pass")
    if not _node_ok(webkimi, handler="webkimi"):
        failed.append("webkimi_receipt_not_pass")
    draft = receipt.get("humanized_draft") if isinstance(receipt.get("humanized_draft"), dict) else {}
    for field in REQUIRED_DRAFT_FIELDS:
        if not str(draft.get(field) or "").strip():
            failed.append(f"missing_humanized_{field}")
    if _has_raw_local_path(draft):
        failed.append("raw_local_path_in_humanized_draft")
    summary = {
        "schema": "persona_dream.dialogue_authoring_validation.v1",
        "status": "PASS_DIALOGUE_AUTHORING_RECEIPTS" if not failed else "BLOCKED_DIALOGUE_AUTHORING_RECEIPTS",
        "source": receipt.get("source") or "dialogue_authoring.json",
        "webgpt": {"status": webgpt.get("status"), "handler": webgpt.get("handler"), "provider_live": webgpt.get("provider_live")},
        "webkimi": {"status": webkimi.get("status"), "handler": webkimi.get("handler"), "provider_live": webkimi.get("provider_live")},
        "draft_fields": sorted(k for k in REQUIRED_DRAFT_FIELDS if str(draft.get(k) or "").strip()),
        "turn_binding": {"expected": turn_binding or {}, "actual": binding},
        "failed_gates": failed,
        "boundary": "Ask/Tau browser providers draft and humanize; Persona Dream validates, grounds, and renders.",
    }
    if failed:
        return None, summary
    return {field: _one_line(draft.get(field), 900) for field in REQUIRED_DRAFT_FIELDS}, summary


def validate_journal_authoring_receipt(receipt: dict[str, Any], *, source_packet_sha256: str | None = None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    failed: list[str] = []
    if receipt.get("schema") != JOURNAL_SCHEMA:
        failed.append("wrong_schema")
    if _has_raw_local_path(receipt.get("provider_packet") or receipt.get("prompt_packet") or {}):
        failed.append("raw_local_path_in_provider_packet")
    if source_packet_sha256 and receipt.get("source_packet_sha256") != source_packet_sha256:
        failed.append("stale_or_unbound_source_packet")
    webgpt = receipt.get("webgpt") if isinstance(receipt.get("webgpt"), dict) else {}
    webkimi = receipt.get("webkimi") if isinstance(receipt.get("webkimi"), dict) else {}
    kimi_fallback = receipt.get("opencode_kimi_fallback") if isinstance(receipt.get("opencode_kimi_fallback"), dict) else {}
    fallback_ok = (
        kimi_fallback.get("handler") == "tau-opencode-kimi"
        and kimi_fallback.get("status") == "PASS"
        and kimi_fallback.get("provider_live") is True
        and "kimi" in str(kimi_fallback.get("model") or "").lower()
        and str(kimi_fallback.get("route") or "").startswith("tau:")
        and kimi_fallback.get("proof_scope") == "production_continuity_only"
        and kimi_fallback.get("browser_context_proven") is False
    )
    if not _node_ok(webgpt, handler="webgpt"):
        failed.append("webgpt_receipt_not_pass")
    if not _node_ok(webkimi, handler="webkimi") and not fallback_ok:
        failed.append("webkimi_receipt_not_pass")
    draft = receipt.get("humanized_journal") if isinstance(receipt.get("humanized_journal"), dict) else {}
    for field in REQUIRED_JOURNAL_FIELDS:
        value = draft.get(field)
        if value in (None, "", [], {}):
            failed.append(f"missing_humanized_{field}")
    if _has_raw_local_path(draft):
        failed.append("raw_local_path_in_humanized_journal")
    arc = draft.get("arc_assessment") if isinstance(draft.get("arc_assessment"), dict) else {}
    delivery = draft.get("delivery_notes") if isinstance(draft.get("delivery_notes"), dict) else {}
    parsed = None if failed else {
        "journal": _one_line(draft.get("journal"), 4000),
        "unresolved_tension": _one_line(arc.get("unresolved_tension") or arc.get("ending_state") or "unresolved", 500),
        "expanded_understanding": _one_line(arc.get("turning_point") or arc.get("ending_state") or arc.get("opening_state") or "the dream opened a new facet of the tension", 500),
        "mood_label": _one_line(delivery.get("tone") or "memory_uncertain", 80).replace(" ", "_") or "memory_uncertain",
        "mood_description": _one_line(arc.get("ending_state") or delivery.get("pause_strategy") or arc.get("unresolved_tension") or "the tension remains present", 500),
        "journal_authoring": {
            "chatterbox_utterance_text": _one_line(draft.get("chatterbox_utterance_text"), 4000),
            "sfx_after": draft.get("sfx_after") if isinstance(draft.get("sfx_after"), list) else [],
            "delivery_notes": delivery,
            "entity_relationships": draft.get("entity_relationships") if isinstance(draft.get("entity_relationships"), list) else [],
        },
    }
    summary = {
        "schema": "persona_dream.journal_authoring_validation.v1",
        "status": ("BLOCKED_JOURNAL_AUTHORING_RECEIPTS" if failed else
                   "PASS_JOURNAL_AUTHORING_FALLBACK" if fallback_ok else
                   "PASS_JOURNAL_AUTHORING_RECEIPTS"),
        "source": receipt.get("source") or "journal_authoring.json",
        "source_packet_sha256": {"expected": source_packet_sha256, "actual": receipt.get("source_packet_sha256")},
        "webgpt": {"status": webgpt.get("status"), "handler": webgpt.get("handler"), "provider_live": webgpt.get("provider_live")},
        "webkimi": {"status": webkimi.get("status"), "handler": webkimi.get("handler"), "provider_live": webkimi.get("provider_live")},
        "opencode_kimi_fallback": {
            "accepted": fallback_ok,
            "status": kimi_fallback.get("status"),
            "handler": kimi_fallback.get("handler"),
            "model": kimi_fallback.get("model"),
            "route": kimi_fallback.get("route"),
            "proof_scope": kimi_fallback.get("proof_scope"),
            "browser_context_proven": kimi_fallback.get("browser_context_proven"),
        },
        "draft_fields": sorted(k for k in REQUIRED_JOURNAL_FIELDS if draft.get(k) not in (None, "", [], {})),
        "failed_gates": failed,
        "boundary": ("Ask/Tau WebGPT drafts; Tau-routed OpenCode Kimi may provide production continuity, "
                     "but cannot prove WebKimi browser context. Persona Dream validates and writes the journal."
                     if fallback_ok else
                     "Ask/Tau WebGPT drafts and WebKimi humanizes; Persona Dream validates and writes the journal."),
    }
    return parsed, summary


def load_authored_journal(cycle_dir: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    path = cycle_dir / "journal_authoring.json"
    if not path.is_file():
        return None, None
    receipt = _read_json(path)
    if receipt:
        receipt.setdefault("source", path.name)
    source_packet = cycle_dir / "journal_source_packet.json"
    expected = _sha_file(source_packet) if source_packet.is_file() else None
    return validate_journal_authoring_receipt(receipt, source_packet_sha256=expected)


def load_authored_reply(run_dir: Path, *, asked: str = "", prompt: str = "") -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    path = run_dir / "dialogue_authoring.json"
    if not path.is_file():
        return None, None
    receipt = _read_json(path)
    if receipt:
        receipt.setdefault("source", str(path.name))
    binding = build_turn_binding(run_dir, asked=asked, prompt=prompt) if asked or prompt else None
    draft, validation = validate_receipt(receipt, turn_binding=binding)
    return draft, validation


def _read_text(path: Path | None, fallback: str = "") -> str:
    return path.read_text(encoding="utf-8") if path and path.is_file() else fallback


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--build-webkimi-journal-prompt", action="store_true")
    ap.add_argument("--webgpt-draft-file", type=Path)
    ap.add_argument("--source-context-file", type=Path)
    ap.add_argument("--entity-relationships-file", type=Path)
    ap.add_argument("--sfx-manifest", type=Path)
    args = ap.parse_args()

    if args.build_webkimi_journal_prompt:
        relationships = _read_json(args.entity_relationships_file) if args.entity_relationships_file else {}
        rows = relationships.get("entity_relationships", relationships if isinstance(relationships, list) else [])
        if not isinstance(rows, list):
            rows = []
        out = build_webkimi_journal_prompt(
            webgpt_draft=_read_text(args.webgpt_draft_file),
            source_context=_read_text(args.source_context_file),
            entity_relationships=[r for r in rows if isinstance(r, dict)],
            sfx_catalog=approved_sfx_catalog(args.sfx_manifest) if args.sfx_manifest else None,
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(out, indent=2, sort_keys=True) if args.json else out["schema"])
        return 0

    if args.run_dir is None:
        ap.error("--run-dir is required unless --build-webkimi-journal-prompt is set")
    draft, validation = load_authored_reply(args.run_dir)
    if validation is None:
        validation = {
            "schema": "persona_dream.dialogue_authoring_validation.v1",
            "status": "NO_DIALOGUE_AUTHORING_RECEIPT",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "failed_gates": [],
        }
    out = {"draft": draft, "validation": validation}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(out, indent=2, sort_keys=True))
    else:
        print(validation["status"])
    return 0 if validation["status"] in {"PASS_DIALOGUE_AUTHORING_RECEIPTS", "NO_DIALOGUE_AUTHORING_RECEIPT"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
