#!/usr/bin/env python3
"""Plan and audit skills-first project setup."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Config(BaseModel):
    """setup-project YAML contract."""

    model_config = ConfigDict(extra="forbid")

    schema_: Literal["setup_project.config.v1"] = Field(alias="schema")
    classification: str
    project: str
    project_root: Path
    purpose: str
    curate_client_config: Path | None = None
    required_skills: list[str] = Field(min_length=1)
    required_files: list[str] = Field(min_length=1)
    readme_must_contain: list[str] = Field(default_factory=list)
    proof_commands: list[str] = Field(default_factory=list)


def load_config(path: Path) -> Config:
    return Config.model_validate(yaml.safe_load(path.read_text()))


def curate_plan(config: Config) -> dict | None:
    if not config.curate_client_config:
        return None
    skill_dir = Path(__file__).resolve().parents[1]
    run = skill_dir.parent / "curate-client" / "run.sh"
    proc = subprocess.run(
        [str(run), "plan", "--config", str(config.curate_client_config)],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    if proc.returncode != 0:
        return {"status": "FAIL", "returncode": proc.returncode, "stderr": proc.stderr[-2000:]}
    return json.loads(proc.stdout)


def plan(config: Config) -> dict:
    steps = [
        {"order": 1, "skill": "curate-client", "action": "build or verify the interview brief prep pack", "writes": "knowledge/prep-pack only"},
        {"order": 2, "skill": "best-practices-readme", "action": "write README navigation, skill provenance, proof, and non-claims", "writes": "README.md"},
        {"order": 3, "skill": "setup-project", "action": "write immutable_goal.json and audit setup surface", "writes": "immutable_goal.json plus setup receipt"},
        {"order": 4, "skill": "best-practices-fastapi", "action": "shape Pydantic contracts and FastAPI adapter boundary", "writes": "src/"},
        {"order": 5, "skill": "memory", "action": "route persistence through Memory endpoints", "writes": "Memory collections via /memory only"},
        {"order": 6, "skill": "hack", "action": "run bounded SAST and read Hack-owned receipts", "writes": "receipts/"},
        {"order": 7, "skill": "terraform + ops-terraform", "action": "create and validate plan-only deployment handoff", "writes": "infra/terraform/"},
        {"order": 8, "skill": "agentic-evals", "action": "prove claims and seams with repeated retained evals", "writes": "fixtures/agentic_eval.json and reports"},
    ]
    return {
        "schema": "setup_project.plan_receipt.v1",
        "status": "PASS",
        "classification": config.classification,
        "project": config.project,
        "project_root": str(config.project_root),
        "purpose": config.purpose,
        "required_skills": config.required_skills,
        "steps": steps,
        "curate_client_plan": curate_plan(config),
        "writes": False,
    }


def audit(config: Config) -> dict:
    root = config.project_root
    missing_files = [name for name in config.required_files if not (root / name).exists()]
    readme = (root / "README.md").read_text(errors="ignore") if (root / "README.md").exists() else ""
    missing_readme = [text for text in config.readme_must_contain if text not in readme]
    goal_ok = False
    goal_path = root / "immutable_goal.json"
    if goal_path.exists():
        try:
            goal = json.loads(goal_path.read_text())
            goal_ok = bool(goal.get("classification") and goal.get("schema") == "openai_interview.immutable_goal.v1")
        except json.JSONDecodeError:
            goal_ok = False
    curate = curate_plan(config)
    problems = []
    if missing_files:
        problems.append({"code": "missing_files", "items": missing_files})
    if missing_readme:
        problems.append({"code": "missing_readme_terms", "items": missing_readme})
    if not goal_ok:
        problems.append({"code": "immutable_goal_invalid", "path": str(goal_path)})
    if curate and curate.get("status") != "PASS":
        problems.append({"code": "curate_client_plan_failed", "detail": curate})
    return {
        "schema": "setup_project.audit_receipt.v1",
        "status": "PASS" if not problems else "FAIL",
        "classification": config.classification,
        "project": config.project,
        "project_root": str(root),
        "required_skills": config.required_skills,
        "curate_client_plan_status": curate.get("status") if curate else None,
        "missing_files": missing_files,
        "missing_readme_terms": missing_readme,
        "immutable_goal_valid": goal_ok,
        "problems": problems,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["plan", "audit"])
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    config = load_config(args.config)
    receipt = plan(config) if args.command == "plan" else audit(config)
    print(json.dumps(receipt, indent=2))
    if receipt["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
