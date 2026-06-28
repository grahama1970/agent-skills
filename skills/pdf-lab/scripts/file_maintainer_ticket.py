"""Build maintainer ticket packets for failed pdf-lab runtime verification.

Inputs: a pdf-lab job directory containing or needing verify-receipt.json.
Outputs: maintainer-ticket.json, and optionally a GitHub issue.
Failure modes: exits non-zero if verification unexpectedly passes or the issue
creation command fails.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

import typer

from runtime_verify import verify


SKILL_DIR = Path(__file__).resolve().parents[1]
SHARED_HELPERS = SKILL_DIR.parent / "_shared" / "skill_self_improvement.py"


def _load_helpers() -> Any:
    if not SHARED_HELPERS.exists():
        return _LocalHelpers
    spec = importlib.util.spec_from_file_location("skill_self_improvement", SHARED_HELPERS)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load runtime helper module: {SHARED_HELPERS}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _LocalHelpers:
    @staticmethod
    def build_ticket_packet(
        *,
        skill_id: str,
        verify_result: dict[str, Any],
        skill_target: str,
        agent_target: str | None = None,
        labels: list[str] | None = None,
        reference_repro: str | None = None,
        notes: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        labels = labels or [
            "skill-bug",
            "route:backend_python_or_skill_runtime",
            "agent:skill-maintainer",
        ]
        failed = [item for item in verify_result.get("checks", []) if not item.get("passed")]
        failed_lines = "\n".join(f"- `{item['name']}`: {item['detail']}" for item in failed)
        body = f"""## Target path
{skill_target}
{agent_target or ""}

## Current state
`./run.sh verify --job-dir {verify_result.get('job_dir')}` returned **{verify_result.get('status')}**.

Failed checks:
{failed_lines or "- no failed check details recorded"}

## Required proof
```bash
cd skills/{skill_id}
./sanity.sh
{reference_repro or f'./run.sh verify --job-dir {verify_result.get("job_dir")}'}
```

## Worker notes
{notes or "Filed automatically from runtime verify failure."}
"""
        first = failed[0]["name"] if failed else "verify"
        return {
            "schema_version": "skill.maintainer_ticket.v1",
            "skill_id": skill_id,
            "title": f"{skill_id}: job verify failed ({first})",
            "body": body,
            "labels": labels,
            "verify_status": verify_result.get("status"),
            "job_dir": verify_result.get("job_dir"),
        }

    @staticmethod
    def file_github_issue(
        *,
        title: str,
        body: str,
        repo: str,
        labels: list[str],
        dry_run: bool,
    ) -> dict[str, Any]:
        if dry_run:
            return {"repo": repo, "title": title, "labels": labels, "dry_run": True, "body_preview": body[:500]}
        cmd = ["gh", "issue", "create", "--repo", repo, "--title", title, "--body", body]
        for label in labels:
            cmd.extend(["--label", label])
        completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
        return {
            "repo": repo,
            "title": title,
            "labels": labels,
            "dry_run": False,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "ok": completed.returncode == 0,
        }


app = typer.Typer(help="Create maintainer ticket packets for failed pdf-lab jobs.")


@app.command()
def main(
    job_dir: Path = typer.Option(..., "--job-dir", help="pdf-lab job/output directory"),
    create: bool = typer.Option(False, "--create", help="Create GitHub issue with gh"),
    repo: str = typer.Option("grahama1970/agent-skills", "--repo", help="GitHub repo"),
) -> None:

    helpers = _load_helpers()
    resolved_job_dir = job_dir.expanduser().resolve()
    verify_result = verify(resolved_job_dir, mode="job")

    packet = helpers.build_ticket_packet(
        skill_id="pdf-lab",
        verify_result=verify_result,
        skill_target="skills/pdf-lab",
        agent_target="skills/pdf-lab/agents/pdf-lab/AGENTS.md",
        reference_repro=f"cd skills/pdf-lab && ./run.sh verify --job-dir {resolved_job_dir}",
        notes="pdf-lab runtime verifier failed; maintainers own code repair and commit.",
    )

    issue_result = helpers.file_github_issue(
        title=packet["title"],
        body=packet["body"],
        repo=repo,
        labels=packet["labels"],
        dry_run=not create,
    )
    packet["issue"] = issue_result

    ticket_path = resolved_job_dir / "maintainer-ticket.json"
    ticket_path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(packet, indent=2, sort_keys=True))

    if create and not issue_result.get("ok"):
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
