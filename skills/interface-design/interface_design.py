#!/usr/bin/env python3
"""Receipt-backed interface-design pipeline scaffold.

This controller deliberately does not call model providers or mutate a target
application.  It creates and maintains the durable run contract consumed by the
project agent, search skills, Scillm workers, Loop nodes, browser review, and the
human approval gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "interface_design.run.v1"
TERMINAL_STATES = {"PASS", "NEEDS_CHANGES", "BLOCKED", "SKIPPED"}
NODE_STATES = {"PENDING", "RUNNING", *TERMINAL_STATES}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return value[:72] or "interface"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def ensure_empty_output(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise ValueError(f"output directory is not empty: {path}")
    path.mkdir(parents=True, exist_ok=True)


def parse_csv(value: str) -> list[str]:
    return list(dict.fromkeys(part.strip() for part in value.split(",") if part.strip()))


def normalize_viewports(values: Iterable[str]) -> list[dict[str, int]]:
    parsed: list[dict[str, int]] = []
    for value in values:
        match = re.fullmatch(r"(\d{3,5})x(\d{3,5})", value.strip().lower())
        if not match:
            raise ValueError(f"invalid viewport {value!r}; expected WIDTHxHEIGHT")
        parsed.append({"width": int(match.group(1)), "height": int(match.group(2))})
    return parsed


def research_queries(surface: str) -> dict[str, Any]:
    human_surface = surface.replace("-", " ")
    return {
        "schema": "interface_design.research_queries.v1",
        "surface": surface,
        "github": [
            {"id": "gh-product", "query": f'"{human_surface}" React Tailwind shadcn open source'},
            {"id": "gh-operator-chat", "query": "operator chat artifact inspector React"},
            {"id": "gh-agent-runs", "query": "AI agent chat run card timeline React"},
            {"id": "gh-evidence", "query": "evidence review chat interface React Tailwind"},
            {"id": "gh-d3-inspector", "query": "chat interface D3 graph inspector React"},
        ],
        "brave": [
            {"id": "brave-product", "query": f'best modern "{human_surface}" interface examples'},
            {"id": "brave-open-source", "query": f'open source "{human_surface}" UX'},
            {"id": "brave-operator-chat", "query": "operator chat interface artifact inspector"},
            {"id": "brave-agent-runs", "query": "AI agent run card chat UX"},
            {"id": "brave-github", "query": f'site:github.com "{human_surface}" shadcn'},
        ],
        "execution": {
            "github_skill": "skills/github-search/run.sh",
            "brave_skill": "skills/brave-search/run.sh",
            "parallel": True,
            "preserve_raw_receipts": True,
        },
    }


def reference_rubric() -> dict[str, Any]:
    return {
        "schema": "interface_design.reference_rubric.v1",
        "dimensions": {
            "workflow_relevance": 25,
            "interaction_quality": 20,
            "visual_hierarchy": 15,
            "implementation_evidence": 15,
            "accessibility_evidence": 10,
            "component_reusability": 10,
            "license_clarity": 5,
        },
        "hard_rejects": [
            "license or provenance cannot be established",
            "reference is only a marketing screenshot with no usable workflow evidence",
            "reference encourages dashboard-first chat or fake operational metrics",
            "candidate would require copying branded product chrome",
        ],
        "selection_rule": "shortlist 6-12 references; extract patterns, not product chrome",
    }


def mockup_rubric() -> dict[str, Any]:
    return {
        "schema": "interface_design.mockup_review_rubric.v1",
        "dimensions": {
            "task_and_product_fit": 20,
            "information_hierarchy": 15,
            "primary_action_clarity": 10,
            "chat_first_structure": 10,
            "structured_operational_objects": 10,
            "visual_polish": 10,
            "accessibility_and_focus": 10,
            "responsive_behavior": 5,
            "implementation_feasibility": 5,
            "originality_without_cloning": 5,
        },
        "hard_rejects": [
            "dashboard theater or generic SaaS chrome",
            "primary user job is not obvious in the first viewport",
            "reference product chrome is copied",
            "required interaction state is absent",
            "keyboard focus or readable contrast is absent",
            "review is based on HTML text without fresh rendered screenshots",
        ],
        "review_output": {
            "verdict": ["PASS", "NEEDS_CHANGES", "BLOCKED", "INSUFFICIENT_EVIDENCE"],
            "required_fields": [
                "score",
                "dimension_scores",
                "blocking_findings",
                "repair_instructions",
                "evidence_screenshots",
                "missing_evidence",
            ],
        },
    }


def implementation_rubric() -> dict[str, Any]:
    return {
        "schema": "interface_design.implementation_review_rubric.v1",
        "dimensions": {
            "deterministic_checks": 20,
            "visual_fidelity_to_selected_mockup": 20,
            "reuse_of_existing_components": 15,
            "interaction_correctness": 10,
            "accessibility": 10,
            "code_quality_and_scope": 10,
            "responsive_behavior": 5,
            "performance": 5,
            "d3_or_svg_correctness_when_applicable": 5,
        },
        "hard_rejects": [
            "build, typecheck, lint, or required tests fail",
            "changed files escape the allowed globs",
            "candidate invents backend data or fake operational state",
            "candidate ignores the component inventory without a recorded reason",
            "interaction path is not exercised by test-interactions",
            "visual verdict lacks fresh screenshots",
        ],
        "selection_rule": "deterministic gates first; reviewer score breaks ties among passing candidates",
    }


def component_inventory_template(target_repo: str) -> dict[str, Any]:
    return {
        "schema": "interface_design.component_inventory.v1",
        "target_repo": target_repo,
        "status": "PENDING",
        "package_manager": None,
        "frameworks": {"react": None, "tailwind": None, "shadcn": None, "d3": None},
        "design_tokens": [],
        "routes": [],
        "components": [],
        "shadcn_registry": [],
        "d3_visualizations": [],
        "stories_or_examples": [],
        "test_commands": [],
        "build_commands": [],
        "reusable_for_selected_mockup": [],
        "gaps": [],
        "evidence": [],
    }


def build_nodes(mockup_lanes: list[str], implementation_lanes: list[str]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = [
        {"id": "brief.normalize", "kind": "controller", "depends_on": []},
        {"id": "research.github", "kind": "github-search", "depends_on": ["brief.normalize"]},
        {"id": "research.brave", "kind": "brave-search", "depends_on": ["brief.normalize"]},
        {"id": "research.rank", "kind": "reviewer", "depends_on": ["research.github", "research.brave"]},
    ]
    for lane in mockup_lanes:
        nodes.extend(
            [
                {"id": f"mockup.generate.{lane}", "kind": "scillm-designer", "depends_on": ["research.rank"], "lane": lane},
                {"id": f"mockup.render.{lane}", "kind": "surf", "depends_on": [f"mockup.generate.{lane}"], "lane": lane},
                {"id": f"mockup.review.{lane}", "kind": "review-design", "depends_on": [f"mockup.render.{lane}"], "lane": lane},
            ]
        )
    nodes.append(
        {
            "id": "mockup.select",
            "kind": "reviewer-join",
            "depends_on": [f"mockup.review.{lane}" for lane in mockup_lanes],
        }
    )
    nodes.append({"id": "components.inventory", "kind": "repo-inventory", "depends_on": ["mockup.select"]})
    for lane in implementation_lanes:
        nodes.extend(
            [
                {"id": f"implementation.loop.{lane}", "kind": "loop", "depends_on": ["components.inventory"], "lane": lane},
                {"id": f"implementation.interactions.{lane}", "kind": "test-interactions", "depends_on": [f"implementation.loop.{lane}"], "lane": lane},
                {"id": f"implementation.render.{lane}", "kind": "surf", "depends_on": [f"implementation.interactions.{lane}"], "lane": lane},
                {"id": f"implementation.review.{lane}", "kind": "review-design", "depends_on": [f"implementation.render.{lane}"], "lane": lane},
            ]
        )
    nodes.extend(
        [
            {
                "id": "implementation.select",
                "kind": "reviewer-join",
                "depends_on": [f"implementation.review.{lane}" for lane in implementation_lanes],
            },
            {"id": "human.approval", "kind": "human-gate", "depends_on": ["implementation.select"]},
        ]
    )
    for node in nodes:
        node["state"] = "PENDING"
        node["artifacts"] = []
        node["updated_at"] = None
    return nodes


def candidate_lanes(names: list[str], kind: str) -> list[dict[str, Any]]:
    if kind == "mockup":
        roles = {
            "claude": "visual hierarchy, editorial restraint, and calm density",
            "openai": "implementation-realistic product workflow and interaction detail",
            "gemini": "alternate visual direction and modern interaction patterns",
            "opencode-kimi": "information architecture, state mechanics, and structural critique",
        }
        return [
            {
                "id": name,
                "worker": "skills/oc-subagent/personas/designer/persona.yaml",
                "role": roles.get(name, "independent interface-design candidate"),
                "writes": [f"mockups/candidates/{name}/**"],
            }
            for name in names
        ]
    strategies = {
        "reuse-first": "maximize reuse of existing React/Tailwind/shadcn/D3 components",
        "composition-first": "compose the selected mockup with the smallest maintainable component boundary",
        "accessibility-first": "prioritize keyboard flow, semantics, responsive behavior, and reduced-motion support",
    }
    return [
        {
            "id": name,
            "worker": "skills/oc-subagent/personas/coder/persona.yaml",
            "reviewers": [
                "skills/oc-subagent/personas/code-reviewer/persona.yaml",
                "skills/oc-subagent/personas/designer/persona.yaml",
                "skills/oc-subagent/personas/qa-tester/persona.yaml",
            ],
            "strategy": strategies.get(name, "independent implementation strategy"),
            "worktree_required": True,
        }
        for name in names
    ]


def run_readme(surface: str, target_repo: str) -> str:
    return f"""# Interface-design run: {surface}

This directory is a durable orchestration receipt. It does not imply that a
mockup or production interface has passed review.

## Execution order

1. Run `research.github` and `research.brave` concurrently using the query pack.
2. Normalize raw results into `research/reference-candidates.json` and rank a
   6–12 item shortlist. Preserve URL, repository, license, screenshot, patterns,
   risks, and source receipts.
3. Generate independent static HTML/CSS candidates, render every candidate at
   every configured viewport, and send the screenshots to a read-only design
   reviewer.
4. Repair only the top candidates in bounded outer-DAG rounds. A text/DOM check
   is not a visual PASS.
5. Select one static direction or write a hybrid plan.
6. Inventory the existing React/Tailwind/shadcn/D3 surface in `{target_repo}`.
7. Build implementation competitors in isolated worktrees. Each lane must use
   `$loop` for one bounded code artifact, deterministic checks, and code review.
8. Run `$test-interactions`, capture fresh screenshots, and run `$review-design`
   after each passing code loop.
9. Compare only candidates that passed deterministic gates; stop at the human
   approval and merge gate.

## Controller commands

```bash
skills/interface-design/run.sh status --run .
skills/interface-design/run.sh record --run . --node research.github --state RUNNING
skills/interface-design/run.sh record --run . --node research.github --state PASS \\
  --artifact research/github-results.json
skills/interface-design/run.sh validate --run .
```
"""


def init_run(args: argparse.Namespace) -> int:
    brief_path = args.brief.resolve()
    if not brief_path.is_file():
        raise ValueError(f"brief does not exist: {brief_path}")
    brief_text = brief_path.read_text(encoding="utf-8")
    output = args.output.resolve()
    ensure_empty_output(output)

    mockup_lanes = parse_csv(args.mockup_lanes)
    implementation_lanes = parse_csv(args.implementation_lanes)
    if len(mockup_lanes) < 2:
        raise ValueError("mockup bakeoff requires at least two lanes")
    if len(implementation_lanes) < 2:
        raise ValueError("implementation bakeoff requires at least two lanes")

    viewports = normalize_viewports(args.viewport or ["1440x1024", "390x844"])
    surface = slugify(args.surface)
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{surface}"

    for directory in [
        "brief",
        "research/raw/github",
        "research/raw/brave",
        "mockups/candidates",
        "mockups/screenshots",
        "mockups/reviews",
        "mockups/repair-rounds",
        "components",
        "implementation/candidates",
        "implementation/screenshots",
        "implementation/reviews",
        "implementation/loop-receipts",
        "status",
        "final",
    ]:
        (output / directory).mkdir(parents=True, exist_ok=True)

    (output / "brief" / "design-brief.md").write_text(brief_text, encoding="utf-8")
    (output / "README.md").write_text(run_readme(surface, args.target_repo), encoding="utf-8")

    request = {
        "schema": "interface_design.request.v1",
        "run_id": run_id,
        "created_at": utc_now(),
        "surface": surface,
        "persona": args.persona,
        "target_repo": args.target_repo,
        "brief": "brief/design-brief.md",
        "brief_sha256": sha256_text(brief_text),
        "viewports": viewports,
        "mockup_lanes": mockup_lanes,
        "implementation_lanes": implementation_lanes,
        "max_mockup_repair_rounds": args.max_mockup_repair_rounds,
        "max_implementation_repair_rounds": args.max_implementation_repair_rounds,
        "human_gate_required": True,
        "auto_merge": False,
    }
    write_json(output / "request.json", request)

    pipeline = {
        "schema": SCHEMA_VERSION,
        "run_id": run_id,
        "surface": surface,
        "state": "RUNNING",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "nodes": build_nodes(mockup_lanes, implementation_lanes),
        "stop_rules": [
            "stop BLOCKED when search credentials, target repository, renderer, or deterministic checks are unavailable",
            "stop NEEDS_CHANGES when bounded repair rounds are exhausted",
            "never infer a visual PASS from HTML, DOM text, or model prose without fresh screenshots",
            "never merge or promote a production candidate without the human.approval node",
        ],
    }
    write_json(output / "pipeline.json", pipeline)
    write_json(output / "research" / "queries.json", research_queries(surface))
    write_json(output / "research" / "reference-rubric.json", reference_rubric())
    write_json(
        output / "research" / "reference-candidates.json",
        {"schema": "interface_design.reference_candidates.v1", "status": "PENDING", "candidates": []},
    )
    write_json(
        output / "research" / "reference-shortlist.json",
        {"schema": "interface_design.reference_shortlist.v1", "status": "PENDING", "selected": [], "rejected": []},
    )
    write_json(
        output / "mockups" / "lanes.json",
        {"schema": "interface_design.mockup_lanes.v1", "lanes": candidate_lanes(mockup_lanes, "mockup")},
    )
    write_json(output / "mockups" / "review-rubric.json", mockup_rubric())
    write_json(
        output / "mockups" / "selection.json",
        {"schema": "interface_design.mockup_selection.v1", "status": "PENDING", "winner": None, "hybrid_plan": None},
    )
    write_json(output / "components" / "inventory.json", component_inventory_template(args.target_repo))
    write_json(
        output / "implementation" / "lanes.json",
        {"schema": "interface_design.implementation_lanes.v1", "lanes": candidate_lanes(implementation_lanes, "implementation")},
    )
    write_json(output / "implementation" / "review-rubric.json", implementation_rubric())
    write_json(
        output / "final" / "decision.json",
        {
            "schema": "interface_design.final_decision.v1",
            "status": "PENDING",
            "winner": None,
            "human_approval": None,
            "merge_authorized": False,
            "evidence": [],
        },
    )
    append_jsonl(
        output / "status" / "status.jsonl",
        {
            "ts": utc_now(),
            "event": "run_initialized",
            "run_id": run_id,
            "surface": surface,
            "next_nodes": ["brief.normalize"],
        },
    )
    print(json.dumps({"ok": True, "run_id": run_id, "run_dir": str(output)}, indent=2))
    return 0


def load_pipeline(run_dir: Path) -> dict[str, Any]:
    pipeline_path = run_dir / "pipeline.json"
    if not pipeline_path.is_file():
        raise ValueError(f"not an interface-design run: {run_dir}")
    pipeline = read_json(pipeline_path)
    if pipeline.get("schema") != SCHEMA_VERSION:
        raise ValueError(f"unsupported pipeline schema: {pipeline.get('schema')}")
    return pipeline


def node_map(pipeline: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node["id"]: node for node in pipeline.get("nodes", [])}


def ready_nodes(pipeline: dict[str, Any]) -> list[str]:
    nodes = node_map(pipeline)
    ready: list[str] = []
    for node in nodes.values():
        if node["state"] != "PENDING":
            continue
        dependencies = [nodes[dependency]["state"] for dependency in node.get("depends_on", [])]
        if all(state in {"PASS", "SKIPPED"} for state in dependencies):
            ready.append(node["id"])
    return ready


def summarize(run_dir: Path, pipeline: dict[str, Any]) -> dict[str, Any]:
    counts = {state: 0 for state in sorted(NODE_STATES)}
    for node in pipeline["nodes"]:
        counts[node["state"]] = counts.get(node["state"], 0) + 1
    blocked = [node["id"] for node in pipeline["nodes"] if node["state"] == "BLOCKED"]
    active = [node["id"] for node in pipeline["nodes"] if node["state"] == "RUNNING"]
    return {
        "schema": "interface_design.status.v1",
        "run_id": pipeline["run_id"],
        "run_dir": str(run_dir),
        "state": pipeline["state"],
        "counts": counts,
        "active_nodes": active,
        "ready_nodes": ready_nodes(pipeline),
        "blocked_nodes": blocked,
    }


def status_run(args: argparse.Namespace) -> int:
    run_dir = args.run.resolve()
    pipeline = load_pipeline(run_dir)
    print(json.dumps(summarize(run_dir, pipeline), indent=2))
    return 0


def record_node(args: argparse.Namespace) -> int:
    run_dir = args.run.resolve()
    pipeline = load_pipeline(run_dir)
    nodes = node_map(pipeline)
    if args.node not in nodes:
        raise ValueError(f"unknown node: {args.node}")
    state = args.state.upper()
    if state not in NODE_STATES:
        raise ValueError(f"invalid state {state}; expected one of {sorted(NODE_STATES)}")

    node = nodes[args.node]
    if state in {"RUNNING", "PASS"}:
        unmet = [
            dependency
            for dependency in node.get("depends_on", [])
            if nodes[dependency]["state"] not in {"PASS", "SKIPPED"}
        ]
        if unmet:
            raise ValueError(
                f"node {args.node} cannot enter {state}; unmet dependencies: {unmet}"
            )
    if args.node == "human.approval" and state == "PASS" and not args.artifact:
        raise ValueError("human.approval PASS requires an approval receipt artifact")

    prior = node["state"]
    node["state"] = state
    node["updated_at"] = utc_now()
    node["artifacts"] = list(dict.fromkeys([*node.get("artifacts", []), *args.artifact]))
    if args.note:
        node["note"] = args.note

    states = {entry["state"] for entry in pipeline["nodes"]}
    if "BLOCKED" in states:
        pipeline["state"] = "BLOCKED"
    elif all(entry["state"] in {"PASS", "SKIPPED"} for entry in pipeline["nodes"]):
        pipeline["state"] = "PASS"
    elif "NEEDS_CHANGES" in states and not any(entry["state"] == "RUNNING" for entry in pipeline["nodes"]):
        pipeline["state"] = "NEEDS_CHANGES"
    else:
        pipeline["state"] = "RUNNING"
    pipeline["updated_at"] = utc_now()
    write_json(run_dir / "pipeline.json", pipeline)
    append_jsonl(
        run_dir / "status" / "status.jsonl",
        {
            "ts": utc_now(),
            "event": "node_state_changed",
            "node": args.node,
            "prior_state": prior,
            "state": state,
            "actor": args.actor,
            "artifacts": args.artifact,
            "note": args.note or None,
        },
    )
    print(json.dumps(summarize(run_dir, pipeline), indent=2))
    return 0


def validate_run(args: argparse.Namespace) -> int:
    run_dir = args.run.resolve()
    errors: list[str] = []
    required = [
        "README.md",
        "request.json",
        "pipeline.json",
        "brief/design-brief.md",
        "research/queries.json",
        "research/reference-rubric.json",
        "research/reference-candidates.json",
        "research/reference-shortlist.json",
        "mockups/lanes.json",
        "mockups/review-rubric.json",
        "mockups/selection.json",
        "components/inventory.json",
        "implementation/lanes.json",
        "implementation/review-rubric.json",
        "final/decision.json",
        "status/status.jsonl",
    ]
    for relative in required:
        if not (run_dir / relative).exists():
            errors.append(f"missing {relative}")
    try:
        pipeline = load_pipeline(run_dir)
    except (ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
        pipeline = None
    if pipeline:
        ids = [node.get("id") for node in pipeline.get("nodes", [])]
        if len(ids) != len(set(ids)):
            errors.append("pipeline node ids are not unique")
        known = set(ids)
        for node in pipeline.get("nodes", []):
            unknown = set(node.get("depends_on", [])) - known
            if unknown:
                errors.append(f"node {node.get('id')} has unknown dependencies: {sorted(unknown)}")
            if node.get("state") not in NODE_STATES:
                errors.append(f"node {node.get('id')} has invalid state {node.get('state')}")
    payload = {"ok": not errors, "run_dir": str(run_dir), "errors": errors}
    print(json.dumps(payload, indent=2))
    return 0 if not errors else 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Create and maintain an interface-design pipeline run.")
    commands = root.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Create a new pipeline run directory.")
    init.add_argument("--brief", type=Path, required=True)
    init.add_argument("--surface", required=True)
    init.add_argument("--target-repo", required=True)
    init.add_argument("--output", type=Path, required=True)
    init.add_argument("--persona", default="margaret-chen")
    init.add_argument("--mockup-lanes", default="claude,openai,gemini,opencode-kimi")
    init.add_argument("--implementation-lanes", default="reuse-first,composition-first,accessibility-first")
    init.add_argument("--viewport", action="append", default=[])
    init.add_argument("--max-mockup-repair-rounds", type=int, default=2)
    init.add_argument("--max-implementation-repair-rounds", type=int, default=3)
    init.set_defaults(func=init_run)

    status = commands.add_parser("status", help="Print current run status.")
    status.add_argument("--run", type=Path, required=True)
    status.set_defaults(func=status_run)

    record = commands.add_parser("record", help="Record a node state transition and artifacts.")
    record.add_argument("--run", type=Path, required=True)
    record.add_argument("--node", required=True)
    record.add_argument("--state", required=True)
    record.add_argument("--artifact", action="append", default=[])
    record.add_argument("--actor", default="project-agent")
    record.add_argument("--note", default="")
    record.set_defaults(func=record_node)

    validate = commands.add_parser("validate", help="Validate run artifacts and DAG references.")
    validate.add_argument("--run", type=Path, required=True)
    validate.set_defaults(func=validate_run)
    return root


def main() -> int:
    try:
        args = parser().parse_args()
        return int(args.func(args))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
