"""Nightly roundtable review of skills amended during the day.

Purpose: discover skills under ``skills/<name>/`` amended in the last 24h from
git history, build one equal-context packet from /project-state,
/ops-workstation, and /brave-search, convene a five-seat concurrent browser
roundtable (webgpt, webclaude, webkimi, webgrok, webgemini) through
/ask tau-dag, and store the attributed synthesis through the /memory daemon
(collection ``project_roundtables`` plus a lessons summary with Qdrant
semantic sync) so ``/memory recall`` finds it.

Inputs: git history of the canonical checkout, downstream skill CLIs
(ask, memory, project-state, brave-search, ops-workstation, scheduler).
Outputs: ``reports/monitor-projects/<run-id>/{packet.md,receipt.json}`` and
memory documents with ``schema: monitor_projects.roundtable.v1``.

Failure modes: any downstream context source that fails is recorded as
``NOT_ESTABLISHED`` in the packet (never silently omitted); a failed ask
execution or failed /store read-back exits non-zero with the receipt marked
``NEEDS_ATTENTION``. This module never touches ArangoDB or Qdrant directly —
all persistence goes through the memory daemon's HTTP API.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx
import typer
from loguru import logger
from pydantic import BaseModel, Field

app = typer.Typer(add_completion=False, no_args_is_help=True)

SKILL_DIR = Path(__file__).resolve().parents[1]
SKILLS_ROOT = SKILL_DIR.parent
REPO_ROOT = SKILLS_ROOT.parent
REPORTS_ROOT = REPO_ROOT / "reports" / "monitor-projects"

HANDLERS = ["webgpt", "webclaude", "webkimi", "webgrok", "webgemini"]
MEMORY_URL = os.environ.get("MEMORY_SERVICE_URL", "http://127.0.0.1:8601")
ROUNDTABLE_COLLECTION = "project_roundtables"
SCHEMA = "monitor_projects.roundtable.v1"
RESEARCH_CAP = 3
NON_SKILL_DIRS = {"_shared", "__pycache__", ".system"}


@dataclass(frozen=True, slots=True)
class AmendedSkill:
    name: str
    files_changed: int
    commits: tuple[str, ...]


class StoreResponse(BaseModel):
    """Boundary model for the memory daemon /store reply."""

    stored: bool | None = None
    key: str | None = Field(default=None, alias="_key")

    model_config = {"populate_by_name": True, "extra": "allow"}


@dataclass
class RunContext:
    run_id: str
    run_dir: Path
    dry_run: bool
    amended: list[AmendedSkill] = field(default_factory=list)


def _run(
    args: list[str],
    timeout: int,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Run a subprocess with no shell, finite timeout, captured output."""
    merged_env = {**os.environ, **(env or {})}
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=merged_env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.error("command timed out after {}s: {}", timeout, args[:3])
        return 124, "", f"timeout after {timeout}s"
    except FileNotFoundError as exc:
        logger.error("command not found: {} ({})", args[0], exc)
        return 127, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def discover_amended(repo_root: Path, since_hours: int = 24) -> list[AmendedSkill]:
    """Amended skills = skills/<name>/ paths touched by commits in the window."""
    rc, out, err = _run(
        [
            "git",
            "log",
            f"--since={since_hours} hours ago",
            "--name-only",
            "--pretty=format:@@%h %s",
        ],
        timeout=60,
        cwd=repo_root,
    )
    if rc != 0:
        logger.error("git log failed: {}", err.strip())
        raise typer.Exit(code=2)

    touched: dict[str, set[str]] = {}
    counts: dict[str, int] = {}
    current_commit = ""
    for line in out.splitlines():
        if line.startswith("@@"):
            current_commit = line[2:].strip()
            continue
        parts = line.strip().split("/")
        if len(parts) >= 3 and parts[0] == "skills":
            name = parts[1]
            if name in NON_SKILL_DIRS or name.startswith("."):
                continue
            if not (repo_root / "skills" / name).is_dir():
                continue
            touched.setdefault(name, set()).add(current_commit)
            counts[name] = counts.get(name, 0) + 1
    return sorted(
        (
            AmendedSkill(name=n, files_changed=counts[n], commits=tuple(sorted(touched[n])))
            for n in touched
        ),
        key=lambda s: -s.files_changed,
    )


def _skill_description(name: str) -> str:
    """First description line from the skill's SKILL.md frontmatter (best effort)."""
    path = SKILLS_ROOT / name / "SKILL.md"
    if not path.is_file():
        return name
    in_desc = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[:40]:
        if line.startswith("description:"):
            rest = line.split(":", 1)[1].strip()
            if rest and rest != ">":
                return rest
            in_desc = True
            continue
        if in_desc:
            stripped = line.strip()
            if stripped and not stripped.startswith("-"):
                return stripped
            break
    return name


def _context_block(label: str, args: list[str], timeout: int, cwd: Path | None = None,
                   env: dict[str, str] | None = None, max_chars: int = 6000) -> str:
    rc, out, err = _run(args, timeout=timeout, cwd=cwd, env=env)
    if rc != 0:
        logger.error("{} context failed (rc={}): {}", label, rc, err.strip()[:300])
        return f"### {label}\nNOT_ESTABLISHED: command failed (rc={rc}): {err.strip()[:300]}\n"
    return f"### {label}\n{out.strip()[:max_chars]}\n"


def build_packet(ctx: RunContext) -> str:
    """One shared packet, identical for every seat (equal-context contract)."""
    date = ctx.run_id.split("T")[0]
    skills_lines = "\n".join(
        f"- `{s.name}` — {s.files_changed} file change(s); commits: {', '.join(s.commits)[:200]}\n"
        f"  description: {_skill_description(s.name)}"
        for s in ctx.amended
    )

    project_state = _context_block(
        "project-state (agent-skills, cached)",
        [str(SKILLS_ROOT / "project-state" / "run.sh"), "report", "--json", "--cached"],
        timeout=600,
        env={"PROJECT_STATE_ROOT": str(REPO_ROOT)},
    )
    discipline_check = _context_block(
        "project-taxonomy ci (disciplines + crosswalk drift + portfolio freshness/coverage)",
        [str(SKILLS_ROOT / "project-taxonomy" / "run.sh"), "ci"],
        timeout=300,
        max_chars=3000,
    )
    workstation = _context_block(
        "ops-workstation quick health",
        [str(SKILLS_ROOT / "ops-workstation" / "run.sh")],
        timeout=180,
        max_chars=3000,
    )
    research_parts = []
    for s in ctx.amended[:RESEARCH_CAP]:
        query = f"{s.name} {_skill_description(s.name)[:120]} best practices"
        research_parts.append(
            _context_block(
                f"brave-search: {s.name}",
                [str(SKILLS_ROOT / "brave-search" / "run.sh"), "web", query],
                timeout=120,
                max_chars=3000,
            )
        )
    if len(ctx.amended) > RESEARCH_CAP:
        skipped = [s.name for s in ctx.amended[RESEARCH_CAP:]]
        research_parts.append(
            f"### brave-search coverage note\nResearch capped at {RESEARCH_CAP} skills; "
            f"not researched: {', '.join(skipped)}\n"
        )

    return f"""# Nightly skill review roundtable — {date}

Objective: Review the skills amended in agent-skills during the last 24h for
correctness risk, best-practices compliance, composition/architecture drift,
and missed opportunities. agent-skills is a collection of skills; review the
amended skill directories only, never the repository as one project.

Immutable goal / acceptance bar: For each amended skill, either a concrete
executable improvement slice or an explicit "no action needed" with reasons.

Target artifacts (amended skills, last 24h):
{skills_lines}

Current evidence:
{project_state}
{discipline_check}
{workstation}
External research (shared identically with every seat):
{chr(10).join(research_parts)}

Constraints:
- Skills must comply with best-practices-skills, best-practices-python, and
  best-practices-arangodb (ArangoDB access only via the /memory daemon).
- Recommendations must be scoped to individual skill directories.

Handlers: {", ".join(HANDLERS)} (concurrent, equal context, peer seats).

Questions for every seat:
1. Which amended skill carries the highest regression or drift risk, and why?
2. What best-practices violations or composition gaps do you see in the
   evidence above?
3. What is the single highest-value executable slice for tomorrow?

Expected response format (per seat):
POSITION: recommended direction.
EVIDENCE: facts, files, receipts, or external sources.
RISKS: likely failure modes and false-green traps.
QUESTIONS: only blockers requiring human/external input.
EXECUTABLE_SLICES: owner, artifact or command, acceptance check.

Proof boundary: Seat responses are advisory reviewer evidence. Local
deterministic verification by the project agent is still required before any
slice is closed.
"""


def run_roundtable(ctx: RunContext, packet_path: Path) -> dict:
    """Compile (and unless dry-run, execute) the roundtable through /ask."""
    target = f"monitor-projects-{ctx.run_id.split('T')[0]}"
    args = [
        str(SKILLS_ROOT / "ask" / "run.sh"),
        "tau-dag",
        packet_path.read_text(encoding="utf-8"),
        "--repo",
        "local/agent-skills",
        "--target",
        target,
        "--topology",
        "concurrent",
        "--json",
    ]
    for handler in HANDLERS:
        args.extend(["--handler", handler])
    if not ctx.dry_run:
        args.extend(["--execute", "--poll-timeout-seconds", "3600"])

    rc, out, err = _run(args, timeout=4200, cwd=SKILLS_ROOT / "ask")
    result: dict = {"rc": rc, "target": target}
    try:
        start = out.index("{")
        result["ask"] = json.loads(out[start:])
    except (ValueError, json.JSONDecodeError):
        logger.error("ask output was not JSON (rc={}): {}", rc, (err or out).strip()[:400])
        result["ask"] = None
        result["raw_tail"] = out.strip()[-2000:]
        result["stderr_tail"] = err.strip()[-1000:]
    return result


def synthesize(ctx: RunContext, ask_result: dict) -> dict:
    """Deterministic synthesis skeleton with per-seat status and pointers.

    Attributed prose synthesis is done by the project agent reading the seat
    responses; this function never fabricates consensus.
    """
    ask = ask_result.get("ask") or {}
    run_dir = ask.get("run_dir") or ask.get("run_directory")
    seat_status: dict[str, str] = {}
    seat_responses: dict[str, str] = {}
    if ctx.dry_run:
        seat_status = {h: "not_run_dry_run" for h in HANDLERS}
    elif run_dir and Path(run_dir).is_dir():
        for handler in HANDLERS:
            matches = sorted(Path(run_dir).rglob(f"*{handler}*response*"))
            if matches:
                text = matches[0].read_text(encoding="utf-8", errors="replace")
                seat_status[handler] = "responded"
                seat_responses[handler] = text[:8000]
            else:
                seat_status[handler] = "NEEDS_ATTENTION_no_response_artifact"
    else:
        seat_status = {h: "NEEDS_ATTENTION_no_run_dir" for h in HANDLERS}

    ok = ctx.dry_run or all(v == "responded" for v in seat_status.values())
    return {
        "schema": SCHEMA,
        "run_id": ctx.run_id,
        "date": ctx.run_id.split("T")[0],
        "created_at": datetime.now(UTC).isoformat(),
        "skills_reviewed": [s.name for s in ctx.amended],
        "handlers": HANDLERS,
        "topology": "concurrent",
        "dry_run": ctx.dry_run,
        "ask_target": ask_result.get("target"),
        "ask_rc": ask_result.get("rc"),
        "ask_compiled": bool(ask),
        "ask_run_dir": run_dir,
        "seat_status": seat_status,
        "seat_responses": seat_responses,
        "status": "ok" if ok else "NEEDS_ATTENTION",
        "proof_boundary": "seat responses are advisory; local verification required",
    }


def store_receipt(receipt: dict) -> bool:
    """Store via the memory daemon and verify with a read-back recall."""
    key = f"monitor-projects-{receipt['run_id']}".replace(":", "-").replace(".", "-")
    timeout = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)
    with httpx.Client(base_url=MEMORY_URL, timeout=timeout) as client:
        resp = client.post(
            "/store",
            json={"document": {"_key": key, **receipt}, "collection": ROUNDTABLE_COLLECTION},
        )
        resp.raise_for_status()
        StoreResponse.model_validate(resp.json())

        summary = {
            "problem": (
                f"What did the nightly monitor-projects roundtable on {receipt['date']} "
                f"find about skills {', '.join(receipt['skills_reviewed'])}?"
            ),
            "solution": (
                f"Roundtable {receipt['run_id']} status={receipt['status']} "
                f"seats={json.dumps(receipt['seat_status'])} "
                f"full receipt: {ROUNDTABLE_COLLECTION}/{key} ask_run_dir={receipt['ask_run_dir']}"
            ),
            "tags": ["monitor-projects", "roundtable", receipt["date"], *receipt["skills_reviewed"][:8]],
        }
        client.post("/store", json={"document": summary}).raise_for_status()

    rc, out, err = _run(
        [str(SKILLS_ROOT / "memory" / "run.sh"), "recall", "--q",
         f"monitor-projects roundtable {receipt['date']}", "--brief"],
        timeout=120,
    )
    verified = rc == 0 and (key in out or receipt["date"] in out)
    if not verified:
        logger.error("read-back failed: recall did not surface {} ({})", key, err.strip()[:200])
    return verified


@app.command()
def discover(json_out: bool = typer.Option(True, "--json/--no-json"),
             since_hours: int = typer.Option(24, "--since-hours")) -> None:
    """List skills amended in the window. No side effects."""
    amended = discover_amended(REPO_ROOT, since_hours)
    payload = [{"name": s.name, "files_changed": s.files_changed, "commits": list(s.commits)}
               for s in amended]
    typer.echo(json.dumps(payload, indent=2) if json_out else "\n".join(s.name for s in amended))


@app.command()
def nightly(dry_run: bool = typer.Option(False, "--dry-run"),
            since_hours: int = typer.Option(24, "--since-hours")) -> None:
    """Full pipeline: discover -> context -> roundtable -> synthesize -> store."""
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = REPORTS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    ctx = RunContext(run_id=run_id, run_dir=run_dir, dry_run=dry_run)
    ctx.amended = discover_amended(REPO_ROOT, since_hours)

    if not ctx.amended:
        receipt = {
            "schema": SCHEMA, "run_id": run_id, "date": run_id.split("T")[0],
            "created_at": datetime.now(UTC).isoformat(), "skills_reviewed": [],
            "status": "no_changes", "dry_run": dry_run,
        }
        (run_dir / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        if not dry_run:
            store_receipt(receipt)
        typer.echo(json.dumps(receipt, indent=2))
        return

    logger.info("amended skills: {}", [s.name for s in ctx.amended])
    packet = build_packet(ctx)
    packet_path = run_dir / "packet.md"
    packet_path.write_text(packet, encoding="utf-8")

    ask_result = run_roundtable(ctx, packet_path)
    receipt = synthesize(ctx, ask_result)
    (run_dir / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    if dry_run:
        typer.echo(json.dumps({**receipt, "seat_responses": "omitted"}, indent=2))
        return

    receipt["stored_verified"] = store_receipt(receipt)
    (run_dir / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    typer.echo(json.dumps({k: v for k, v in receipt.items() if k != "seat_responses"}, indent=2))
    if receipt["status"] != "ok" or not receipt["stored_verified"]:
        raise typer.Exit(code=1)


@app.command()
def last() -> None:
    """Recall the most recent roundtable receipt from /memory."""
    rc, out, err = _run(
        [str(SKILLS_ROOT / "memory" / "run.sh"), "recall", "--q",
         "monitor-projects nightly roundtable receipt", "--brief"],
        timeout=120,
    )
    typer.echo(out if rc == 0 else f"recall failed: {err.strip()}")
    if rc != 0:
        raise typer.Exit(code=1)


@app.command()
def discuss(question: str) -> None:
    """Recall roundtable material relevant to a question, for human discussion."""
    rc, out, err = _run(
        [str(SKILLS_ROOT / "memory" / "run.sh"), "recall", "--q",
         f"monitor-projects roundtable {question}", "--brief"],
        timeout=120,
    )
    typer.echo(out if rc == 0 else f"recall failed: {err.strip()}")
    if rc != 0:
        raise typer.Exit(code=1)


@app.command()
def register(cron: str = typer.Option("30 2 * * *", "--cron")) -> None:
    """Register the nightly job with /scheduler."""
    rc, out, err = _run(
        [str(SKILLS_ROOT / "scheduler" / "run.sh"), "register",
         "--name", "monitor-projects-nightly",
         "--cron", cron,
         "--command", str(SKILL_DIR / "run.sh") + " nightly"],
        timeout=60,
    )
    typer.echo(out.strip() or err.strip())
    if rc != 0:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
