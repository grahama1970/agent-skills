#!/usr/bin/env bash
set -euo pipefail

python3 - "$@" <<'PY'
import argparse
import datetime as dt
import json
import re
from pathlib import Path


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug[:48] or "design-request"


def infer_routing(request: str) -> list[str]:
    lowered = request.lower()
    skills = ["best-practices-design", "memory"]
    if any(word in lowered for word in ["mockup", "screenshot", "external design", "match", "frozen"]):
        skills.append("best-practices-codex-design")
    if any(word in lowered for word in ["react", "component", "route", "ux-lab", "implementation", "implement"]):
        skills.append("best-practices-react")
    if any(word in lowered for word in ["polish", "motion", "animation", "hover", "typography", "radius", "feel"]):
        skills.append("make-interfaces-feel-better")
    if any(word in lowered for word in ["d3", "chart", "graph", "svg", "visualization", "data viz"]):
        skills.append("best-practices-d3")
    if any(word in lowered for word in ["infographic", "architecture", "workflow", "system map", "proof sheet"]):
        skills.append("best-practices-infographic")
    if any(word in lowered for word in ["research", "examples", "references", "competitor", "precedent"]):
        skills.append("dogpile")
    if any(word in lowered for word in ["review", "critique", "designer", "persona"]):
        skills.extend(["ask", "scillm"])
    if any(word in lowered for word in ["compare", "choose", "human review", "image", "mockup", "mockups"]):
        skills.append("interview")
    if any(word in lowered for word in ["ux-lab", "react", "implement", "component"]):
        skills.append("ux-lab")
    return list(dict.fromkeys(skills))


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


parser = argparse.ArgumentParser(description="Start a create-design collaboration session.")
parser.add_argument("--dry-run", action="store_true", help="Create artifacts without invoking collaborators.")
parser.add_argument("--root", default=".create-design/runs", help="Directory for session artifacts.")
parser.add_argument("request", nargs="*", help="Natural-language design request.")
args = parser.parse_args()

request = " ".join(args.request).strip()
if not request:
    raise SystemExit("usage: run.sh [--dry-run] '<design request>'")

now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
run_dir = Path(args.root) / f"{now}-{slugify(request)}"
run_dir.mkdir(parents=True, exist_ok=False)

routing = infer_routing(request)

request_doc = {
    "schema": "create_design.request.v1",
    "created_at": now,
    "request": request,
    "dry_run": args.dry_run,
    "run_dir": str(run_dir),
}
write_json(run_dir / "request.json", request_doc)

write_json(
    run_dir / "best-practices-routing.json",
    {
        "schema": "create_design.best_practices_routing.v1",
        "request": request,
        "applicable_skills": routing,
        "always_required": ["best-practices-design", "memory"],
        "notes": [
            "Routing is a starter inference; the project agent must read applicable SKILL.md files before acting.",
            "ux-lab is a downstream implementation workbench, not the design authority.",
        ],
    },
)

write_json(
    run_dir / "collaboration-plan.json",
    {
        "schema": "create_design.collaboration_plan.v1",
        "request": request,
        "steps": [
            {"id": "memory_recall", "skill": "memory", "purpose": "Recall prior UX lessons and accepted/rejected decisions."},
            {"id": "classify_surface", "skill": "best-practices-design", "purpose": "Select applicable best-practices gates."},
            {"id": "external_research", "skill": "dogpile", "purpose": "Gather references only when current precedents are needed."},
            {"id": "designer_review", "skill": "ask/scillm", "purpose": "Use bounded designer/reviewer collaborators."},
            {"id": "human_review", "skill": "interview", "purpose": "Launch HTML/TUI review for image or multi-part decisions."},
            {"id": "implementation", "skill": "ux-lab", "purpose": "Implement accepted direction in the React workbench."},
            {"id": "visual_proof", "skill": "surf/test-interactions/review-design", "purpose": "Capture screenshots/CDP proof and reviewer verdicts."},
            {"id": "memory_learn", "skill": "memory", "purpose": "Store accepted decisions, rejected patterns, and artifact paths."},
        ],
        "status": "started" if not args.dry_run else "dry_run_started",
    },
)

print(json.dumps({"ok": True, "run_dir": str(run_dir), "artifacts": [str(p) for p in sorted(run_dir.iterdir())]}, indent=2))
PY
