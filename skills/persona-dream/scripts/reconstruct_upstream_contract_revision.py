#!/usr/bin/env python3
"""Reconstruct missing upstream contract artifacts in one new immutable revision.

This command executes the HANDOFF "Next Gate" transaction rooted at the frozen
source revision:

1. Create a new immutable revision with sourceRevisionId equal to the active
   revision.
2. Produce and validate the seven missing canonical files for immutable-goal
   steps 05 (dream packet), 11 (Look Lock), 12 (Script DNA), and 15 (panel
   continuity and repair ledger).
3. Emit step-41 invalidation evidence for affected downstream steps 06-42.
4. Recompute the revision artifact index and manifest.
5. Run revision Memory prepare, exact verify, semantic verification, active
   pointer update, and activation.
6. Stage the deterministic 42-step pipeline record bundle inside the revision
   so a follow-up command can write and exactly reread the new revision-bound
   step records without mutating the frozen artifact set.

The command never mutates the source revision, never performs provider work,
and stops before compiling or submitting any Kling request. All seven new
files are deterministic reconstructions derived from accepted artifacts that
already exist in the source revision; every file records its exact derivation
sources by hash and states that no new live selector/model call is claimed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from jsonschema import Draft202012Validator

from activate_revision_qualification import activate
from idea_lineage import (
    BINDING_BASENAME,
    EXPECTED_PHASE_IDS,
    IdeaLineageError,
    build_lineage_manifest,
    build_phase_bindings,
    canonical_json_bytes,
    canonical_text,
    idea_id,
    idea_sha256,
    read_object,
    sha256_file,
    validate_revision_idea_lineage,
    validate_schema,
)
from prepare_revision_qualification import GateBlocked, prepare, verify
from validate_dream_packet import validate_dream_packet
from write_revision_artifact_index import write_index
from pydantic_step_gate import pydantic_error_messages

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = SKILL_ROOT / "schemas"
REPAIR_KIND = "upstream_contract_reconstruction"
EXCLUDED_ROOT_FILES = {
    "revision_artifact_index.json",
    "revision_manifest.json",
    "revision_memory_prepare_receipt.json",
    "revision_memory_verify_receipt.json",
    "revision_activation_receipt.json",
    "semantic_mix_repair_receipt.json",
}
EXCLUDED_PHASE_DIRS = {
    "phase_11_submit_return",
    "phase_12_watch_observation",
    "phase_13_final_acceptance",
}
PHASE_01_IDENTITY_FILES = {
    "human_idea.json",
    "dream_request.json",
    "residue_links.json",
    "contradiction_report.json",
    "idea_lineage_manifest.json",
}
LEDGER_NAME = "upstream_contract_invalidation_ledger.v1.json"
GATE_SUMMARY_NAME = "upstream_reconstruction_gate_summary.v1.json"
STEP_BUNDLE_NAME = "pipeline_step_records.v1.json"
STEP_COLLECTION = "persona_dream_pipeline_steps"

# The immutable-goal step table from GOAL.md, with the source-revision statuses
# recorded by the rev_idea_f3f9c48d5cc2 audit. Dispositions here define the new
# revision's deterministic step states: reconstructed steps pass, everything
# downstream is stale or superseded until Later Gate revalidation.
STEP_TABLE: list[tuple[int, str, str, str]] = [
    (1, "request_idea_intake", "Request / Idea Intake", "PASS"),
    (2, "dreaming_persona_selection", "Dreaming Persona Selection", "PASS_BOUND_REQUEST"),
    (3, "memory_recall", "Memory Recall", "PASS"),
    (4, "residue_grounding", "Residue Grounding", "PASS"),
    (5, "dream_packet", "Dream Packet", "BLOCKED_MISSING_REQUIRED_ARTIFACT"),
    (6, "story_video_plan", "Story / Video Plan", "PASS"),
    (7, "producer_selection", "Producer Persona Selection", "PASS"),
    (8, "director_selection", "Director Selection", "PASS"),
    (9, "script_writer_selection", "Script Writer Selection", "PASS"),
    (10, "creative_authority_receipts", "Creative Authority Receipts", "PASS"),
    (11, "look_lock", "Look Lock", "BLOCKED_MISSING_REQUIRED_ARTIFACT"),
    (12, "script_dna", "Script DNA", "BLOCKED_MISSING_REQUIRED_ARTIFACT"),
    (13, "storyboard_prompt_composition", "Storyboard Prompt Composition", "PASS"),
    (14, "storyboard_panel_receipts", "Storyboard Panel Receipts", "PASS"),
    (15, "panel_continuity_repair_ledger", "Panel Continuity And Repair Ledger", "BLOCKED_MISSING_REQUIRED_ARTIFACT"),
    (16, "panel_generation_loop", "Panel Generation Loop", "PASS"),
    (17, "panel_visual_review_loop", "Panel Visual Review Loop", "PASS"),
    (18, "surgical_panel_repair", "Surgical Panel Repair", "PASS_NO_REPAIR_REQUIRED"),
    (19, "panel_repair_gate", "Panel Repair Gate", "PASS"),
    (20, "panel_source_receipt", "Panel Source Receipt", "PASS"),
    (21, "provider_media_publication_work_order", "Provider Media Publication Work Order", "PASS_EXISTING_PUBLICATION_REUSED"),
    (22, "local_provider_media_staging", "Local Provider Media Staging", "PASS_NOT_REQUIRED_ALREADY_PUBLISHED"),
    (23, "publication_preflight", "Publication Preflight", "PASS"),
    (24, "publication_authorization", "Publication Authorization", "PASS_APPROVED"),
    (25, "public_url_probe", "Public URL Probe", "PASS"),
    (26, "provider_media_handoff", "Provider Media Handoff", "PASS"),
    (27, "provider_media_lock", "Provider Media Lock", "PASS"),
    (28, "kling_scene_packet", "Kling Scene Packet", "PASS_EXECUTED_REQUEST"),
    (29, "provider_final_gate", "Provider Final Gate", "PASS_EXECUTED_PREFLIGHT"),
    (30, "paid_call_authorization", "Paid Call Authorization", "PASS_APPROVED_CONSUMED"),
    (31, "kling_submit", "Kling Submit", "PASS_LIVE"),
    (32, "kling_poll_callback", "Kling Poll / Callback", "PASS_LIVE"),
    (33, "output_retrieval", "Output Retrieval", "PASS_LIVE"),
    (34, "ffprobe_technical_validation", "FFprobe / Technical Validation", "PASS_LIVE"),
    (35, "frame_contact_sheet", "Frame Contact Sheet", "PASS"),
    (36, "post_kling_continuity_review", "Post-Kling Continuity Review", "FAIL"),
    (37, "voice_audio_handoff", "Voice / Audio Handoff Lane When Voiced", "PASS_NOT_REQUIRED_AUDIO_OFF"),
    (38, "final_assembly_movie_lane", "Final Assembly / Movie Lane", "PASS_NOT_REQUIRED_SINGLE_PROVIDER_OUTPUT"),
    (39, "report_generation", "Report Generation", "PASS_BLOCKED_REPORT"),
    (40, "gate_validation_loop", "Gate Validation Loop", "BLOCKED"),
    (41, "upstream_revision_invalidation", "Upstream Revision Invalidation", "PASS"),
    (42, "final_acceptance_boundary", "Final Acceptance Boundary", "BLOCKED"),
]
RECONSTRUCTED_STEPS = {5, 11, 12, 15}
UPSTREAM_PASS_STEPS = {1, 2, 3, 4}
SUPERSEDED_PROVIDER_STEPS = set(range(30, 37))


class ReconstructionBlocked(RuntimeError):
    def __init__(self, code: str, *, details: Mapping[str, Any] | None = None, exit_code: int = 2) -> None:
        super().__init__(code)
        self.code = code
        self.details = dict(details or {})
        self.exit_code = exit_code


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: Mapping[str, Any] | Sequence[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


@contextmanager
def reconstruction_lock(run_root: Path) -> Iterator[None]:
    path = run_root / ".persona-dream" / "state" / "upstream_contract_reconstruction.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.mkdir()
    except FileExistsError as exc:
        raise ReconstructionBlocked("BLOCKED_UPSTREAM_RECONSTRUCTION_LOCKED", details={"path": str(path)}) from exc
    try:
        yield
    finally:
        path.rmdir()


def active_revision(run_root: Path) -> tuple[str, dict[str, Any]]:
    pointer_path = run_root / ".persona-dream" / "state" / "active_revision.json"
    if not pointer_path.is_file():
        raise ReconstructionBlocked("BLOCKED_ACTIVE_REVISION_MISSING", details={"path": str(pointer_path)})
    pointer = read_object(pointer_path)
    revision_id = str(pointer.get("revisionId") or "")
    if not revision_id:
        raise ReconstructionBlocked("BLOCKED_ACTIVE_REVISION_MISSING")
    return revision_id, pointer


def deterministic_revision_id(run_id: str, source_revision_id: str) -> str:
    payload = canonical_json_bytes(
        {
            "run_id": run_id,
            "source_revision_id": source_revision_id,
            "repair": "upstream-contract-v1",
        }
    )
    return f"rev_upstream_{hashlib.sha256(payload).hexdigest()[:12]}"


def copy_source_revision(source_root: Path, target_root: Path) -> None:
    if target_root.exists():
        raise ReconstructionBlocked("BLOCKED_UPSTREAM_TARGET_ALREADY_EXISTS", details={"path": str(target_root)})
    target_root.mkdir(parents=True)
    for child in source_root.iterdir():
        if child.name in EXCLUDED_ROOT_FILES or child.name in EXCLUDED_PHASE_DIRS:
            continue
        destination = target_root / child.name
        if child.is_dir():
            shutil.copytree(child, destination, symlinks=False)
        elif child.is_file():
            shutil.copy2(child, destination)
    for binding in target_root.rglob(BINDING_BASENAME):
        binding.unlink()


def provenance(source_revision_id: str, sources: Mapping[str, str]) -> dict[str, Any]:
    return {
        "derivation": "deterministic_reconstruction_from_accepted_revision_artifacts",
        "source_revision_id": source_revision_id,
        "source_artifact_hashes": dict(sorted(sources.items())),
        "live_selector_call": False,
        "reconstruction": True,
    }


def rewrite_identity_artifacts(
    target_root: Path,
    source_root: Path,
    *,
    run_id: str,
    revision_id: str,
    source_revision_id: str,
    created_at: str,
) -> Path:
    """Rebuild the revision-id-bearing Phase 01/02 identity artifacts.

    Content fields (idea text, residue items, contradictions, story) are exact
    copies from the source revision; only revision identity and migration
    provenance change.
    """
    source_phase01 = source_root / "phase_01_idea"
    phase01 = target_root / "phase_01_idea"
    phase02 = target_root / "phase_02_story"

    source_human = read_object(source_phase01 / "human_idea.json")
    idea_value = canonical_text(str(source_human.get("text") or ""))
    digest = idea_sha256(idea_value)
    ident = idea_id(idea_value)
    if digest != source_human.get("idea_sha256") or ident != source_human.get("idea_id"):
        raise ReconstructionBlocked("BLOCKED_SOURCE_HUMAN_IDEA_IDENTITY_MISMATCH")

    human_idea = dict(source_human)
    human_idea.update({"revision_id": revision_id, "source_revision_id": source_revision_id, "created_at": created_at})
    validate_schema(human_idea, "human_idea.v1.schema.json", phase_id="01")
    human_path = phase01 / "human_idea.json"
    write_json(human_path, human_idea)

    for name in ("dream_request.json", "residue_links.json", "contradiction_report.json"):
        value = read_object(source_phase01 / name)
        value["revision_id"] = revision_id
        if "source_revision_id" in value:
            value["source_revision_id"] = source_revision_id
        if name == "dream_request.json":
            value["created_at"] = created_at
        write_json(phase01 / name, value)

    story = read_object(source_root / "phase_02_story" / "story_contract.json")
    previous_migration = story.get("migration")
    story.update(
        {
            "revision_id": revision_id,
            "source_revision_id": source_revision_id,
            "created_at": created_at,
            "migration": {
                "kind": REPAIR_KIND,
                "authoritative_source": f"{source_revision_id}:phase_02_story/story_contract.json",
                "authoritative_source_sha256": sha256_file(source_root / "phase_02_story" / "story_contract.json"),
                "creative_regeneration_performed": False,
                "human_story_acceptance_inferred": False,
                "previous_migration": previous_migration,
            },
        }
    )
    write_json(phase02 / "story_contract.json", story)

    placeholder_manifest = {
        "schema": "persona_dream.phase_idea_lineage_manifest.v1",
        "status": "PASS_PHASE_IDEA_LINEAGE",
        "run_id": run_id,
        "revision_id": revision_id,
        "idea_id": ident,
        "idea_sha256": digest,
        "source": "explicit_human",
        "human_idea_artifact": {"relative_path": "phase_01_idea/human_idea.json", "sha256": sha256_file(human_path)},
        "phase_binding_count": 10,
        "phase_bindings": {
            phase_id: {
                "relative_path": f"phase_{phase_id}/idea_lineage_binding.json",
                "sha256": "sha256:" + "0" * 64,
                "binding_sha256": "sha256:" + "0" * 64,
            }
            for phase_id in EXPECTED_PHASE_IDS
        },
        "lineage_chain_sha256": "sha256:" + "0" * 64,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "submitted": False,
    }
    write_json(phase01 / "idea_lineage_manifest.json", placeholder_manifest)
    return human_path


def load_reconstruction_sources(source_root: Path) -> dict[str, Any]:
    request_key = "ff2ce7f310fdda2d4900bcec5767ddaef46d592e55ef3900d9384813be0a6f41"
    paths = {
        "residue_links": source_root / "phase_01_idea" / "residue_links.json",
        "contradiction_report": source_root / "phase_01_idea" / "contradiction_report.json",
        "human_idea": source_root / "phase_01_idea" / "human_idea.json",
        "story_contract": source_root / "phase_02_story" / "story_contract.json",
        "crew_contract": source_root / "phase_03_crew" / "crew_contract.json",
        "script_contract": source_root / "phase_06_script" / "script_contract.json",
        "timed_transcript": source_root / "phase_06_script" / "timed_transcript.json",
        "entity_table": source_root / "phase_06_script" / "entity_environment_script_table.json",
        "storyboard_packet": source_root / "phase_07_storyboard_live_tau" / "storyboard_packet.json",
        "post_kling_review": source_root
        / "phase_11_submit_return"
        / "provider_return"
        / request_key
        / "post_kling_continuity_review_receipt.v1.json",
    }
    values: dict[str, Any] = {}
    hashes: dict[str, str] = {}
    for key, path in paths.items():
        if not path.is_file():
            raise ReconstructionBlocked("BLOCKED_RECONSTRUCTION_SOURCE_MISSING", details={"source": key, "path": str(path)})
        values[key] = json.loads(path.read_text(encoding="utf-8"))
        hashes[str(path.relative_to(source_root))] = sha256_file(path)
    values["hashes"] = hashes
    return values


def synthesize_dream_packet(
    target_root: Path,
    sources: Mapping[str, Any],
    *,
    run_id: str,
    revision_id: str,
    source_revision_id: str,
    created_at: str,
) -> list[Path]:
    residue_items = [
        {
            "source_id": item["source_id"],
            "collection": item.get("collection", "persona_memory"),
            "persona_id": item.get("persona_id", "embry"),
            "scope": "persona-dream",
            "text": item["text"],
            "source_path": item.get("source_path"),
        }
        for item in sources["residue_links"]["items"]
    ]
    if not residue_items:
        raise ReconstructionBlocked("BLOCKED_RECONSTRUCTION_SOURCE_MISSING", details={"source": "residue_links.items"})
    residue_ids = [item["source_id"] for item in residue_items]
    idea_text = canonical_text(str(sources["human_idea"].get("text") or ""))

    dream_prompt = (
        "Synthetic dream for Embry, with Kai as the secondary persona. "
        f"The requested dream topic is: {idea_text} "
        "Memory residue gathers around Kai's annotated surf map and its hazard/etiquette rules, "
        "the minor reef scrape where Embry chose shore on her own terms, and Kai's private surf-timing "
        "correction that let her continue without self-punishment. Core tension: autonomy versus obligation "
        "- a stolen sick day that still obeys the reef, the lineup, and her own careful judgment. "
        "Render as symbolic cinematic images, not factual claims. All imagery is synthetic dream content."
    )

    contact_sheet_rel = "phase_04_contact_sheets/source_artifacts/contact_sheet_index.png"
    contact_sheet_path = target_root / contact_sheet_rel
    if not contact_sheet_path.is_file() or contact_sheet_path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
        raise ReconstructionBlocked("BLOCKED_CONTACT_SHEET_SOURCE_MISSING", details={"path": str(contact_sheet_path)})

    frame_prompts = []
    for panel in sources["storyboard_packet"]["panels"]:
        camera = panel.get("camera") or {}
        frame_prompts.append(
            {
                "frame_id": str(panel["panel_id"]),
                "prompt": (
                    f"Embry dream frame, {panel['panel_id']}: {canonical_text(str(panel.get('action') or ''))} "
                    f"Camera: {camera.get('shot_code', 'MS')}, {camera.get('lens', 'water-housing perspective')}, "
                    f"{camera.get('movement', 'slow drift with the swell')}. Waterline Kahalu'u Bay, lava reef, "
                    "continuous daylight, synthetic dream still."
                ),
                "negative_prompt": "wide establishing shot, crowd lineup shot, distant silhouettes, back-facing two-shot, watermark, UI screenshot",
                "source_ids": residue_ids,
                "synthetic": True,
                "time_range_s": panel.get("time_range"),
            }
        )

    packet = {
        "schema": "persona_dream.packet.v1",
        "run_id": run_id,
        "revision_id": revision_id,
        "mode": "video_plan",
        "persona": {"id": "embry", "display_name": "Embry"},
        "secondary_persona": {"id": "kai", "display_name": "Kai"},
        "about": idea_text,
        "residue_items": residue_items,
        "contradictions": sources["contradiction_report"].get("contradictions", []),
        "dream_prompt": dream_prompt,
        "frame_prompts": frame_prompts,
        "contact_sheet": contact_sheet_rel,
        "reflection": (
            "I woke with the surf map, the reef scrape, and Kai's quiet timing correction still arranged "
            "like images rather than answers. The dream stayed synthetic but kept its source traces intact: "
            f"{len(residue_items)} memory residues and {len(sources['contradiction_report'].get('contradictions', []))} "
            "explicit tensions. The stolen sick day still had rules, and choosing carefully was the whole rebellion. "
            "Treat this as a reflective lead, not as evidence or a durable identity change."
        ),
        "synthetic": True,
        "created_at": created_at,
        "provenance": provenance(
            source_revision_id,
            {
                key: value
                for key, value in sources["hashes"].items()
                if key.startswith(("phase_01_idea/", "phase_02_story/", "phase_07_storyboard_live_tau/storyboard_packet"))
            },
        ),
        "claims": {
            "proves": [
                "a canonical dream packet exists for this revision, grounded in the exact recalled residue items",
                "frame prompts are bound one-to-one to the four accepted storyboard beats",
            ],
            "does_not_prove": [
                "a new live memory recall was executed during reconstruction",
                "story acceptance, panel generation, or provider readiness",
            ],
        },
        "actual_provider_call_attempts": 0,
        "provider_live": False,
    }
    packet_path = target_root / "phase_01_idea" / "dream_packet.json"
    write_json(packet_path, packet)
    prompt_path = target_root / "phase_01_idea" / "dream_prompt.txt"
    prompt_path.write_text(dream_prompt + "\n", encoding="utf-8")

    validation = validate_dream_packet(packet_path, run_root=target_root)
    if validation.get("status") == "BLOCKED":
        raise ReconstructionBlocked("BLOCKED_DREAM_PACKET_VALIDATION", details=validation.get("first_blocker") or {})
    write_json(target_root / "phase_01_idea" / "dream_packet_validation.json", validation)
    return [packet_path, prompt_path]


def synthesize_look_lock_and_script_dna(
    target_root: Path,
    sources: Mapping[str, Any],
    *,
    run_id: str,
    revision_id: str,
    source_revision_id: str,
    created_at: str,
) -> list[Path]:
    packet = sources["storyboard_packet"]
    camera_contract = packet["camera_contract"]
    panels = packet["panels"]
    kai_line = next(
        (
            str(entry.get("text") or "")
            for entry in sources["timed_transcript"]
            if entry.get("speaker") == "Kai"
        ),
        "",
    )

    look_lock = {
        "camera_format": "digital cinema camera in surf water housing, waterline operation, 1280x720 target delivery",
        "lens": canonical_text(str(camera_contract.get("lens_language") or "")),
        "lighting": "natural hard June mid-day Hawaiian sunlight, silver glare on the wave face, no artificial fill",
        "color_grade": "warm natural daylight grade with golden highlights, clean turquoise water, true-to-skin tones",
        "atmosphere_texture": "salt spray, heat shimmer, sweat sheen on skin, sun-softened surfboard wax",
        "composition": "; ".join(str(item) for item in camera_contract.get("framing", [])),
        "motion_rules": (
            "slow observational drift with the swell; small handheld corrections at the board rail; "
            "gentle lateral drift keeping Kai outside the decision point; one brief forward glide with the "
            "wave shoulder in the final beat; no dramatic push-ins"
        ),
        "continuity_rule": (
            "Embry in navy rashguard and Kai in black rashguard on two white shortboards at Kahalu'u Bay; "
            "lava reef readable in the lower foreground; safe channel geometry visible in the final beat; "
            "each required face at least 80px and never back-only; continuous daylight; no unrelated "
            "foreground people"
        ),
    }

    shot_plan = []
    for index, panel in enumerate(panels, start=1):
        camera = panel.get("camera") or {}
        shot_plan.append(
            {
                "shot_number": index,
                "panel_id": panel["panel_id"],
                "framing": f"{camera.get('shot_code', 'MS')} - {canonical_text(str(camera.get('composition') or ''))}",
                "camera_movement": canonical_text(str(camera.get("movement") or "")),
                "action": canonical_text(str(panel.get("action") or "")),
                "focus_target": "Embry and Kai identity readability first, reef and channel geometry second",
                "continuity_reminder": (
                    "navy/black rashguards, two white shortboards, waterline height, lava reef in lower "
                    "foreground, continuous daylight"
                ),
                "time_range_s": panel.get("time_range"),
            }
        )

    script_dna = {
        "primary_mode": "quiet procedural naturalism",
        "influences_as_techniques": [
            "restraint-first blocking instead of dialogue exposition",
            "competence shown through physical micro-corrections",
            "environmental clock pressure from set waves instead of verbal deadlines",
            "nonverbal cue-and-consent beats between equals",
        ],
        "scene_engine": "a stolen sick day still obeys local rules: wait, read the water, then commit",
        "dialogue_style": (
            "near-silent; at most one quiet practical line from Kai "
            f"(canonical line: {json.dumps(kai_line)}); no banter, no exposition"
        ),
        "conflict_pattern": "autonomy versus obligation, mediated by surf etiquette and the lava-reef hazard",
        "structure": "four-beat ten-second arc: shared restraint, physical strain, read-and-cue, Embry-only commit",
        "theme": "earned autonomy: choosing carefully is the rebellion",
        "beat_rules": [
            "each beat contains one visible physical micro-correction",
            "Kai never takes over Embry's decision",
            "the final beat must show an unmistakable Embry-only forward commit through the safe channel",
            "the lava-reef boundary and safe-channel geometry must remain visually readable in the final beat",
        ],
        "do_not_use": [
            "spoken exposition",
            "melodrama",
        ]
        + [str(item) for item in camera_contract.get("forbidden_shot_types", [])],
    }

    technique_selection = {
        "schema": "persona_dream.technique_selection.v1",
        "skill": "cinematic_technique_selector",
        "version": "1.0.0",
        "mode": "technique_and_script_selection",
        "run_id": run_id,
        "revision_id": revision_id,
        "created_at": created_at,
        "user_intent_summary": canonical_text(str(sources["story_contract"].get("story") or "")),
        "inferred_context": {
            "genre": "grounded slice-of-life surf drama",
            "mood": ["restrained", "sun-drenched", "quietly rebellious", "competent"],
            "location_type": "public reef break, Kahalu'u Bay, Kona Coast, Big Island",
            "time_of_day": "June mid-day with hard glare",
            "realism_level": "photoreal naturalism, no stylization",
            "shot_count": len(panels),
            "duration_seconds": sources["story_contract"].get("target_duration_s", 10),
            "aspect_ratio": "16:9",
            "subject": "Embry and Kai surfing on a faked sick day",
            "era": "June 2024",
        },
        "visual_strategy": {
            "primary_visual_dna": "waterline surf-documentary realism with identity-readable faces",
            "trait_translation": [
                "restraint reads as slow observational drift, never a push-in",
                "hazard reads as lava reef shapes in the lower foreground",
                "autonomy reads as Embry alone entering the safe channel in the final beat",
                "heat reads as glare, sweat sheen, and softened wax texture",
            ],
            "rationale": (
                "The accepted storyboard, camera contract, and script contract already encode a waterline "
                "surf-documentary look with strict identity readability targets; this selection locks that "
                "language so a repaired SB_004 request and any regenerated downstream artifact inherit one "
                "stable visual grammar."
            ),
        },
        "look_lock": look_lock,
        "script_dna": script_dna,
        "shot_plan": shot_plan,
        "continuity_lock": [
            "Embry: young woman, navy rashguard, white performance shortboard with sun-softened wax",
            "Kai: young man, black rashguard, well-used white shortboard",
            "environment: Kahalu'u Bay waterline, lava reef lower foreground, safe channel, June swell, continuous daylight",
            "identity: each required face at least 80px, never back-only, no unrelated foreground people",
            "audio: silent contract, generate_audio=false, nonverbal cues only",
        ],
        "negative_constraints": [str(item) for item in camera_contract.get("forbidden_shot_types", [])]
        + ["night or golden-hour relighting", "artificial studio lighting", "added crowds or extra foreground surfers"],
        "composer_notes": [
            "map look_lock into the Kling cinematography control matrix before composing provider prompts",
            "the SB_004 repair prompt must add an unmistakable Embry-only forward commit and a readable "
            "lava-reef boundary without changing wardrobe, boards, identity bindings, or the silent-audio contract",
            "keep every provider prompt at or under 512 characters per multi_prompt entry",
        ],
        "provenance": provenance(
            source_revision_id,
            {
                key: value
                for key, value in sources["hashes"].items()
                if key.startswith(("phase_02_story/", "phase_03_crew/", "phase_06_script/", "phase_07_storyboard_live_tau/storyboard_packet"))
            },
        ),
        "claims": {
            "proves": [
                "a canonical Look Lock and Script DNA exist for this revision, derived from the accepted "
                "story, crew, script, and storyboard artifacts",
            ],
            "does_not_prove": [
                "a new live cinematic-technique-selector model call was executed",
                "downstream storyboard or provider artifacts were regenerated against this selection",
            ],
        },
        "mocked": False,
        "live": False,
        "actual_provider_call_attempts": 0,
    }

    schema = json.loads((SCHEMA_ROOT / "cinematic_technique_selection.v1.schema.json").read_text(encoding="utf-8"))
    errors = pydantic_error_messages(schema, technique_selection) + [error.message for error in Draft202012Validator(schema).iter_errors(technique_selection)]
    if errors:
        raise ReconstructionBlocked("BLOCKED_TECHNIQUE_SELECTION_SCHEMA", details={"errors": errors})

    crew_dir = target_root / "phase_03_crew"
    technique_path = crew_dir / "technique_selection.json"
    write_json(technique_path, technique_selection)

    look_lock_value = {
        "schema": "persona_dream.look_lock.v1",
        "run_id": run_id,
        "revision_id": revision_id,
        "created_at": created_at,
        "look_lock": look_lock,
        "source_technique_selection": "phase_03_crew/technique_selection.json",
        "provenance": technique_selection["provenance"],
        "claims": technique_selection["claims"],
    }
    look_lock_path = crew_dir / "look_lock.json"
    write_json(look_lock_path, look_lock_value)

    shot_bible = {
        "schema": "persona_dream.shot_bible.v1",
        "run_id": run_id,
        "revision_id": revision_id,
        "created_at": created_at,
        "look_lock": look_lock,
        "shots": shot_plan,
        "identity_readability_targets": camera_contract.get("identity_readability_targets", {}),
        "forbidden_shot_types": camera_contract.get("forbidden_shot_types", []),
        "provenance": technique_selection["provenance"],
        "claims": technique_selection["claims"],
    }
    shot_bible_path = crew_dir / "shot_bible.json"
    write_json(shot_bible_path, shot_bible)

    script_dna_value = {
        "schema": "persona_dream.script_dna_selection.v1",
        "run_id": run_id,
        "revision_id": revision_id,
        "created_at": created_at,
        "script_dna": script_dna,
        "source_technique_selection": "phase_03_crew/technique_selection.json",
        "provenance": provenance(
            source_revision_id,
            {
                key: value
                for key, value in sources["hashes"].items()
                if key.startswith(("phase_02_story/", "phase_06_script/"))
            },
        ),
        "claims": technique_selection["claims"],
    }
    dna_schema = json.loads((SCHEMA_ROOT / "cinematic_script_dna.v1.schema.json").read_text(encoding="utf-8"))
    dna_errors = pydantic_error_messages(dna_schema, script_dna_value) + [error.message for error in Draft202012Validator(dna_schema).iter_errors(script_dna_value)]
    if dna_errors:
        raise ReconstructionBlocked("BLOCKED_SCRIPT_DNA_SCHEMA", details={"errors": dna_errors})
    script_dna_path = crew_dir / "script_dna_selection.json"
    write_json(script_dna_path, script_dna_value)

    return [technique_path, look_lock_path, shot_bible_path, script_dna_path]


def synthesize_panel_ledger(
    target_root: Path,
    sources: Mapping[str, Any],
    *,
    run_id: str,
    revision_id: str,
    source_revision_id: str,
    created_at: str,
) -> Path:
    packet = sources["storyboard_packet"]
    entity_table = sources["entity_table"]
    review = sources["post_kling_review"]
    behaviors_by_entity = {
        str(row.get("entity") or ""): canonical_text(str(row.get("environment_interaction") or ""))
        for row in entity_table
        if isinstance(row, Mapping)
    }

    props_by_panel = {
        "sb_001": ["embry_white_shortboard", "kai_white_shortboard", "navy_rashguard", "black_rashguard"],
        "sb_002": ["embry_white_shortboard", "sun_softened_wax", "navy_rashguard", "phone_in_beach_bag"],
        "sb_003": ["kai_white_shortboard", "black_rashguard", "embry_white_shortboard"],
        "sb_004": ["embry_white_shortboard", "navy_rashguard", "wave_shoulder"],
    }
    sb004_findings = [str(item.get("code") or "") for item in review.get("blocking_findings", [])]

    records = []
    for panel in packet["panels"]:
        panel_id = str(panel["panel_id"])
        end_frame = panel.get("end_frame") or {}
        accepted = end_frame.get("accepted_frame") or {}
        identity_review = accepted.get("identity_continuity_review") or {}
        record: dict[str, Any] = {
            "panel": panel_id,
            "time_range_s": panel.get("time_range"),
            "required_visible_entities": identity_review.get("required_entities", ["Embry", "Kai"]),
            "required_props": props_by_panel.get(panel_id, []),
            "required_environment": ["kahaluu_bay_waterline", "lava_reef_lower_foreground", "june_swell", "continuous_daylight"],
            "required_dynamic_behaviors": [
                behavior
                for behavior in (
                    behaviors_by_entity.get("Embry", ""),
                    behaviors_by_entity.get("Kai", ""),
                    behaviors_by_entity.get("June Swell", ""),
                    behaviors_by_entity.get("Lava Reef", ""),
                )
                if behavior
            ],
            "acting_beats": panel.get("acting_beats", []),
            "visual_review_status": str(identity_review.get("status") or "UNKNOWN"),
            "visual_review_receipt": identity_review.get("receipt"),
            "visible_entities": identity_review.get("visible_entities", []),
            "failed_requirements": [],
            "repair_action": None,
            "repair_attempt": 0,
        }
        if panel_id == "sb_004":
            record["required_dynamic_behaviors"] = record["required_dynamic_behaviors"] + [
                "Embry alone commits forward through the safe channel while Kai remains outside the main action",
                "the lava-reef boundary and safe-channel geometry stay visually readable through the final beat",
            ]
            record["downstream_provider_findings"] = {
                "source": f"{source_revision_id}:phase_11_submit_return post-Kling continuity review",
                "receipt_sha256": sources["hashes"][
                    "phase_11_submit_return/provider_return/"
                    "ff2ce7f310fdda2d4900bcec5767ddaef46d592e55ef3900d9384813be0a6f41/"
                    "post_kling_continuity_review_receipt.v1.json"
                ],
                "codes": sb004_findings,
                "note": (
                    "the accepted panel passed storyboard visual review, but the provider return failed the "
                    "final-beat commit action and reef readability; the repaired SB_004 provider request must "
                    "encode these dynamic-behavior requirements explicitly"
                ),
            }
            record["repair_action"] = "compile_repaired_sb_004_provider_request_with_stronger_final_action_constraint"
        records.append(record)

    ledger = {
        "schema": "persona_dream.panel_continuity_and_repair_ledger.v1",
        "run_id": run_id,
        "revision_id": revision_id,
        "created_at": created_at,
        "panel_count": len(records),
        "panels": records,
        "review_status_source": "phase_07_storyboard_live_tau/storyboard_packet.json accepted-frame identity reviews",
        "provenance": provenance(
            source_revision_id,
            {
                key: value
                for key, value in sources["hashes"].items()
                if key.startswith(("phase_06_script/entity", "phase_07_storyboard_live_tau/storyboard_packet", "phase_11_submit_return/"))
            },
        ),
        "claims": {
            "proves": [
                "a consolidated panel continuity and repair ledger exists for this revision, bound to the "
                "accepted panel reviews and the exact provider-return findings",
            ],
            "does_not_prove": [
                "a new panel visual review was executed during reconstruction",
                "the repaired SB_004 provider request exists or is authorized",
            ],
        },
        "mocked": False,
        "live": False,
        "actual_provider_call_attempts": 0,
    }
    if any(str(record["visual_review_status"]) != "PASS" for record in records):
        raise ReconstructionBlocked(
            "BLOCKED_PANEL_LEDGER_REVIEW_STATUS",
            details={"statuses": {record["panel"]: record["visual_review_status"] for record in records}},
        )
    path = target_root / "phase_07_storyboard_live_tau" / "panel_continuity_and_repair_ledger.json"
    write_json(path, ledger)
    return path


def step_dispositions() -> dict[int, dict[str, str]]:
    dispositions: dict[int, dict[str, str]] = {}
    for number, slug, name, previous_status in STEP_TABLE:
        if number in UPSTREAM_PASS_STEPS:
            status, disposition, action = previous_status, "carried_current", "none; identity artifacts rebound byte-compatibly to this revision"
        elif number in RECONSTRUCTED_STEPS:
            status, disposition, action = "PASS_RECONSTRUCTED", "reconstructed_current", "none; canonical artifact produced and validated in this revision"
        elif number == 41:
            status, disposition, action = "PASS", "current", "none; this revision's invalidation ledger is the step artifact"
        elif number == 42:
            status, disposition, action = (
                "BLOCKED_AWAITING_DOWNSTREAM_REVALIDATION",
                "blocked",
                "final acceptance requires steps 06-29 revalidation, a repaired SB_004 request, new authorization, and a passing post-Kling continuity review",
            )
        elif number in SUPERSEDED_PROVIDER_STEPS:
            status, disposition, action = (
                "SUPERSEDED_PROVIDER_EVIDENCE_PRIOR_REVISION",
                "superseded",
                "provider evidence remains bound to the prior revision and consumed request hash; a repaired request, new hash-bound approvals, and a new paid-call authorization are required",
            )
        else:
            status, disposition, action = (
                "STALE_UPSTREAM_CONTRACT_SUPERSEDED",
                "stale",
                "hash-revalidate or regenerate against the new upstream contract artifacts in dependency order before reuse",
            )
        dispositions[number] = {
            "step_slug": slug,
            "step_name": name,
            "previous_status": previous_status,
            "status": status,
            "disposition": disposition,
            "required_action": action,
        }
    return dispositions


def write_invalidation_ledger(
    target_root: Path,
    new_files: Mapping[str, str],
    dispositions: Mapping[int, Mapping[str, str]],
    *,
    run_id: str,
    revision_id: str,
    source_revision_id: str,
    created_at: str,
) -> Path:
    entries = [
        {
            "step_no": number,
            **dispositions[number],
        }
        for number in sorted(dispositions)
        if number >= 6
    ]
    ledger = {
        "schema": "persona_dream.upstream_invalidation_ledger.v1",
        "run_id": run_id,
        "revision_id": revision_id,
        "source_revision_id": source_revision_id,
        "created_at": created_at,
        "changed_upstream_artifacts": dict(sorted(new_files.items())),
        "affected_steps": entries,
        "rule": (
            "no downstream artifact in this revision may be claimed current until it is hash-revalidated or "
            "regenerated against the changed upstream artifacts; provider evidence from the prior revision is "
            "superseded, not reusable"
        ),
        "claims": {
            "proves": ["every affected downstream step 06-42 has an explicit stale, superseded, blocked, or revalidated disposition"],
            "does_not_prove": ["any downstream artifact has been revalidated yet"],
        },
    }
    path = target_root / LEDGER_NAME
    write_json(path, ledger)
    return path


def build_step_records(
    target_root: Path,
    dispositions: Mapping[int, Mapping[str, str]],
    step_paths: Mapping[int, list[str]],
    *,
    run_id: str,
    revision_id: str,
    source_revision_id: str,
    created_at: str,
) -> Path:
    documents = []
    for number in sorted(dispositions):
        entry = dispositions[number]
        paths = step_paths.get(number, [])
        hashes: dict[str, str] = {}
        for relative in paths:
            path = target_root / relative
            if not path.is_file():
                raise ReconstructionBlocked(
                    "BLOCKED_STEP_EVIDENCE_MISSING",
                    details={"step_no": number, "path": str(path)},
                )
            hashes[relative] = sha256_file(path)
        blocked = entry["status"].startswith(("BLOCKED", "STALE", "SUPERSEDED"))
        documents.append(
            {
                "_key": f"persona_dream:{run_id}:{revision_id}:{number:02d}:{entry['step_slug']}",
                "schema": "persona_dream.pipeline_step_memory.v1",
                "run_id": run_id,
                "revision_id": revision_id,
                "source_revision_id": source_revision_id,
                "step_no": number,
                "step_slug": entry["step_slug"],
                "step_name": entry["step_name"],
                "status": entry["status"],
                "disposition": entry["disposition"],
                "previous_status_in_source_revision": entry["previous_status"],
                "inputs": {"source_revision_id": source_revision_id, "repair_kind": REPAIR_KIND},
                "outputs": paths,
                "receipt_paths": [path for path in paths if path.endswith(".json")],
                "artifact_hashes": hashes,
                "request_hash": None,
                "provider_task_id": None,
                "memory_write_method": "/upsert",
                "claims": {
                    "proves": [f"step {number:02d} state for revision {revision_id} is durably recorded"],
                    "does_not_prove": ["downstream revalidation, provider readiness, or final acceptance"],
                },
                "blocker": entry["required_action"] if blocked else None,
                "observed_at": created_at,
                "retrieval_text": (
                    f"Persona Dream {run_id} {revision_id} step {number:02d} {entry['step_name']} "
                    f"status {entry['status']} disposition {entry['disposition']}"
                ),
                "tags": [
                    "persona-dream",
                    f"run:{run_id}",
                    f"revision:{revision_id}",
                    f"step:{number:02d}",
                    f"status:{entry['status'].lower()}",
                    f"disposition:{entry['disposition']}",
                ],
            }
        )
    bundle = {
        "schema": "persona_dream.pipeline_step_memory_bundle.v1",
        "run_id": run_id,
        "revision_id": revision_id,
        "collection": STEP_COLLECTION,
        "count": len(documents),
        "documents": documents,
    }
    path = target_root / STEP_BUNDLE_NAME
    write_json(path, bundle)
    return path


def write_gate_summary(
    target_root: Path,
    dispositions: Mapping[int, Mapping[str, str]],
    new_files: Mapping[str, str],
    *,
    run_id: str,
    revision_id: str,
    source_revision_id: str,
    created_at: str,
) -> Path:
    passing = sorted(
        number
        for number, entry in dispositions.items()
        if not entry["status"].startswith(("BLOCKED", "STALE", "SUPERSEDED", "FAIL"))
    )
    stale = sorted(number for number, entry in dispositions.items() if entry["disposition"] in {"stale", "superseded"})
    blocked = sorted(number for number, entry in dispositions.items() if entry["disposition"] == "blocked")
    summary = {
        "schema": "persona_dream.upstream_reconstruction_gate_summary.v1",
        "status": "PASS_UPSTREAM_CONTRACT_RECONSTRUCTION",
        "run_id": run_id,
        "revision_id": revision_id,
        "source_revision_id": source_revision_id,
        "created_at": created_at,
        "reconstructed_steps_passing": sorted(RECONSTRUCTED_STEPS),
        "reconstructed_artifacts": dict(sorted(new_files.items())),
        "counts": {
            "total": len(dispositions),
            "passing_or_current": len(passing),
            "stale_or_superseded": len(stale),
            "blocked": len(blocked),
        },
        "passing_steps": passing,
        "stale_or_superseded_steps": stale,
        "blocked_steps": blocked,
        "no_downstream_artifact_silently_current": True,
        "invalidation_ledger": LEDGER_NAME,
        "step_record_bundle": STEP_BUNDLE_NAME,
        "memory_persistence": {
            "collection": STEP_COLLECTION,
            "expected_count": len(dispositions),
            "receipt_location": (
                ".persona-dream/state/pipeline_step_memory_receipt_" + revision_id + ".json "
                "(outside the frozen revision artifact set)"
            ),
        },
        "next_gate": (
            "regenerate or hash-revalidate steps 06-29 in dependency order, compile a repaired SB_004 request, "
            "fix its hash, initialize an unused attempt ledger, and stop at step 30 awaiting human hash-bound "
            "paid-call authorization"
        ),
        "mocked": False,
        "live": False,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "submitted": False,
    }
    path = target_root / GATE_SUMMARY_NAME
    write_json(path, summary)
    return path


def write_queue_contract(run_root: Path, source_revision_id: str, target_revision_id: str, created_at: str) -> str:
    digest = hashlib.sha256(
        canonical_json_bytes(
            {
                "run_id": run_root.name,
                "source": source_revision_id,
                "target": target_revision_id,
                "repair": REPAIR_KIND,
            }
        )
    ).hexdigest()
    work_order_id = f"repair-{digest[:16]}"
    work_order = {
        "schemaVersion": "persona_dream.repair_work_order.v1",
        "workOrderId": work_order_id,
        "dedupKey": digest,
        "runId": run_root.name,
        "runRoot": str(run_root.resolve()),
        "sourceRevisionId": source_revision_id,
        "targetRevisionId": target_revision_id,
        "createdAt": created_at,
        "detection": {
            "earliestStalePhase": "01",
            "selectedThroughPhase": "10",
            "phaseRange": list(EXPECTED_PHASE_IDS),
            "reasons": [{"phaseId": "01", "code": "BLOCKED_UPSTREAM_CONTRACT_ARTIFACTS_MISSING"}],
        },
        "policy": {
            "maxAttemptsPerPhase": 1,
            "forbiddenSideEffects": [
                "external_network",
                "public_media_publication",
                "paid_provider_call",
                "provider_submission",
                "human_acceptance_fabrication",
            ],
            "stopBeforePhase": "11",
        },
        "status": "REQUESTED",
    }
    work_path = run_root / ".persona-dream" / "repair" / "work-orders" / f"{work_order_id}.json"
    queue_path = run_root / ".persona-dream" / "repair" / "tau-queue" / f"{work_order_id}.json"
    write_json(work_path, work_order)
    write_json(queue_path, {
        "schemaVersion": "persona_dream.tau_repair_queue_item.v1",
        "status": "QUEUED",
        "queuedAt": created_at,
        "workOrderPath": str(work_path.resolve()),
        "workOrder": work_order,
    })
    return work_order_id


def step_evidence_paths(new_files: Mapping[str, str]) -> dict[int, list[str]]:
    paths: dict[int, list[str]] = {
        1: ["phase_01_idea/dream_request.json", "phase_01_idea/human_idea.json"],
        2: ["phase_01_idea/dream_request.json", "phase_01_idea/human_idea.json"],
        3: ["phase_01_idea/residue_links.json"],
        4: ["phase_01_idea/residue_links.json", "phase_01_idea/contradiction_report.json"],
        5: ["phase_01_idea/dream_packet.json", "phase_01_idea/dream_prompt.txt", "phase_01_idea/dream_packet_validation.json"],
        11: ["phase_03_crew/technique_selection.json", "phase_03_crew/look_lock.json", "phase_03_crew/shot_bible.json"],
        12: ["phase_03_crew/script_dna_selection.json"],
        15: ["phase_07_storyboard_live_tau/panel_continuity_and_repair_ledger.json"],
        41: [LEDGER_NAME],
        42: [GATE_SUMMARY_NAME],
    }
    for number, _slug, _name, _previous in STEP_TABLE:
        paths.setdefault(number, [LEDGER_NAME])
    return paths


def reconstruct(args: argparse.Namespace) -> dict[str, Any]:
    run_root = args.run_root.expanduser().resolve(strict=True)
    run_id = run_root.name
    source_revision_id, _pointer = active_revision(run_root)
    if args.source_revision_id and args.source_revision_id != source_revision_id:
        raise ReconstructionBlocked(
            "BLOCKED_UPSTREAM_SOURCE_REVISION_CHANGED",
            details={"active_revision_id": source_revision_id, "requested": args.source_revision_id},
        )
    source_root = run_root / ".persona-dream" / "revisions" / source_revision_id
    if not source_root.is_dir():
        raise ReconstructionBlocked("BLOCKED_SOURCE_REVISION_MISSING", details={"path": str(source_root)})

    created_at = args.created_at or utc_now()
    target_revision_id = args.target_revision_id or deterministic_revision_id(run_id, source_revision_id)
    target_root = run_root / ".persona-dream" / "revisions" / target_revision_id

    with reconstruction_lock(run_root):
        copy_source_revision(source_root, target_root)
        try:
            human_path = rewrite_identity_artifacts(
                target_root,
                source_root,
                run_id=run_id,
                revision_id=target_revision_id,
                source_revision_id=source_revision_id,
                created_at=created_at,
            )
            sources = load_reconstruction_sources(source_root)
            new_paths: list[Path] = []
            new_paths += synthesize_dream_packet(
                target_root, sources,
                run_id=run_id, revision_id=target_revision_id,
                source_revision_id=source_revision_id, created_at=created_at,
            )
            new_paths += synthesize_look_lock_and_script_dna(
                target_root, sources,
                run_id=run_id, revision_id=target_revision_id,
                source_revision_id=source_revision_id, created_at=created_at,
            )
            new_paths.append(
                synthesize_panel_ledger(
                    target_root, sources,
                    run_id=run_id, revision_id=target_revision_id,
                    source_revision_id=source_revision_id, created_at=created_at,
                )
            )
            new_files = {str(path.relative_to(target_root)): sha256_file(path) for path in new_paths}

            dispositions = step_dispositions()
            write_invalidation_ledger(
                target_root, new_files, dispositions,
                run_id=run_id, revision_id=target_revision_id,
                source_revision_id=source_revision_id, created_at=created_at,
            )
            write_gate_summary(
                target_root, dispositions, new_files,
                run_id=run_id, revision_id=target_revision_id,
                source_revision_id=source_revision_id, created_at=created_at,
            )
            build_step_records(
                target_root, dispositions, step_evidence_paths(new_files),
                run_id=run_id, revision_id=target_revision_id,
                source_revision_id=source_revision_id, created_at=created_at,
            )

            manifest_path = target_root / "revision_manifest.json"
            write_json(
                manifest_path,
                {
                    "schema": "persona_dream.revision_manifest.v1",
                    "status": "FROZEN_ALL_LOCAL_GATES_PASS",
                    "runId": run_id,
                    "revisionId": target_revision_id,
                    "sourceRevisionId": source_revision_id,
                    "sourceCommit": args.source_commit,
                    "createdAt": created_at,
                    "repairKind": REPAIR_KIND,
                    "ideaId": idea_id(canonical_text(str(sources["human_idea"].get("text") or ""))),
                    "ideaSha256": idea_sha256(canonical_text(str(sources["human_idea"].get("text") or ""))),
                    "reconstructedArtifacts": dict(sorted(new_files.items())),
                    "actual_provider_call_attempts": 0,
                    "provider_live": False,
                    "provider_ready": False,
                    "live_submit_ready": False,
                    "submitted": False,
                },
            )
            index_path = target_root / "revision_artifact_index.json"
            provisional_index = write_index(target_root, index_path, run_id, target_revision_id)
            human_idea = read_object(human_path)
            bindings, binding_paths = build_phase_bindings(target_root, provisional_index, human_idea)
            for phase_id in EXPECTED_PHASE_IDS:
                write_json(binding_paths[phase_id], bindings[phase_id])
            lineage_manifest = build_lineage_manifest(target_root, human_path, human_idea, bindings, binding_paths)
            validate_schema(lineage_manifest, "phase_idea_lineage_manifest.v1.schema.json", phase_id="01")
            write_json(target_root / "phase_01_idea" / "idea_lineage_manifest.json", lineage_manifest)
            final_index = write_index(target_root, index_path, run_id, target_revision_id)
            lineage = validate_revision_idea_lineage(target_root, run_id, target_revision_id, final_index)

            qargs = argparse.Namespace(
                run_root=args.run_root,
                revision_id=target_revision_id,
                source_commit=args.source_commit,
                memory_url=args.memory_url,
                collection=args.collection,
                connect_timeout=args.connect_timeout,
                read_timeout=args.read_timeout,
                test_fixture=args.test_fixture,
                command="prepare",
            )
            prepare_receipt = prepare(qargs)
            qargs.command = "verify"
            verify_receipt = verify(qargs)

            work_order_id = write_queue_contract(run_root, source_revision_id, target_revision_id, created_at)
            pointer_path = run_root / ".persona-dream" / "state" / "active_revision.json"
            atomic_write_json(
                pointer_path,
                {
                    "schemaVersion": "persona_dream.active_revision_pointer.v1",
                    "runId": run_id,
                    "revisionId": target_revision_id,
                    "revisionRoot": str(target_root.resolve()),
                    "revisionManifestSha256": sha256_file(manifest_path),
                    "ideaId": lineage.idea_id,
                    "ideaSha256": lineage.idea_sha256,
                },
            )
            activation_args = argparse.Namespace(
                run_root=args.run_root,
                revision_id=target_revision_id,
                source_commit=args.source_commit,
                memory_url=args.memory_url,
                collection=args.collection,
                connect_timeout=args.connect_timeout,
                read_timeout=args.read_timeout,
                test_fixture=args.test_fixture,
            )
            activation_receipt = activate(activation_args)
            activation_path = target_root / "revision_activation_receipt.json"
            if activation_receipt.get("status") != "PASS_ACTIVE_CONSISTENT" or not activation_path.is_file():
                raise ReconstructionBlocked("BLOCKED_UPSTREAM_RECONSTRUCTION_ACTIVATION_FAILED")

            receipt = {
                "schema": "persona_dream.upstream_contract_reconstruction_receipt.v1",
                "status": "PASS_UPSTREAM_CONTRACT_RECONSTRUCTION_ACTIVE",
                "run_id": run_id,
                "source_revision_id": source_revision_id,
                "target_revision_id": target_revision_id,
                "work_order_id": work_order_id,
                "repair_kind": REPAIR_KIND,
                "reconstructed_artifacts": dict(sorted(new_files.items())),
                "invalidation_ledger": LEDGER_NAME,
                "gate_summary": GATE_SUMMARY_NAME,
                "step_record_bundle": STEP_BUNDLE_NAME,
                "artifact_index_sha256": sha256_file(index_path),
                "revision_manifest_sha256": sha256_file(manifest_path),
                "memory_prepare_status": prepare_receipt.get("status"),
                "memory_verify_status": verify_receipt.get("status"),
                "activation_status": activation_receipt.get("status"),
                "phase_lineage_passed_count": lineage.phase_binding_count,
                "phase_lineage_expected_count": 10,
                "provider_live": False,
                "provider_ready": False,
                "live_submit_ready": False,
                "submitted": False,
                "actual_provider_call_attempts": 0,
                "mocked": bool(args.test_fixture),
                "live": not bool(args.test_fixture),
                "observed_at": utc_now(),
            }
            receipt_path = (
                run_root
                / ".persona-dream"
                / "state"
                / f"upstream_contract_reconstruction_receipt_{target_revision_id}.json"
            )
            write_json(receipt_path, receipt)
            receipt["receipt_path"] = str(receipt_path)
            return receipt
        except Exception:
            activation_started = (target_root / "revision_activation_receipt.json").exists()
            if not activation_started and not (target_root / "revision_memory_prepare_receipt.json").exists():
                shutil.rmtree(target_root, ignore_errors=True)
            raise


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--run-root", type=Path, required=True)
    value.add_argument("--source-revision-id")
    value.add_argument("--target-revision-id")
    value.add_argument("--created-at", help="ISO-8601 timestamp for deterministic replay")
    value.add_argument("--source-commit", required=True)
    value.add_argument("--memory-url", default="http://127.0.0.1:8601")
    value.add_argument("--collection", default="project_knowledge")
    value.add_argument("--connect-timeout", type=float, default=5.0)
    value.add_argument("--read-timeout", type=float, default=60.0)
    value.add_argument("--test-fixture", action="store_true", help=argparse.SUPPRESS)
    value.add_argument("--json", action="store_true")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = reconstruct(args)
    except (ReconstructionBlocked, GateBlocked, IdeaLineageError) as exc:
        code = getattr(exc, "code", "BLOCKED_UPSTREAM_CONTRACT_RECONSTRUCTION")
        output = {
            "schema": "persona_dream.upstream_contract_reconstruction_error.v1",
            "status": code,
            "details": getattr(exc, "details", {}),
            "actual_provider_call_attempts": 0,
            "provider_live": False,
            "provider_ready": False,
            "live_submit_ready": False,
            "submitted": False,
            "mocked": bool(args.test_fixture),
            "live": False,
        }
        print(json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False))
        return int(getattr(exc, "exit_code", 2))
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) if args.json else result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
