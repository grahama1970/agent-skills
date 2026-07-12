from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cognitive", ROOT / "scripts/write_cognitive_loop_dry_run.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


def test_fixture_observation_blocks_interpretation_and_writes():
    observation = {"fixture_backed": True, "transcript_facts": [{"fact_id": "transcript-001", "statement": "Kai, wait."}], "visual_facts": []}
    outputs = module.build(observation, "dream-1", "rev-1")
    assert outputs["interpretation"]["accepted_interpretations"] == []
    assert "BLOCKED_INTERPRETATION_PROVIDER_OBSERVATION_MISSING" in outputs["interpretation"]["blockers"]
    assert outputs["tom"]["accepted_tom"] == []
    assert outputs["persistence"]["actual_memory_writes"] == 0
    assert outputs["persistence"]["direct_qdrant_writes_allowed"] is False
    assert outputs["recall"]["executed"] is False
    assert outputs["behavior"]["executed"] is False
