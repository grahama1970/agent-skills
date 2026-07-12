from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cognitive", ROOT / "scripts/write_cognitive_loop_dry_run.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


def test_fixture_observation_blocks_interpretation_and_writes():
    observation = {"fixture_backed": True, "transcript_facts": [{"fact_id": "transcript-001", "statement": "Kai, wait."}], "visual_facts": []}
    residue = {"schema": "persona_dream.residue_links.v1", "items": [{"source_id": "memory-1", "persona_id": "embry", "scope": "persona-dream", "text": "Embry remembers Kai challenging whether schedules demonstrate care.", "scores": {"bm25": 1.0}}]}
    outputs = module.build(observation, residue, "dream-1", "rev-1", "sha256:residue")
    assert outputs["interpretation"]["accepted_interpretations"] == []
    assert "BLOCKED_INTERPRETATION_PROVIDER_OBSERVATION_MISSING" in outputs["interpretation"]["blockers"]
    assert "BLOCKED_INTERPRETATION_SOURCE_MEMORY_BINDING_MISSING" not in outputs["interpretation"]["blockers"]
    assert outputs["interpretation"]["candidates"][0]["source_memory_refs"] == ["memory-1"]
    assert outputs["interpretation"]["source_memory_bindings"][0]["memory_text_sha256"].startswith("sha256:")
    assert outputs["tom"]["accepted_tom"] == []
    assert outputs["persistence"]["actual_memory_writes"] == 0
    assert outputs["persistence"]["direct_qdrant_writes_allowed"] is False
    assert outputs["recall"]["executed"] is False
    assert outputs["behavior"]["executed"] is False


def test_wrong_persona_residue_remains_blocked():
    observation = {"fixture_backed": True, "transcript_facts": [{"fact_id": "transcript-001"}], "visual_facts": []}
    residue = {"schema": "persona_dream.residue_links.v1", "items": [{"source_id": "memory-1", "persona_id": "other", "text": "Wrong persona memory."}]}
    outputs = module.build(observation, residue, "dream-1", "rev-1", "sha256:residue")
    assert "BLOCKED_INTERPRETATION_PERSONA_SCOPE_MISMATCH:memory-1" in outputs["interpretation"]["blockers"]
    assert "BLOCKED_INTERPRETATION_SOURCE_MEMORY_BINDING_MISSING" in outputs["interpretation"]["blockers"]
