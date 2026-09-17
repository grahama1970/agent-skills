"""Numeric-gate boundary tests; synthetic samples cannot establish real-human efficacy."""
import pytest
from pydantic import ValidationError

from a_detection.contracts import Policy
from a_detection.efficacy import EfficacyRequest, qualify
from a_detection.errors import DetectionError
from a_detection.model import model_digest, save_model, train
from tests.helpers import corpus


def test_synthetic_corpus_cannot_enter_real_efficacy_gate(tmp_path):
    rows = corpus()
    path = tmp_path / "clearly-synthetic.jsonl"
    path.write_text("\n".join(row.model_dump_json() for row in rows))
    model, _ = train(rows)
    model_path = tmp_path / "synthetic-model.json"
    save_model(model_path, model)
    request = EfficacyRequest(corpus=str(path), model=str(model_path), model_sha256=model_digest(model),
                             study_id="SYNTHETIC-NEGATIVE-CONTROL", min_tpr=0.5,
                             minimum_heldout_families=2, minimum_test_human_sessions=300)
    with pytest.raises(DetectionError):
        qualify(request, Policy())


@pytest.mark.parametrize("minimum", [0, -1, "300", True])
def test_sample_requirement_cannot_be_malformed(minimum):
    with pytest.raises(ValidationError):
        EfficacyRequest(corpus="/external/study.jsonl", model="/external/model.json", model_sha256="0"*64,
                        study_id="example", min_tpr=0.5, minimum_heldout_families=2,
                        minimum_test_human_sessions=minimum)
