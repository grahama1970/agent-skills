"""Explainer catalog IO for explain-project.

Reads strict JSONL records and emits deterministic summaries/sample fixtures.
JSON syntax and Pydantic failures are raised to the caller so the CLI/server can
return structured terminal errors instead of partial records.
"""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .models import (
    ExplainerStep,
    ExplainerSummary,
    FailureCode,
    FeatureExplainer,
)


class CatalogError(ValueError):
    """Catalog input failure with line-aware details."""

    def __init__(
        self,
        code: FailureCode,
        message: str,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.errors = list(errors or [])


def _validation_errors(
    error: ValidationError,
) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []

    for item in error.errors():
        entry = dict(item)
        if "ctx" in entry:
            entry["ctx"] = {
                key: str(value)
                for key, value in entry["ctx"].items()
            }
        cleaned.append(entry)

    return cleaned


def read_jsonl(path: Path) -> list[FeatureExplainer]:
    """Read and strictly validate all non-empty JSONL records."""

    rows: list[FeatureExplainer] = []

    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        1,
    ):
        if not line.strip():
            continue

        try:
            raw = json.loads(line)
        except JSONDecodeError as error:
            raise CatalogError(
                FailureCode.JSON_DECODE_FAILED,
                f"line {line_number}: {error.msg}",
                [
                    {
                        "loc": [line_number, error.pos],
                        "msg": error.msg,
                        "type": "json_decode",
                    }
                ],
            ) from error

        try:
            rows.append(FeatureExplainer.model_validate(raw))
        except ValidationError as error:
            raise CatalogError(
                FailureCode.PYDANTIC_VALIDATION_FAILED,
                (
                    f"line {line_number}: "
                    "Pydantic boundary validation failed"
                ),
                [
                    {"line": line_number, **item}
                    for item in _validation_errors(error)
                ],
            ) from error

    return rows


def steps_for(row: FeatureExplainer) -> list[ExplainerStep]:
    """Return explicit steps, or one backward-compatible legacy step."""

    if row.steps:
        return row.steps

    bullets = list(row.teleprompter_points[:4])
    if len(bullets) == 1:
        bullets.append(row.proof_boundary)

    return [
        ExplainerStep(
            step_id="legacy-1",
            title=row.title,
            bullets=bullets,
            source_range_index=0,
            source_explanation=row.question,
            debugger_stop_index=0 if row.debugger_stops else None,
            diagram_node_ids=row.diagram.node_ids[:1],
            proof_boundary=row.proof_boundary,
            confidence=row.confidence,
        )
    ]


def summaries(
    rows: list[FeatureExplainer],
) -> list[ExplainerSummary]:
    """Build stable UI catalog summaries."""

    return [
        ExplainerSummary(
            feature_id=row.feature_id,
            title=row.title,
            question_family=row.question_family,
            question=row.question,
            steps=len(steps_for(row)),
            diagram_source=row.diagram.source_path,
            diagram_verified=bool(row.diagram.sha256),
            diagram_nodes=len(row.diagram.node_ids),
        )
        for row in sorted(
            rows,
            key=lambda item: item.feature_id,
        )
    ]


def sample_record() -> FeatureExplainer:
    """Return the retained three-step sample explainer."""

    return FeatureExplainer.model_validate(
        {
            "schema": "project.feature_explainer.v1",
            "feature_id": "publish.report_last",
            "title": "Report-last publication",
            "question_family": "failure",
            "question": (
                "What happens if a worker crashes "
                "before reporting success?"
            ),
            "teleprompter_points": [
                "The corpus may exist before the release is READY.",
                (
                    "READY is only published after "
                    "report.json is renamed last."
                ),
                (
                    "A failed worker is replayed or quarantined; "
                    "partial output is not success."
                ),
            ],
            "source_ranges": [
                {
                    "file": "src/anonymization_trial/pipeline.py",
                    "start_line": 180,
                    "end_line": 220,
                    "symbol": "_publish",
                }
            ],
            "diagram": {
                "source_kind": "excalidraw",
                "source_path": (
                    "docs/explain/boards/publish-flow.excalidraw"
                ),
                "node_ids": [
                    "staging",
                    "verify",
                    "publish-report",
                ],
                "rendered_svg_path": (
                    "docs/explain/svg/publish-flow.svg"
                ),
                "editable": True,
                "compiled_by": "ops-excalidraw -> create-svg",
                "sha256": "sha256:fixture",
            },
            "debugger_stops": [
                {
                    "file": "src/anonymization_trial/pipeline.py",
                    "line": 210,
                    "locals": [
                        "tmp",
                        "report_path",
                        "output_corpus",
                    ],
                    "watches": [],
                    "proves": (
                        "The final readiness report has not "
                        "been published yet."
                    ),
                }
            ],
            "proof_boundary": (
                "Explains local publication ordering, "
                "not distributed transaction safety."
            ),
            "confidence": "medium",
            "steps": [
                {
                    "step_id": "staging",
                    "title": "Crash-safe staging",
                    "bullets": [
                        "Write into a staging directory first.",
                        (
                            "Do not publish READY while "
                            "outputs are partial."
                        ),
                    ],
                    "source_range_index": 0,
                    "source_explanation": (
                        "_publish keeps incomplete outputs "
                        "away from the final report."
                    ),
                    "debugger_stop_index": 0,
                    "diagram_node_ids": ["staging"],
                    "proof_boundary": (
                        "Local filesystem ordering only."
                    ),
                    "confidence": "medium",
                },
                {
                    "step_id": "verify",
                    "title": "Verify before publish",
                    "bullets": [
                        (
                            "Run deterministic checks before "
                            "the final rename."
                        ),
                        (
                            "Treat failed checks as quarantine, "
                            "not success."
                        ),
                    ],
                    "source_range_index": 0,
                    "source_explanation": (
                        "The verification branch decides "
                        "whether publish may continue."
                    ),
                    "debugger_stop_index": 0,
                    "diagram_node_ids": ["verify"],
                    "proof_boundary": (
                        "Does not prove distributed "
                        "transaction safety."
                    ),
                    "confidence": "medium",
                },
                {
                    "step_id": "report-last",
                    "title": "Report is last",
                    "bullets": [
                        (
                            "The final report is the "
                            "readiness signal."
                        ),
                        (
                            "If it is absent, the release "
                            "is incomplete."
                        ),
                    ],
                    "source_range_index": 0,
                    "source_explanation": (
                        "The final report path is renamed "
                        "after data artifacts exist."
                    ),
                    "debugger_stop_index": 0,
                    "diagram_node_ids": ["publish-report"],
                    "proof_boundary": (
                        "Report-last proves local "
                        "readiness semantics."
                    ),
                    "confidence": "high",
                },
            ],
        }
    )


def write_sample(path: Path) -> None:
    """Write one strict JSONL sample record."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        sample_record().model_dump_json(by_alias=True) + "\n",
        encoding="utf-8",
    )
