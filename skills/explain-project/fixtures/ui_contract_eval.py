#!/usr/bin/env python3
"""Static React contract gate for explain-project UI source."""

from __future__ import annotations

import re
from pathlib import Path


INTERACTIVE = re.compile(
    r"<(button|input|textarea|select)\b(?P<attrs>[^>]*)>",
    re.DOTALL,
)

STATIC_QID = re.compile(
    r'data-qid="([^"]+)"'
)


def require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    root = (
        Path(__file__).resolve().parents[1]
        / "ui"
        / "src"
    )

    tsx_files = sorted(
        root.rglob("*.tsx")
    )

    require(
        bool(tsx_files),
        "no TSX files found",
    )

    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in tsx_files
    )

    for path in tsx_files:
        text = path.read_text(
            encoding="utf-8"
        )

        for match in INTERACTIVE.finditer(text):
            attrs = match.group("attrs")

            for required in (
                "data-qid=",
                "data-qs-action=",
                "title=",
            ):
                require(
                    required in attrs,
                    (
                        f"{path}: "
                        f"<{match.group(1)}> "
                        f"missing {required}"
                    ),
                )

        for qid in STATIC_QID.findall(text):
            require(
                f"element_id: '{qid}'" in combined,
                (
                    f"{path}: {qid} lacks "
                    "useRegisterAction registration"
                ),
            )

    input_rail = (
        root
        / "components"
        / "InputRail.tsx"
    ).read_text(
        encoding="utf-8"
    )

    teleprompter = (
        root
        / "components"
        / "TeleprompterStage.tsx"
    ).read_text(
        encoding="utf-8"
    )

    evidence = (
        root
        / "components"
        / "EvidenceRail.tsx"
    ).read_text(
        encoding="utf-8"
    )

    diagram = (
        root
        / "components"
        / "DiagramStage.tsx"
    ).read_text(
        encoding="utf-8"
    )

    health = (
        root
        / "components"
        / "IntegrationHealth.tsx"
    ).read_text(
        encoding="utf-8"
    )

    hook = (
        root
        / "useRegisterAction.ts"
    ).read_text(
        encoding="utf-8"
    )

    keys = (
        root
        / "useCockpit.ts"
    ).read_text(
        encoding="utf-8"
    )

    require(
        (
            "function ExplainerButton"
            in input_rail
            and "useRegisterAction({"
            in input_rail
        ),
        (
            "dynamic explainer action is not "
            "registered in a child component"
        ),
    )

    require(
        "useRegisterAction({" in teleprompter,
        "teleprompter actions are not registered",
    )

    require(
        "useRegisterAction({" in evidence,
        "evidence actions are not registered",
    )

    require(
        (
            "data-active={isActive ? 'true' : 'false'}"
            in diagram
            and "data-diagram-diagnostic=\"missing-node\""
            in diagram
            and "mutation_allowed=false"
            in diagram
        ),
        "diagram stage lacks revision-driven highlight diagnostics",
    )

    require(
        (
            "state.integration_health.live_evidence" in health
            and "state.integration_health.source_reveal" in health
            and "state.integration_health.debugger_target" in health
            and "state.integration_health.diagram" in health
        ),
        "integration health component does not read typed state",
    )

    require(
        (
            "useEffect(() =>" in hook
            and "useRegisterAction" in hook
        ),
        (
            "registration hook is not "
            "top-level useEffect based"
        ),
    )

    require(
        (
            "ArrowRight" in keys
            and "dispatch('step.next')" in keys
        ),
        "ArrowRight is not mapped to step.next",
    )

    require(
        (
            "ArrowLeft" in keys
            and "dispatch('step.previous')" in keys
        ),
        "ArrowLeft is not mapped to step.previous",
    )

    require(
        (
            "debugger.prepare" not in keys
            and "source.reveal" not in keys
        ),
        (
            "keyboard hook contains "
            "external adapter actions"
        ),
    )

    for path in tsx_files:
        text = path.read_text(
            encoding="utf-8"
        )

        map_index = text.find(".map((")

        if map_index >= 0:
            require(
                (
                    "useRegisterAction"
                    not in text[
                        map_index:
                        map_index + 220
                    ]
                ),
                (
                    f"{path}: possible hook "
                    "call inside map"
                ),
            )

    print(
        "EXPLAIN_PROJECT_UI_CONTRACT_EVAL_OK"
    )


if __name__ == "__main__":
    main()
