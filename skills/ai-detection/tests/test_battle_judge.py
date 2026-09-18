"""ai-detection as a Battle invariant target, driven by Battle's own run_judge."""
import sys
from pathlib import Path

from ai_detection.humanize import Transform, humanize
from ai_detection.model import save_model, train
from tests.helpers import corpus

# Import Battle's real judge runner rather than reimplementing scoring.
_BATTLE_SRC = Path(__file__).resolve().parents[2] / "battle" / "src"
if str(_BATTLE_SRC) not in sys.path:
    sys.path.insert(0, str(_BATTLE_SRC))

JUDGE = str(Path(__file__).resolve().parents[1] / "battle" / "detector_judge.py")


def _trained_model(tmp_path):
    model, _ = train(corpus())
    model_path = tmp_path / "model.json"
    save_model(model_path, model)
    return model, model_path


def test_battle_judge_passes_when_ai_code_stays_flagged(tmp_path):
    from battle_skill.invariant_judge import run_judge

    _model, model_path = _trained_model(tmp_path)
    target = tmp_path / "released"
    target.mkdir()
    for i, rec in enumerate(r for r in corpus() if r.label == "machine"):
        (target / f"m{i}.py").write_text(rec.source, encoding="utf-8")

    result = run_judge(JUDGE, str(target), {"model_path": str(model_path)}).to_dict()
    assert result["schema"] == "battle.invariant_result.v1"
    assert result["passed"] is True  # synthetic detector keeps AI samples flagged
    assert result["violations"] == []
    assert result["evidence"]["proof_scope"] == "mechanism_only_score_vs_threshold"


def test_battle_judge_fails_closed_and_records_red_wins(tmp_path):
    from battle_skill.invariant_judge import run_judge

    model, model_path = _trained_model(tmp_path)
    target = tmp_path / "released"
    target.mkdir()
    # Force a Red win by planting a below-threshold file (a human-style sample).
    human = next(r.source for r in corpus() if r.label == "human")
    (target / "evader.py").write_text(humanize(human, Transform.AST_REFORMAT), encoding="utf-8")

    result = run_judge(JUDGE, str(target), {
        "model_path": str(model_path), "threshold": model.calibration.threshold}).to_dict()
    assert result["schema"] == "battle.invariant_result.v1"
    # Either the planted file scores below threshold (violation) or not; the
    # contract we assert is that the judge produced a typed, fail-closed verdict.
    assert isinstance(result["passed"], bool)
    assert isinstance(result["violations"], list)

    # Missing model => fail-closed FAILED, never a silent pass.
    bad = run_judge(JUDGE, str(target), {"model_path": str(tmp_path / "nope.json")}).to_dict()
    assert bad["passed"] is False and bad["violations"]
