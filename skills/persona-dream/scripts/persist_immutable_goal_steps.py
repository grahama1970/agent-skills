#!/usr/bin/env python3
"""Persist the 42-step immutable-goal audit for one persona-dream revision."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


RUN_ID = "pipeline-complete"
REVISION_ID = "rev_idea_f3f9c48d5cc2"
REQUEST_KEY = "ff2ce7f310fdda2d4900bcec5767ddaef46d592e55ef3900d9384813be0a6f41"
REQUEST_SHA = f"sha256:{REQUEST_KEY}"
RETURN_REL = f"phase_11_submit_return/provider_return/{REQUEST_KEY}"
FINAL_REL = "phase_13_final_acceptance"
COLLECTION = "persona_dream_pipeline_steps"


def step(
    number: int,
    slug: str,
    name: str,
    status: str,
    paths: list[str],
    proves: str,
    does_not_prove: str,
    blocker: str | None = None,
) -> dict[str, Any]:
    return {
        "step_no": number,
        "step_slug": slug,
        "step_name": name,
        "status": status,
        "paths": paths,
        "proves": proves,
        "does_not_prove": does_not_prove,
        "blocker": blocker,
    }


STEPS = [
    step(1, "request_idea_intake", "Request / Idea Intake", "PASS", ["phase_01_idea/dream_request.json", "phase_01_idea/human_idea.json"], "The exact Embry and Kai surfing idea is bound to this revision.", "Downstream creative quality."),
    step(2, "dreaming_persona_selection", "Dreaming Persona Selection", "PASS_BOUND_REQUEST", ["phase_01_idea/dream_request.json", "phase_01_idea/human_idea.json"], "Embry is the dreaming persona and Kai is the secondary persona in the bound request.", "A new persona-selection model call."),
    step(3, "memory_recall", "Memory Recall", "PASS", ["phase_01_idea/residue_links.json", "revision_memory_verify_receipt.json"], "Persona-scoped residue and exact Memory revision reread exist.", "A new recall performed during this finalization."),
    step(4, "residue_grounding", "Residue Grounding", "PASS", ["phase_01_idea/residue_links.json", "phase_01_idea/contradiction_report.json"], "Residue links and contradiction findings are revision-bound.", "Dream-packet completeness."),
    step(5, "dream_packet", "Dream Packet", "BLOCKED_MISSING_REQUIRED_ARTIFACT", [], "No positive dream-packet artifact exists in this immutable revision.", "dream_packet.json or dream_prompt.txt.", "missing dream_packet.json and dream_prompt.txt"),
    step(6, "story_video_plan", "Story / Video Plan", "PASS", ["phase_02_story/story_contract.json"], "The accepted ten-second story contract is revision-bound.", "Look Lock or Script DNA."),
    step(7, "producer_selection", "Producer Persona Selection", "PASS", ["phase_03_crew/crew_contract.json"], "Karen Kehela Sherwood is selected as producer with rationale and source evidence.", "A new producer selection run."),
    step(8, "director_selection", "Director Selection", "PASS", ["phase_03_crew/crew_contract.json"], "Kathryn Bigelow is selected as director with rationale and source evidence.", "A new director selection run."),
    step(9, "script_writer_selection", "Script Writer Selection", "PASS", ["phase_03_crew/crew_contract.json"], "John Stockwell is selected as script writer with rationale and source evidence.", "A new writer selection run."),
    step(10, "creative_authority_receipts", "Creative Authority Receipts", "PASS", ["phase_03_crew/crew_contract.json", "phase_03_crew/crew_gate_receipt.json"], "Producer, director, and writer authority are recorded and gate-checked.", "Look Lock or Script DNA output."),
    step(11, "look_lock", "Look Lock", "BLOCKED_MISSING_REQUIRED_ARTIFACT", [], "The storyboard contains camera and lighting language but no canonical Look Lock receipt exists.", "technique_selection.json, look_lock.json, or shot_bible.json.", "missing canonical Look Lock artifacts"),
    step(12, "script_dna", "Script DNA", "BLOCKED_MISSING_REQUIRED_ARTIFACT", [], "The script is reviewed, but no canonical Script DNA selector receipt exists.", "script_dna_selection.json.", "missing script_dna_selection.json"),
    step(13, "storyboard_prompt_composition", "Storyboard Prompt Composition", "PASS", ["phase_07_storyboard_live_tau/storyboard_packet.json", "phase_07_storyboard_live_tau/storyboard_panel_contract.generated.json"], "Four timed storyboard prompts are bound to accepted references.", "Provider-return continuity."),
    step(14, "storyboard_panel_receipts", "Storyboard Panel Receipts", "PASS", ["phase_07_storyboard_live_tau/storyboard_packet.json", "revision_artifact_index.json"], "Eight accepted start/end frames and their receipt paths are indexed.", "Post-Kling action continuity."),
    step(15, "panel_continuity_repair_ledger", "Panel Continuity And Repair Ledger", "BLOCKED_MISSING_REQUIRED_ARTIFACT", [], "Panel review receipts exist, but the required consolidated ledger file does not.", "panel_continuity_and_repair_ledger.json.", "missing panel_continuity_and_repair_ledger.json"),
    step(16, "panel_generation_loop", "Panel Generation Loop", "PASS", ["phase_07_storyboard_live_tau/storyboard_packet.json", "revision_artifact_index.json"], "Generated storyboard frame paths, hashes, models, and provider receipts are indexed.", "Returned-video continuity."),
    step(17, "panel_visual_review_loop", "Panel Visual Review Loop", "PASS", ["phase_07_storyboard_live_tau/storyboard_packet.json", "phase_07_storyboard_live_tau/receipts/panel_repair_gate_receipt.json"], "Identity reviews and visual acceptance feed the panel gate.", "Post-Kling continuity."),
    step(18, "surgical_panel_repair", "Surgical Panel Repair", "PASS_NO_REPAIR_REQUIRED", ["phase_07_storyboard_live_tau/receipts/panel_repair_gate_receipt.json"], "The terminal reviewed panel state required no additional final repair attempt.", "That every historical candidate passed."),
    step(19, "panel_repair_gate", "Panel Repair Gate", "PASS", ["phase_07_storyboard_live_tau/receipts/panel_repair_gate_receipt.json"], "The canonical panel gate status is PASS_PANEL_REVIEWED.", "Returned-video continuity."),
    step(20, "panel_source_receipt", "Panel Source Receipt", "PASS", ["phase_07_storyboard_live_tau/receipts/panel_source_receipt.json"], "The canonical reviewed panel source receipt exists.", "Public provider fetchability."),
    step(21, "provider_media_publication_work_order", "Provider Media Publication Work Order", "PASS_EXISTING_PUBLICATION_REUSED", ["phase_11_submit_return/preflight/provider_media_transition_manifest.json"], "Phase 11 records the transition from existing GitHub publication to provider use.", "A new upload operation."),
    step(22, "local_provider_media_staging", "Local Provider Media Staging", "PASS_NOT_REQUIRED_ALREADY_PUBLISHED", ["phase_11_submit_return/preflight/provider_media_transition_manifest.json"], "The accepted media already had immutable public GitHub URLs, so no new local staging was required.", "A new staging copy."),
    step(23, "publication_preflight", "Publication Preflight", "PASS", ["phase_11_submit_return/preflight/phase11_adapter_preflight_receipt.v1.json", "phase_11_submit_return/preflight/provider_media_transition_manifest.json"], "The request-scoped adapter and media preflight passed.", "Provider-return visual quality."),
    step(24, "publication_authorization", "Publication Authorization", "PASS_APPROVED", [f"phase_11_submit_return/preflight/approvals/{REQUEST_KEY}/publication_authorization_receipt.json"], "Publication authority is approved for the exact request hash.", "Continuity quality."),
    step(25, "public_url_probe", "Public URL Probe", "PASS", ["phase_11_submit_return/preflight/provider_media_transition_manifest.json"], "Seven provider media URLs returned HTTP 200 with parity evidence.", "Provider generation quality."),
    step(26, "provider_media_handoff", "Provider Media Handoff", "PASS", ["phase_11_submit_return/preflight/provider_media_transition_manifest.json"], "Provider-accessible media URLs and bindings passed the transition gate.", "Returned-video continuity."),
    step(27, "provider_media_lock", "Provider Media Lock", "PASS", ["phase_11_submit_return/canonical/phase11_media_binding_manifest.v2.json"], "The exact provider media bindings are hash-locked to this request.", "Provider-return continuity."),
    step(28, "kling_scene_packet", "Kling Scene Packet", "PASS_EXECUTED_REQUEST", ["phase_11_submit_return/canonical/phase11_live_request.v1.json"], "The exact four-prompt audio-off request is canonical and was later submitted once.", "Provider-return continuity."),
    step(29, "provider_final_gate", "Provider Final Gate", "PASS_EXECUTED_PREFLIGHT", ["phase_11_submit_return/preflight/phase11_adapter_preflight_receipt.v1.json", f"phase_11_submit_return/attempts/{REQUEST_KEY}/attempt_ledger.v1.json"], "Technical preflight passed before the request-scoped submit-once transition.", "Post-return acceptance."),
    step(30, "paid_call_authorization", "Paid Call Authorization", "PASS_APPROVED_CONSUMED", [f"phase_11_submit_return/preflight/approvals/{REQUEST_KEY}/paid_call_authorization_receipt.json", f"phase_11_submit_return/attempts/{REQUEST_KEY}/attempt_ledger.v1.json"], "One exact paid attempt was authorized and consumed once.", "Authorization for another attempt."),
    step(31, "kling_submit", "Kling Submit", "PASS_LIVE", [f"phase_11_submit_return/attempts/{REQUEST_KEY}/attempt_ledger.v1.json", f"{RETURN_REL}/phase11_provider_return_envelope.v1.json"], "One live provider submit produced request id 019f6bef-0c0f-7921-8a5e-a1f12890fb75.", "Visual acceptance."),
    step(32, "kling_poll_callback", "Kling Poll / Callback", "PASS_LIVE", [f"phase_11_submit_return/attempts/{REQUEST_KEY}/attempt_ledger.v1.json"], "The attempt ledger records 43 polls and a completed terminal event.", "Visual acceptance."),
    step(33, "output_retrieval", "Output Retrieval", "PASS_LIVE", [f"{RETURN_REL}/provider_return.mp4", f"{RETURN_REL}/phase11_provider_return_envelope.v1.json"], "The 18,520,578-byte provider MP4 was downloaded and hash-locked.", "Continuity acceptance."),
    step(34, "ffprobe_technical_validation", "FFprobe / Technical Validation", "PASS_LIVE", [f"{RETURN_REL}/phase11_download_ffprobe_receipt.v1.json", f"{RETURN_REL}/provider_return.mp4"], "FFprobe reports readable H.264, 1280x720, 24 fps, and 10.041667 seconds.", "Story continuity."),
    step(35, "frame_contact_sheet", "Frame Contact Sheet", "PASS", [f"{RETURN_REL}/frame_contact_sheet.png", f"{RETURN_REL}/frame_contact_sheet_receipt.v1.json"], "A 4x3 PNG contains all twelve Watch frames from the exact MP4.", "Continuity acceptance."),
    step(36, "post_kling_continuity_review", "Post-Kling Continuity Review", "FAIL", [f"{RETURN_REL}/post_kling_continuity_review_receipt.v1.json", f"{RETURN_REL}/frame_contact_sheet.png"], "The exact MP4 was inspected against all four intended beats.", "Final acceptance because SB_004 action and reef geometry fail.", "SB_004 commit action and visible lava-reef boundary are missing"),
    step(37, "voice_audio_handoff", "Voice / Audio Handoff Lane When Voiced", "PASS_NOT_REQUIRED_AUDIO_OFF", ["phase_11_submit_return/canonical/phase11_live_request.v1.json", f"{RETURN_REL}/phase11_download_ffprobe_receipt.v1.json"], "generate_audio=false agrees with the returned video having no audio stream.", "A voiced-video lane."),
    step(38, "final_assembly_movie_lane", "Final Assembly / Movie Lane", "PASS_NOT_REQUIRED_SINGLE_PROVIDER_OUTPUT", [f"{RETURN_REL}/provider_return.mp4", f"{RETURN_REL}/phase11_download_ffprobe_receipt.v1.json"], "The bounded run has one provider-return clip and requires no stitch or mux operation.", "Continuity acceptance."),
    step(39, "report_generation", "Report Generation", "PASS_BLOCKED_REPORT", [f"{FINAL_REL}/final_report.v1.json", f"{FINAL_REL}/final_report.md"], "The final report is source-derived and explicitly blocked on continuity and missing upstream contracts.", "Final acceptance."),
    step(40, "gate_validation_loop", "Gate Validation Loop", "BLOCKED", [f"{FINAL_REL}/final_gate_validation_summary.v1.json"], "All 42 step states are enumerated with blockers and the next critical action.", "A passing final gate.", "seven non-passing or missing-contract step states remain"),
    step(41, "upstream_revision_invalidation", "Upstream Revision Invalidation", "PASS", ["revision_activation_receipt.json", "semantic_mix_repair_receipt.json", "revision_manifest.json"], "The mixed predecessor was rejected and this immutable revision was activated with lineage evidence.", "Post-Kling continuity."),
    step(42, "final_acceptance_boundary", "Final Acceptance Boundary", "BLOCKED", [f"{FINAL_REL}/final_acceptance_receipt.v1.json"], "The acceptance boundary records the exact successful live evidence and every remaining blocker.", "Final acceptance.", "post-Kling continuity failed and required upstream contract artifacts are absent"),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_final_artifacts(revision_root: Path, observed_at: str, memory_exact_count: int = 0) -> None:
    final_root = revision_root / FINAL_REL
    blockers = [
        {"step_no": item["step_no"], "step_name": item["step_name"], "status": item["status"], "blocker": item["blocker"]}
        for item in STEPS
        if item["status"].startswith("BLOCKED") or item["status"] == "FAIL"
    ]
    counts = {
        "total": 42,
        "passing_or_not_required": 42 - len(blockers),
        "failed": sum(item["status"] == "FAIL" for item in STEPS),
        "blocked": sum(item["status"].startswith("BLOCKED") for item in STEPS),
    }
    gate = {
        "schema": "persona_dream.final_gate_validation_summary.v1",
        "status": "BLOCKED_FINAL_ACCEPTANCE",
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "request_body_sha256": REQUEST_SHA,
        "counts": counts,
        "blockers": blockers,
        "live_evidence": {"provider_calls": 1, "poll_count": 43, "returned_mp4": True, "ffprobe_pass": True, "frame_contact_sheet_pass": True},
        "memory_persistence": {"collection": COLLECTION, "exact_reread_count": memory_exact_count, "expected_count": 42},
        "next_critical_action": "restore the missing upstream contract artifacts, then compile a repaired SB_004 request and obtain separate authorization for one new paid attempt",
        "mocked": False,
        "live": True,
        "observed_at": observed_at,
    }
    acceptance = {
        "schema": "persona_dream.final_acceptance_receipt.v1",
        "status": "BLOCKED_FINAL_ACCEPTANCE",
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "request_body_sha256": REQUEST_SHA,
        "accepted": False,
        "working_kling_video_returned": True,
        "provider_mp4_sha256": "sha256:2545394fb8e48694acb2751b25cbf6fc55a4dfdbde66e241deecfb5f2f1ecd33",
        "technical_validation_passed": True,
        "frame_contact_sheet_passed": True,
        "post_kling_continuity_passed": False,
        "pipeline_step_memory_target": 42,
        "pipeline_step_memory_exact_reread": memory_exact_count,
        "blockers": blockers,
        "claims": {
            "proves": ["a real Kling MP4 was submitted, polled, downloaded, technically validated, contact-sheeted, and visually reviewed"],
            "does_not_prove": ["the returned video satisfies the final action contract", "the immutable goal is accepted"],
        },
        "observed_at": observed_at,
    }
    report = {
        "schema": "persona_dream.final_report.v1",
        "status": "BLOCKED_FINAL_ACCEPTANCE",
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "request_body_sha256": REQUEST_SHA,
        "counts": counts,
        "mocked": False,
        "live": True,
        "actually_exercised": ["one live Kling submit", "43 provider polls", "MP4 retrieval", "ffprobe", "12-frame Watch analysis", "4x3 contact-sheet inspection"],
        "verified_outputs": {
            "provider_mp4": f"../phase_11_submit_return/provider_return/{REQUEST_KEY}/provider_return.mp4",
            "provider_mp4_sha256": "sha256:2545394fb8e48694acb2751b25cbf6fc55a4dfdbde66e241deecfb5f2f1ecd33",
            "duration_seconds": 10.041667,
            "codec": "h264",
            "dimensions": "1280x720",
            "fps": 24,
            "contact_sheet": f"../phase_11_submit_return/provider_return/{REQUEST_KEY}/frame_contact_sheet.png",
        },
        "continuity_result": "FAILED_POST_KLING_CONTINUITY_REVIEW",
        "memory_persistence": {"collection": COLLECTION, "exact_reread_count": memory_exact_count, "expected_count": 42},
        "blockers": blockers,
        "observed_at": observed_at,
    }
    dump(final_root / "final_gate_validation_summary.v1.json", gate)
    dump(final_root / "final_acceptance_receipt.v1.json", acceptance)
    dump(final_root / "final_report.v1.json", report)
    lines = [
        "# Persona Dream Final Report",
        "",
        "Status: `BLOCKED_FINAL_ACCEPTANCE`",
        "",
        f"Run: `{RUN_ID}`",
        f"Revision: `{REVISION_ID}`",
        f"Request: `{REQUEST_SHA}`",
        "",
        "A real 10.041667-second H.264 Kling MP4 was submitted once, polled 43 times, downloaded, ffprobed, sampled into 12 frames, and assembled into a 4x3 contact sheet.",
        "",
        "Final acceptance is blocked. The final beat does not visibly show Embry committing through the safe channel or a readable lava-reef boundary. Canonical Dream Packet, Look Lock, Script DNA, and panel continuity-ledger artifacts are also absent from this immutable revision.",
        "",
        f"Step counts: {counts['passing_or_not_required']} passing/not-required, {counts['failed']} failed, {counts['blocked']} blocked, 42 total. Memory exact reread: {memory_exact_count}/42.",
        "",
        "Mocked: no",
        "Live: yes",
    ]
    (final_root / "final_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_documents(revision_root: Path, observed_at: str) -> list[dict[str, Any]]:
    documents = []
    for item in STEPS:
        hashes: dict[str, str] = {}
        for relative in item["paths"]:
            path = revision_root / relative
            if not path.is_file():
                raise SystemExit(f"required evidence path missing for step {item['step_no']:02d}: {path}")
            hashes[relative] = sha256(path)
        key = f"persona_dream:{RUN_ID}:{REVISION_ID}:{item['step_no']:02d}:{item['step_slug']}"
        documents.append({
            "_key": key,
            "schema": "persona_dream.pipeline_step_memory.v1",
            "run_id": RUN_ID,
            "revision_id": REVISION_ID,
            "step_no": item["step_no"],
            "step_slug": item["step_slug"],
            "step_name": item["step_name"],
            "status": item["status"],
            "inputs": {"request_body_sha256": REQUEST_SHA, "source_revision_id": REVISION_ID},
            "outputs": item["paths"],
            "receipt_paths": [path for path in item["paths"] if path.endswith(".json")],
            "artifact_hashes": hashes,
            "request_hash": REQUEST_SHA if item["step_no"] >= 24 else None,
            "provider_task_id": "019f6bef-0c0f-7921-8a5e-a1f12890fb75" if 31 <= item["step_no"] <= 36 else None,
            "memory_write_method": "/upsert",
            "memory_write_receipt": {"collection": COLLECTION, "batch_size": 42, "status": "PASS"},
            "exact_reread_receipt": {"endpoint": "/list", "filters": {"run_id": RUN_ID, "revision_id": REVISION_ID}, "expected_count": 42, "status": "PASS"},
            "semantic_sync_state": "requested",
            "qdrant_collection": None,
            "qdrant_point_id": None,
            "claims": {"proves": [item["proves"]], "does_not_prove": [item["does_not_prove"]]},
            "blocker": item["blocker"],
            "observed_at": observed_at,
            "retrieval_text": f"Persona Dream {RUN_ID} {REVISION_ID} step {item['step_no']:02d} {item['step_name']} status {item['status']}",
            "tags": ["persona-dream", f"run:{RUN_ID}", f"revision:{REVISION_ID}", f"step:{item['step_no']:02d}", f"status:{item['status'].lower()}"],
        })
    return documents


def response_documents(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return payload.get("documents") or payload.get("items") or []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("revision_root", type=Path)
    parser.add_argument("--memory-base-url", default="http://127.0.0.1:8601")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    revision_root = args.revision_root.expanduser().resolve()
    observed_at = datetime.now(timezone.utc).isoformat()

    build_final_artifacts(revision_root, observed_at)
    documents = make_documents(revision_root, observed_at)
    final_root = revision_root / FINAL_REL
    dump(final_root / "pipeline_step_memory_records.v1.json", {"schema": "persona_dream.pipeline_step_memory_bundle.v1", "count": 42, "documents": documents})
    if args.dry_run:
        print(json.dumps({"status": "DRY_RUN", "document_count": len(documents), "final_root": str(final_root)}, indent=2))
        return 0

    timeout = httpx.Timeout(30.0, connect=2.0)
    with httpx.Client(base_url=args.memory_base_url, timeout=timeout) as client:
        write = client.post("/upsert", json={"collection": COLLECTION, "documents": documents})
        write.raise_for_status()
        first = client.post("/list", json={"collection": COLLECTION, "limit": 100, "filters": {"run_id": RUN_ID, "revision_id": REVISION_ID}})
        first.raise_for_status()
        first_docs = response_documents(first.json())
        by_key = {doc["_key"]: doc for doc in first_docs}
        expected_keys = {doc["_key"] for doc in documents}
        if set(by_key) != expected_keys:
            raise SystemExit(f"first exact reread key mismatch: expected 42, got {len(by_key)}")
        for document in documents:
            stored = by_key[document["_key"]]
            document["semantic_sync_state"] = stored.get("semantic_sync_state", "unknown")
            document["qdrant_collection"] = stored.get("qdrant_collection")
            document["qdrant_point_id"] = stored.get("qdrant_point_id")
        second_write = client.post("/upsert", json={"collection": COLLECTION, "documents": documents})
        second_write.raise_for_status()
        final = client.post("/list", json={"collection": COLLECTION, "limit": 100, "filters": {"run_id": RUN_ID, "revision_id": REVISION_ID}})
        final.raise_for_status()
        final_docs = response_documents(final.json())
    final_keys = {doc.get("_key") for doc in final_docs}
    if final_keys != expected_keys or len(final_docs) != 42:
        raise SystemExit(f"final exact reread mismatch: expected 42, got {len(final_docs)}")
    build_final_artifacts(revision_root, observed_at, memory_exact_count=42)
    final_documents = make_documents(revision_root, observed_at)
    final_by_key = {doc["_key"]: doc for doc in final_docs}
    for document in final_documents:
        stored = final_by_key[document["_key"]]
        document["semantic_sync_state"] = stored.get("semantic_sync_state", "unknown")
        document["qdrant_collection"] = stored.get("qdrant_collection")
        document["qdrant_point_id"] = stored.get("qdrant_point_id")
    with httpx.Client(base_url=args.memory_base_url, timeout=timeout) as client:
        hash_refresh = client.post("/upsert", json={"collection": COLLECTION, "documents": final_documents})
        hash_refresh.raise_for_status()
        refreshed = client.post("/list", json={"collection": COLLECTION, "limit": 100, "filters": {"run_id": RUN_ID, "revision_id": REVISION_ID}})
        refreshed.raise_for_status()
        refreshed_docs = response_documents(refreshed.json())
    refreshed_keys = {doc.get("_key") for doc in refreshed_docs}
    if refreshed_keys != expected_keys or len(refreshed_docs) != 42:
        raise SystemExit(f"hash-refresh exact reread mismatch: expected 42, got {len(refreshed_docs)}")
    documents = final_documents
    final_docs = refreshed_docs
    final_keys = refreshed_keys
    receipt = {
        "schema": "persona_dream.pipeline_step_memory_write_receipt.v1",
        "status": "PASS_EXACT_REREAD_42_OF_42",
        "collection": COLLECTION,
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "request_body_sha256": REQUEST_SHA,
        "upsert_response": write.json(),
        "second_upsert_response": second_write.json(),
        "hash_refresh_upsert_response": hash_refresh.json(),
        "exact_reread_count": 42,
        "exact_reread_keys": sorted(final_keys),
        "semantic_synced_count": sum(doc.get("semantic_sync_state") == "synced" for doc in final_docs),
        "qdrant_pointer_count": sum(bool(doc.get("qdrant_point_id")) for doc in final_docs),
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "claims": {
            "proves": ["all 42 pipeline step states are durably present under exact run and revision filters"],
            "does_not_prove": ["all 42 steps passed", "final acceptance", "post-Kling continuity"],
        },
    }
    dump(final_root / "pipeline_step_memory_write_receipt.v1.json", receipt)
    dump(final_root / "pipeline_step_memory_records.v1.json", {"schema": "persona_dream.pipeline_step_memory_bundle.v1", "count": 42, "documents": documents})
    print(json.dumps({"status": receipt["status"], "exact_reread_count": 42, "semantic_synced_count": receipt["semantic_synced_count"], "qdrant_pointer_count": receipt["qdrant_pointer_count"], "final_root": str(final_root)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
