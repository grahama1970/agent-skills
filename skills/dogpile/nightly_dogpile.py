#!/usr/bin/env python3
"""
nightly_dogpile.py - Nightly Deep Dive Orchestrator

Workflow:
1. Assess Project (Static + LLM) -> report.json
2. Filter for Critical/Brittle/Aspirational issues
3. Dogpile Research (if needed) -> context.md
4. Code Review Loop (Fix) -> PR/Commit
"""
import os
import sys
import json
import subprocess
import typer
from pathlib import Path
from typing import Dict, Any, List
from loguru import logger
import httpx

# Configuration
SKILLS_DIR = Path.home() / "workspace/experiments/pi-mono/.pi/skills"
ASSESS_SCRIPT = SKILLS_DIR / "assess/assess.py"
DOGPILE_SCRIPT = SKILLS_DIR / "dogpile/run.sh"
CODE_REVIEW_SCRIPT = SKILLS_DIR / "review-code/code_review.py"
# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
TASK_MONITOR_SCRIPT = SKILLS_DIR / "task-monitor/monitor_adapter.py"

def run_assessment(project_path: Path) -> Dict[str, Any]:
    """Run assess.py and return parsed JSON."""
    print(f"Running assessment on {project_path}...")
    try:
        result = subprocess.run(
            [sys.executable, str(ASSESS_SCRIPT), "run", str(project_path)],
            capture_output=True, text=True, check=True,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        # Find JSON in output (grep for first {)
        output = result.stdout
        json_start = output.find('{')
        if json_start != -1:
            return json.loads(output[json_start:])
        return {}
    except subprocess.CalledProcessError as e:
        print(f"Assessment failed: {e.stderr}", file=sys.stderr)
        return {}

def record_nightly_assessment(project: str, issue: Dict[str, Any], research: str = "", outcome: str = "", status: str = "success"):
    """Store assessment run in /memory via Unix socket."""
    print(f"Recording assessment for: {issue['feature']}")
    try:
        import httpx
        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
            client.post("/learn", json={
                "problem": f"Nightly assessment: {project} - {issue.get('feature', '')}",
                "solution": f"outcome={outcome} status={status} research={research}",
                "tags": ["nightly-assessment", project, status],
            })
    except Exception as e:
        print(f"Assessment recording failed: {e}", file=sys.stderr)

def trigger_dogpile(topic: str) -> str:
    """Run dogpile search and return summary."""
    print(f"Dogpiling on: {topic}")
    try:
        # Call dogpile search
        result = subprocess.run(
            [str(DOGPILE_SCRIPT), "search", topic],
            capture_output=True, text=True, check=True,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Dogpile failed: {e.stderr}", file=sys.stderr)
        return f"Research failed for {topic}"

def update_task_monitor(task_id: str, status: str, progress: int):
    """Update task monitor if available."""
    try:
        # Use the monitor adapter if it exists
        if TASK_MONITOR_SCRIPT.exists():
            subprocess.run([
                sys.executable, str(TASK_MONITOR_SCRIPT), 
                "update", task_id, 
                "--status", status, 
                "--progress", str(progress)
            ], check=False,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
    except Exception as e:
        logger.error("check failed: {}", e)

def trigger_code_review(project_path: Path, issue: Dict[str, Any], context: str):
    """Run code_review.py loop to fix the issue."""
    print(f"Starting Code Review Loop for: {issue['feature']}")
    update_task_monitor("nightly-fix", f"Fixing {issue['feature']}", 50)
    
    # Construct a request.md for the review
    request_content = f"""
# Nightly Fix: {issue['feature']}

## Issue
{issue['reason']}

## Location
{issue['location']}

## Context from Research
{context}

## Goal
Fix the identified issue. Ensure no regressions.
"""
    request_path = project_path / ".nightly_fix_request.md"
    request_path.write_text(request_content)

    # Run loop
    cmd = [
        sys.executable, str(CODE_REVIEW_SCRIPT), "loop",
        "--file", str(request_path),
        "--rounds", "2",
        "--workspace", str(project_path),
        "--save-intermediate"
    ]
    
    print(f"Executing: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        update_task_monitor("nightly-fix", f"Fixed {issue['feature']}", 100)
        return "Code review successful. Patch applied."
    except subprocess.CalledProcessError:
        update_task_monitor("nightly-fix", f"FAILED {issue['feature']}", 0)
        return "Code review failed."

def run_project(project_path: Path):
    if not project_path.exists():
        print(f"Project not found: {project_path}")
        return

    print(f"=== Starting Nightly Deep Dive: {project_path.name} ===")
    
    # 1. Assess
    report = run_assessment(project_path)
    if not report:
        print("No assessment report generated.")
        return

    # 2. Identify Issues (Brittle & Over-Engineered)
    issues_to_fix = []
    issues_to_fix.extend(report.get("categories", {}).get("brittle", []))
    issues_to_fix.extend(report.get("categories", {}).get("over_engineered", []))
    issues_to_fix.extend(report.get("categories", {}).get("aspirational", [])) # Maybe implement stubs?

    print(f"Found {len(issues_to_fix)} potential issues.")

    # 3. Fix Loop
    for issue in issues_to_fix[:1]: # Limit to 1 per night for safety
        print(f"Selected for repair: {issue['feature']}")
        
        # 4. Research
        context = trigger_dogpile(f"{issue['feature']} in {report['project']}")
        
        # 5. Review/Fix
        outcome = trigger_code_review(project_path, issue, context)
        
        # 6. Memory Storage (Permanent Record)
        record_nightly_assessment(
            project=report['project'],
            issue=issue,
            research=context,
            outcome=outcome or "Fix applied or LGTM",
            status="success" if outcome else "failed"
        )

app = typer.Typer(help="Nightly Dogpile Orchestrator")


@app.command()
def main(
    project: str = typer.Option(None, help="Specific project to run on"),
    all_projects: bool = typer.Option(False, help="Run on all registered projects"),
):
    if project:
        run_project(Path(project))
    elif all_projects:
        # Example hardcoded list for now, ideally read from config
        projects = [
            Path(__file__).resolve().parent.parent.parent.parent,
            # Add others here
        ]
        for p in projects:
            run_project(p)
    else:
        typer.echo("Specify --project PATH or --all-projects")
        raise typer.Exit(1)

if __name__ == "__main__":
    app()
