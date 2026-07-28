#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON=(uv run --project "${SCRIPT_DIR}" python)
OUT_DIR="$(mktemp -d /tmp/persona-dream-sanity.XXXXXX)"

"${SCRIPT_DIR}/run.sh" generate \
  --persona embry \
  --fixture "${SCRIPT_DIR}/scripts/fixtures/sample_residue.json" \
  --output-dir "${OUT_DIR}" \
  --run-id sanity \
  --no-write-memory

"${PYTHON[@]}" - "${OUT_DIR}" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
required = [
    "dream_request.json",
    "response.json",
    "residue_links.json",
    "contradiction_report.json",
    "dream_packet.json",
    "dream_prompt.txt",
    "frame_prompts.json",
    "contact_sheet.png",
    "dream_reflection.md",
    "memory_write_receipt.json",
]
missing = [name for name in required if not (out / name).exists()]
if missing:
    raise SystemExit(f"missing artifacts: {missing}")

if (out / "contact_sheet.png").read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
    raise SystemExit("contact_sheet.png is not a PNG")

packet = json.loads((out / "dream_packet.json").read_text())
receipt = json.loads((out / "memory_write_receipt.json").read_text())
response = json.loads((out / "response.json").read_text())

assert packet["schema"] == "persona_dream.packet.v1"
assert packet["persona"]["id"] == "embry"
assert len(packet["frame_prompts"]) >= 3
assert receipt["status"] == "skipped"
assert response["status"] == "ok"

print(json.dumps({
    "status": "ok",
    "mode": "static_dream",
    "output_dir": str(out),
    "artifact_count": len(required),
    "frame_count": len(packet["frame_prompts"]),
}, indent=2))
PY

VIDEO_OUT_DIR="$(mktemp -d /tmp/persona-dream-video-plan-sanity.XXXXXX)"

"${SCRIPT_DIR}/run.sh" generate \
  --mode video_plan \
  --persona horus \
  --secondary-persona embry \
  --fixture "${SCRIPT_DIR}/scripts/fixtures/sample_residue.json" \
  --about "creating the SPARTA Explorer app" \
  --scene "Horus and Embry have tea under a patio table with an umbrella on a 40k void world where Tyranids are playing in the background." \
  --duration-seconds 30 \
  --output-dir "${VIDEO_OUT_DIR}" \
  --run-id video-plan-sanity \
  --no-write-memory

"${PYTHON[@]}" - "${VIDEO_OUT_DIR}" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
required = [
    "dream_story.md",
    "dream_story.json",
    "character_scene_bible.json",
    "storyboard.json",
    "timed_transcript.json",
    "multimodal_prompts.json",
    "voice_handoff_plan.json",
    "pipeline_stage_report.json",
    "pipeline_stage_report.md",
    "manifest.json",
]
missing = [name for name in required if not (out / name).exists()]
if missing:
    raise SystemExit(f"missing video_plan artifacts: {missing}")

timed = json.loads((out / "timed_transcript.json").read_text())
prompts = json.loads((out / "multimodal_prompts.json").read_text())
voice = json.loads((out / "voice_handoff_plan.json").read_text())
bible = json.loads((out / "character_scene_bible.json").read_text())
report = json.loads((out / "pipeline_stage_report.json").read_text())
manifest = json.loads((out / "manifest.json").read_text())

shots = timed["shots"]
prompt_items = prompts["prompts"]
durations = [shot["duration_sec"] for shot in shots]
frame_counts = [prompt["num_frames"] for prompt in prompt_items]

assert timed["schema"] == "persona_dream.timed_transcript.v1"
assert timed["duration_seconds"] == 30
assert len(shots) == 4
assert durations == [7.5, 7.5, 7.5, 7.5]
assert len(prompt_items) == 4
assert frame_counts == [121, 121, 121, 121]
assert voice["schema"] == "persona_dream.voice_handoff_plan.v1"
assert voice["owner"] == "create-movie/audio-lane"
assert {speaker["speaker_id"] for speaker in voice["speakers"]} == {"embry", "horus"}
assert [line["speaker_id"] for line in voice["lines"]] == ["horus", "embry", "horus", "horus"]
assert any("voice_identity_boundary_receipt.json" in receipt for receipt in voice["required_receipts"])
assert bible["schema"] == "persona_dream.character_scene_bible.v1"
assert {character["character_id"] for character in bible["characters"]} == {"embry", "horus"}
assert bible["self_improvement_loop"]["schema"] == "persona_dream.self_improvement_loop.v1"
assert report["schema"] == "persona_dream.pipeline_stage_report.v1"
assert any(stage["stage_id"] == "stage_09_voice_handoff" for stage in report["stages"])
assert any(stage["stage_id"] == "stage_10_self_improvement_loop" for stage in report["stages"])
assert manifest["mode"] == "video_plan"
assert "i2v" in manifest["next_lanes"]
assert "voice_handoff_plan.json" in manifest["required_modes"]["video_plan"]

print(json.dumps({
    "status": "ok",
    "mode": "video_plan",
    "output_dir": str(out),
    "artifact_count": len(required),
    "shot_durations": durations,
    "frame_counts": frame_counts,
}, indent=2))
PY

"${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_storyboard_first_fixture_regressions.py"

"${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" \
  "${SCRIPT_DIR}/scripts/fixtures/panel_repair_gate_valid.json" \
  --require-provider-eligible

"${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" \
  "${SCRIPT_DIR}/scripts/fixtures/panel_repair_gate_valid_voiced.json" \
  --require-provider-eligible

if "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" \
  "${SCRIPT_DIR}/scripts/fixtures/panel_repair_gate_invalid_partial_pass.json" \
  --require-provider-eligible; then
  echo "invalid partial pass fixture unexpectedly passed" >&2
  exit 1
fi

if "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" \
  "${SCRIPT_DIR}/scripts/fixtures/panel_repair_gate_invalid_provider_fields.json" \
  --require-provider-eligible; then
  echo "invalid provider field fixture unexpectedly passed" >&2
  exit 1
fi

if "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" \
  "${SCRIPT_DIR}/scripts/fixtures/panel_repair_gate_invalid_voice_id_claim.json" \
  --require-provider-eligible; then
  echo "invalid voice id claim fixture unexpectedly passed" >&2
  exit 1
fi

if "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" \
  "${SCRIPT_DIR}/scripts/fixtures/panel_repair_gate_invalid_missing_receipts.json" \
  --require-provider-eligible; then
  echo "invalid missing receipts fixture unexpectedly passed" >&2
  exit 1
fi

if "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" \
  "${SCRIPT_DIR}/scripts/fixtures/panel_repair_gate_invalid_voice_source_mismatch.json" \
  --require-provider-eligible; then
  echo "invalid voice source mismatch fixture unexpectedly passed" >&2
  exit 1
fi

"${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_panel_repair_gate_schema_consistency.py"


CONTACT_GATE_FIXTURE="$(mktemp -d /tmp/persona-dream-contact-gate.XXXXXX)"
"${PYTHON[@]}" - "${CONTACT_GATE_FIXTURE}" <<'PYGATE'
import json
import shutil
import sys
from pathlib import Path
from PIL import Image

fixture_root = Path(sys.argv[1])
src_run = Path("/mnt/storage12tb/skills/persona-dream/outputs/20260612-horus-embry-storyboard-first-scillm-strict")
refs = fixture_root / "reference_sheets"
refs.mkdir(parents=True)
review = fixture_root / "pipeline_review_8892" / "artifacts"
review.mkdir(parents=True)
gate_src = src_run / "pipeline_review_8892" / "artifacts" / "phase_05_contact_sheets_anti_hallucination_gate.json"
if gate_src.exists():
    shutil.copy2(gate_src, review / "phase_05_contact_sheets_anti_hallucination_gate.json")
for name in [
    "horus_reference_sheet.png",
    "embry_reference_sheet.png",
    "creature_baby_tyranid_railing_reference_sheet.png",
    "prop_umbrella_reference_sheet.png",
]:
    shutil.copy2(src_run / "reference_sheets" / name, refs / name)
Image.new("RGB", (1332, 790), "#223344").save(refs / "prop_umbrella_reference_sheet.png")
print(json.dumps({"fixture_root": str(fixture_root)}))
PYGATE

if "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_phase_05_contact_sheet_gate.py"   --run-root "${CONTACT_GATE_FIXTURE}" --json; then
  echo "wrong-size contact-sheet fixture unexpectedly passed" >&2
  exit 1
fi

if [[ -n "${PERSONA_DREAM_CONTACT_GATE_RUN_ROOT:-}" ]]; then
  "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_phase_05_contact_sheet_gate.py"     --run-root "${PERSONA_DREAM_CONTACT_GATE_RUN_ROOT}"     --write-gate     --json
fi

# Boundary guard: enforce the operator rule "only /tau may reach /scillm".
# Deterministic static scan (no network); fails on any un-sanctioned direct
# scillm proxy call in skills/persona-dream or skills/watch. The TEMPORARY_DEBT
# registry is now empty (all callers migrated to Tau, allowlisted as diagnostics,
# or retired), so the ratchet runs in --strict mode: ANY remaining direct-scillm
# line (a new caller, or a reverted migration) fails the gate.
echo "== enforcing current-state/receipt consistency (check-current-state-consistency --strict) =="
"${SCRIPT_DIR}/run.sh" check-current-state-consistency --strict

echo "== enforcing Tau-only model-routing boundary (check-tau-routing-boundary --strict) =="
"${SCRIPT_DIR}/run.sh" check-tau-routing-boundary --strict

# CI guard: deterministic contract suite must stay green. This is the offline
# regression net that catches contract/schema/fixture rot (e.g. omitted vendored
# schemas or relocated agent-contract paths). No paid or live provider calls.
echo "== running deterministic contract suite (run.sh test-suite) =="
"${SCRIPT_DIR}/run.sh" test-suite
