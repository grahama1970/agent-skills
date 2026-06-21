#!/usr/bin/env python3
"""Compile durable phase plans and $loop nodes for interface-design-pipeline."""
from __future__ import annotations

import copy
import shlex
import sys
from pathlib import Path
from typing import Any

from pipeline_common import (
    PHASES,
    REPO_ROOT,
    RECEIPT_SCHEMA,
    SKILL_DIR,
    append_event,
    compact_utc,
    path_for_node,
    read_json,
    render_brief,
    resolve_manifest_path,
    slug,
    utc_now,
    validate_manifest,
    write_json,
)


def research_lanes(manifest: dict[str, Any], run_dir: Path) -> list[dict[str, Any]]:
    config = manifest["research"]
    lanes: list[dict[str, Any]] = []
    for source, queries in (("github", config["github_queries"]), ("brave", config["brave_queries"])):
        for index, query in enumerate(queries, 1):
            lane_id = f"{source}-{index:02d}"
            argv = (
                ["skills/github-search/run.sh", "search", query, "--limit", str(config.get("github_limit", 8)), "--deep", "--json"]
                if source == "github"
                else [sys.executable, "skills/brave-search/brave_search.py", "web", query, "--count", str(config.get("brave_count", 10)), "--json"]
            )
            lanes.append({
                "id": lane_id,
                "source": source,
                "query": query,
                "required": source in config.get("required_sources", ["github", "brave"]),
                "argv": argv,
                "artifact_dir": path_for_node(run_dir / "phases/01-research/raw" / lane_id),
            })
    return lanes


def mockup_node(manifest: dict[str, Any], run_dir: Path, competitor: dict[str, Any]) -> dict[str, Any]:
    cfg = manifest["mockups"]
    candidate = run_dir / "phases/03-mockup-tournament/candidates" / competitor["id"]
    candidate_rel = path_for_node(candidate)
    check = [sys.executable, "skills/interface-design-pipeline/scripts/check_artifact.py", "mockup", "--path", f"{candidate_rel}/index.html", "--screenshot", f"{candidate_rel}/screenshot.png"]
    for state in cfg.get("required_states", []):
        check += ["--required-text", state]
    for term in manifest["surface"].get("forbidden_ui_terms", []):
        check += ["--forbid", term]
    return {
        "node_type": "loop",
        "node_id": f"mockup_{slug(competitor['id'])}",
        "objective": (
            f"Build the {competitor['id']} HTML/CSS candidate. Strategy: {competitor['strategy']}\n"
            f"Read {path_for_node(run_dir / 'brief.md')} and the research/reference packets. "
            f"Write index.html, screenshot.png, rationale.md, and states.md only under {candidate_rel}. "
            "Use interface-designer; interface-reviewer is read-only."
        ),
        "allowed_globs": [f"{candidate_rel}/**"],
        "required_changed_globs": [f"{candidate_rel}/index.html"],
        "checks": [shlex.join(check)],
        "max_attempts": int(cfg.get("max_rounds", 3)),
        "check_timeout": int(cfg.get("check_timeout", 180)),
        "agent_config": str(SKILL_DIR / "examples/agents.mockup.toml"),
        "run_root": f"{path_for_node(run_dir / 'loop-runs')}/mockups/{competitor['id']}",
        "require_clean": False,
        "worktree": {"mode": "existing"},
    }


def implementation_node(manifest: dict[str, Any], run_dir: Path, competitor: dict[str, Any]) -> dict[str, Any]:
    cfg = manifest["implementation"]
    inventory = run_dir / "phases/04-component-inventory/component-inventory.json"
    checks = [
        shlex.join([sys.executable, str(SKILL_DIR / "scripts/check_artifact.py"), "component-inventory", "--path", str(inventory)]),
        *cfg["checks"],
    ]
    return {
        "node_type": "loop",
        "node_id": f"implementation_{slug(competitor['id'])}",
        "objective": (
            f"Build the {competitor['id']} competitor in its disposable worktree. Strategy: {competitor['strategy']}\n"
            f"Target {cfg['target_surface']}. Read the selected mockup and {inventory}. "
            "Reuse existing React/Tailwind/shadcn/D3 components first and write implementation-reuse.json. "
            "Do not merge, push, or edit outside allowed globs."
        ),
        "allowed_globs": cfg["allowed_globs"],
        "required_changed_globs": cfg["required_changed_globs"],
        "checks": checks,
        "max_attempts": int(cfg.get("max_rounds", 3)),
        "check_timeout": int(cfg.get("check_timeout", 600)),
        "agent_config": str(SKILL_DIR / "examples/agents.implementation.toml"),
        "run_root": ".loop/runs/interface-implementation",
        "require_clean": True,
        "worktree": {"mode": "existing"},
        "outer_worktree_policy": "one disposable worktree per competitor",
    }


def receipt_payload(run_dir: Path, manifest: dict[str, Any], status: str, current_phase: str) -> dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "run_id": run_dir.name,
        "name": manifest["name"],
        "status": status,
        "terminal": False,
        "current_phase": current_phase,
        "human_promotion_required": True,
        "run_dir": str(run_dir),
        "updated_at": utc_now(),
    }


def plan_pipeline(manifest_path: Path, output: Path | None = None) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest = read_json(manifest_path)
    errors = validate_manifest(manifest)
    if errors:
        raise ValueError("manifest validation failed:\n- " + "\n- ".join(errors))
    brief_source = resolve_manifest_path(manifest_path, manifest["brief"])
    if not brief_source.is_file():
        raise ValueError(f"brief not found: {brief_source}")
    if output is None:
        root = Path(manifest.get("output_root", ".interface-design/runs"))
        root = root if root.is_absolute() else REPO_ROOT / root
        run_dir = root / f"{compact_utc()}-{slug(manifest['name'])}"
    else:
        run_dir = output.expanduser().resolve()
    if run_dir.exists():
        raise ValueError(f"run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)

    snapshot = copy.deepcopy(manifest)
    snapshot.update({"_source": str(manifest_path), "_brief_source": str(brief_source)})
    write_json(run_dir / "manifest.snapshot.json", snapshot)
    (run_dir / "brief.md").write_text(render_brief(manifest, brief_source.read_text(encoding="utf-8")), encoding="utf-8")

    lanes = research_lanes(manifest, run_dir)
    write_json(run_dir / "phases/01-research/plan.json", {
        "schema": "interface_design_pipeline.research_plan.v1",
        "parallel": True,
        "required_sources": manifest["research"].get("required_sources", ["github", "brave"]),
        "lanes": lanes,
        "selection_agent": "interface-researcher",
    })
    write_json(run_dir / "phases/02-reference-adjudication/agent-task.json", {
        "schema": "interface_design_pipeline.agent_task.v1",
        "agent": "interface-researcher",
        "read_only": True,
        "inputs": [path_for_node(run_dir / "phases/01-research/references.normalized.json"), path_for_node(run_dir / "brief.md")],
        "output": path_for_node(run_dir / "phases/02-reference-adjudication/reference-selection.json"),
        "required_fields": ["verdict", "selected_references", "patterns_to_keep", "patterns_to_reject", "provenance"],
    })

    mockups = [mockup_node(manifest, run_dir, item) for item in manifest["mockups"]["competitors"]]
    for node in mockups:
        write_json(run_dir / "phases/03-mockup-tournament/nodes" / f"{node['node_id']}.json", node)
    write_json(run_dir / "phases/03-mockup-tournament/plan.json", {
        "schema": "interface_design_pipeline.tournament_plan.v1", "phase": "mockup", "parallel_competitors": True,
        "nodes": mockups, "adjudicator": "interface-adjudicator",
        "output": path_for_node(run_dir / "phases/03-mockup-tournament/adjudication.json"),
    })

    impl = manifest["implementation"]
    write_json(run_dir / "phases/04-component-inventory/agent-task.json", {
        "schema": "interface_design_pipeline.agent_task.v1", "agent": "interface-researcher", "mode": "component_inventory",
        "read_only": True, "target_repo": impl["target_repo"], "target_surface": impl["target_surface"],
        "component_roots": impl["component_roots"], "stack": impl["stack"],
        "output": path_for_node(run_dir / "phases/04-component-inventory/component-inventory.json"),
        "hard_gate": "implementation waits for inventory PASS",
    })
    implementations = [implementation_node(manifest, run_dir, item) for item in impl["competitors"]]
    for node in implementations:
        write_json(run_dir / "phases/05-implementation-tournament/node-templates" / f"{node['node_id']}.json", node)
    write_json(run_dir / "phases/05-implementation-tournament/plan.json", {
        "schema": "interface_design_pipeline.tournament_plan.v1", "phase": "implementation",
        "parallel_competitors": True, "worktree_policy": "disposable", "nodes": implementations,
        "required_evidence": ["loop receipt", "fresh screenshot", "interaction results", "component reuse receipt"],
    })
    write_json(run_dir / "phases/06-final-adjudication/agent-task.json", {
        "schema": "interface_design_pipeline.agent_task.v1", "agent": "interface-adjudicator", "read_only": True,
        "inputs": ["mockup adjudication", "component inventory", "implementation receipts", "screenshots", "interaction results"],
        "output": path_for_node(run_dir / "phases/06-final-adjudication/adjudication.json"),
        "rules": ["hard failures cannot be averaged away", "no screenshot means no visual winner", "human promotes"],
    })
    write_json(run_dir / "phases/07-human-promotion/gate.json", {
        "schema": "interface_design_pipeline.human_gate.v1", "required": True, "status": "PENDING",
        "allowed_decisions": ["PROMOTE_WINNER", "PROMOTE_HYBRID", "RETURN_TO_MOCKUPS", "RETURN_TO_IMPLEMENTATION", "REJECT_ALL"],
    })

    phases = {phase: "PENDING" for phase in PHASES}
    phases["research"] = "PLANNED"
    status = {"schema": "interface_design_pipeline.status.v1", "run_id": run_dir.name, "name": manifest["name"],
              "status": "PLANNED", "current_phase": "research", "phases": phases, "created_at": utc_now(), "updated_at": utc_now()}
    write_json(run_dir / "status.json", status)
    write_json(run_dir / "pipeline-receipt.json", receipt_payload(run_dir, manifest, "PLANNED", "research"))
    commands = {"research": [sys.executable, path_for_node(SKILL_DIR / "scripts/pipeline.py"), "research", "--run-dir", path_for_node(run_dir), "--execute"]}
    write_json(run_dir / "commands.json", commands)
    append_event(run_dir, "pipeline_planned", manifest=str(manifest_path), run_id=run_dir.name)
    return {"schema": "interface_design_pipeline.plan_result.v1", "status": "PLANNED", "run_dir": str(run_dir),
            "research_lanes": len(lanes), "mockup_competitors": len(mockups),
            "implementation_competitors": len(implementations), "next_command": shlex.join(commands["research"])}
