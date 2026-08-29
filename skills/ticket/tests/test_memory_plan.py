"""Tests for deterministic ticket Memory concept and query-plan compilation."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
CLI = SKILL_DIR / "scripts" / "ticket_cli.py"


def _ticket_body(
    *,
    route: str = "backend_python_or_skill_runtime",
    outcome: str = "Add the compiler.",
    target: str = "skills/ticket",
    target_paths: tuple[str, ...] = ("skills/ticket/SKILL.md", "skills/ticket/scripts/ticket_cli.py"),
    marker_extra: str = "",
) -> str:
    rendered_target_paths = "\n".join(f"- {path}" for path in target_paths)
    return f"""## Type

feature

## Target

{target}

## Target paths

{rendered_target_paths}

## Current state

Ticket workers invent Memory query text independently.

## Requested outcome

{outcome}

## Required proof

Run `skills/ticket/run.sh memory-plan 1362 --repo grahama1970/agent-skills --json` and read back `proof-summary.json`.

## Route

{route}

## Requested repair agent

agent-skill-maintainer

## Non-goals

No Memory retrieval execution.

## Required repository context

- `skills/ticket/SKILL.md`

## Required skills

- `ticket`
- `memory`

## Dependencies

- blocked-by: grahama1970/graph-memory-operator#112

<!-- ticket-skill
type: feature
target: {target}
{marker_extra}route: {route}
agent: agent-skill-maintainer
context_files: skills/ticket/SKILL.md
required_skills: ticket,memory
depends_on: grahama1970/graph-memory-operator#112
memory_recipe: ticket-repair-context-v1
memory_symbols: DiagramNode
memory_identifiers: binding_paths
memory_anchors: ticket context compiler
-->
"""


def _run_memory_plan_proc(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    body_file = tmp_path / "issue.md"
    body_file.write_text(body, encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(CLI),
            "memory-plan",
            "--body-file",
            str(body_file),
            "--repo",
            "grahama1970/agent-skills",
            "--json",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _run_plan(tmp_path: Path, body: str) -> dict:
    proc = _run_memory_plan_proc(tmp_path, body)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _run_plan_fail(tmp_path: Path, body: str, expected: str) -> None:
    proc = _run_memory_plan_proc(tmp_path, body)
    assert proc.returncode != 0, proc.stdout
    assert expected in proc.stderr


def test_memory_plan_is_byte_identical_for_same_body(tmp_path: Path) -> None:
    body = _ticket_body()
    first = _run_plan(tmp_path, body)
    second = _run_plan(tmp_path, body)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["schema"] == "ticket.memory_query_plan.v1"
    assert first["concepts"]["schema"] == "ticket.memory_concepts.v1"
    assert first["concepts"]["skill_id"] == "ticket"
    assert first["github_mutation"] is False
    assert first["memory_retrieval_executed"] is False
    assert first["seam_validation"]["status"] == "PASS"


def test_memory_plan_rejects_unsafe_skill_targets(tmp_path: Path) -> None:
    unsafe_targets = {
        "skills/ticket,skills/project-watchdog": "unsafe_multi_target",
        "/home/graham/workspace/experiments/agent-skills/skills/ticket": "unsafe_absolute_target",
        "../skills/ticket": "unsafe_traversal_target",
        "skills/*": "unsafe_glob_target",
        ".": "unsafe_broad_target",
    }
    for target, expected in unsafe_targets.items():
        _run_plan_fail(tmp_path, _ticket_body(target=target, target_paths=(target,)), expected)


def test_memory_plan_rejects_cross_skill_target_paths(tmp_path: Path) -> None:
    body = _ticket_body(
        target="skills/ticket",
        target_paths=("skills/ticket", "skills/project-watchdog"),
    )
    _run_plan_fail(tmp_path, body, "unsafe_multi_skill_target")


def test_memory_plan_rejects_marker_skill_id_mismatch(tmp_path: Path) -> None:
    body = _ticket_body(marker_extra="skill_id: project-watchdog\n")
    _run_plan_fail(tmp_path, body, "skill_id_mismatch")


def test_memory_plan_digest_changes_when_outcome_changes(tmp_path: Path) -> None:
    first = _run_plan(tmp_path, _ticket_body(outcome="Add the compiler."))
    second = _run_plan(tmp_path, _ticket_body(outcome="Add a different compiler."))
    assert first["issue_body_sha256"] != second["issue_body_sha256"]
    assert first["concepts_sha256"] != second["concepts_sha256"]
    assert first["plan_sha256"] != second["plan_sha256"]


def test_code_route_includes_code_entry_and_symbol_enables_impact(tmp_path: Path) -> None:
    plan = _run_plan(tmp_path, _ticket_body())
    effective = {step["id"]: step for step in plan["effective_steps"]}
    assert "target-code-entry" in effective
    assert "bounded-impact" in effective
    assert effective["bounded-impact"]["selectors"]["symbols"] == ["DiagramNode"]
    assert plan["concepts"]["target_paths"] == [
        "skills/ticket/SKILL.md",
        "skills/ticket/scripts/ticket_cli.py",
    ]


def test_documentation_route_does_not_invent_code_traversal(tmp_path: Path) -> None:
    plan = _run_plan(tmp_path, _ticket_body(route="documentation_or_report"))
    effective_ids = {step["id"] for step in plan["effective_steps"]}
    skipped_ids = {step["id"] for step in plan["skipped_steps"]}
    assert "target-code-entry" not in effective_ids
    assert "target-code-entry" in skipped_ids


def test_human_first_ticket_with_recipe_fails_closed(tmp_path: Path) -> None:
    body = _ticket_body(route="documentation_or_report").replace("type: feature", "type: question")
    body_file = tmp_path / "question.md"
    body_file.write_text(body, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(CLI), "memory-plan", "--body-file", str(body_file), "--json"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode != 0
    assert "human-first tickets cannot become dispatchable" in proc.stderr


def test_compact_memory_marker_fields_are_emitted() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "feature",
            "memory plan",
            "--target",
            "skills/ticket",
            "--limitation",
            "missing plan",
            "--capability",
            "emit plan",
            "--workflow",
            "worker previews plan",
            "--acceptance",
            "plan has symbols",
            "--proof",
            "skills/agentic-evals/run.sh run skills/ticket/fixtures/agentic_eval.json --case skill-target-memory-plan --output /tmp/ticket_eval.json shows READY; ./run.sh sanity-live.sh --allow-live then read back receipt.json",
            "--route",
            "backend_python_or_skill_runtime",
            "--memory-recipe",
            "ticket-repair-context-v1",
            "--memory-symbol",
            "DiagramNode",
            "--memory-identifier",
            "binding_paths",
            "--memory-anchor",
            "ticket context compiler",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    assert "skill_id: ticket" in proc.stdout
    assert "memory_recipe: ticket-repair-context-v1" in proc.stdout
    assert "memory_symbols: DiagramNode" in proc.stdout
    assert "memory_identifiers: binding_paths" in proc.stdout
    assert "memory_anchors: ticket context compiler" in proc.stdout
