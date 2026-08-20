#!/usr/bin/env python3
"""Deterministic eval->ticket loop: failed /ask agentic-evals become tickets.

One bounded tick of the convergence loop the operator asked for (2026-08-20):

1. Run the agentic-evals runner on a fixture (default: the live subset).
2. Every case whose outcome is FAIL files one compliant /ticket bug carrying
   the trial evidence, the report path, and a deterministic re-pass command as
   required proof. BLOCKED cases (unmet preconditions / all-infra-blocked
   trials) are surfaced but NOT ticketed -- an external outage is not a code
   defect to dispatch a repair agent at.
3. Tickets are deduplicated against open issues by exact title, so a failure
   that persists across loop ticks keeps ONE ticket, not one per run.
4. The fix side is the existing project-watchdog lane: its cron leases the
   ticket, dispatches a creator-reviewer Tau DAG in an isolated worktree, and
   its closure audit demands the ticket's proof command -- which is the eval
   re-passing. The next eval-loop tick then either passes (converged) or
   re-files, so the system loops until all evals pass without anyone
   hand-driving it.

Preview-first like /ticket itself: without --apply it prints the tickets it
WOULD file. Exit 0 when every case passed, 1 when failures exist.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import typer

app = typer.Typer(add_completion=False)

SKILL_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = SKILL_ROOT.parent
REPORTS = Path("/mnt/storage12tb/skills/ask/outputs/eval-reports")
REPO = "grahama1970/agent-skills"


def _ticket_title(case_name: str) -> str:
    return f"eval regression: {case_name}"


def _open_ticket_exists(title: str) -> bool:
    proc = subprocess.run(
        ["gh", "issue", "list", "--repo", REPO, "--state", "open",
         "--search", f'in:title "{title}"', "--json", "title"],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        # Fail closed into filing: a dedupe check that cannot read GitHub must
        # not silently suppress a regression ticket.
        return False
    try:
        return any(row.get("title") == title for row in json.loads(proc.stdout or "[]"))
    except json.JSONDecodeError:
        return False


def _tick(
    fixture: Path,
    apply: bool,
    dispatch_fix: bool,
    repair_creator: str,
    skip_run: Path | None,
) -> int:
    """One bounded loop tick. Returns the number of FAILED cases."""

    if skip_run:
        report_path = skip_run
    else:
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        report_path = REPORTS / f"{stamp}-eval-loop.json"
        proc = subprocess.run(
            [str(SKILLS_ROOT / "agentic-evals" / "run.sh"), "run", str(fixture),
             "--output", str(report_path)],
            capture_output=True, text=True, cwd=SKILLS_ROOT / "agentic-evals",
        )
        if not report_path.is_file():
            typer.echo("EVAL_LOOP_ERROR: runner produced no report", err=True)
            typer.echo(proc.stderr[-400:], err=True)
            raise typer.Exit(1)
    report = json.loads(report_path.read_text())
    failed = [c for c in report.get("cases", []) if c.get("outcome") == "FAIL"]
    blocked = [c for c in report.get("cases", []) if c.get("outcome") == "BLOCKED"]
    passed = [c for c in report.get("cases", []) if c.get("outcome") == "PASS"]
    typer.echo(f"EVAL_LOOP: {len(passed)} PASS, {len(failed)} FAIL, {len(blocked)} BLOCKED "
               f"({report_path.name})")
    for c in blocked:
        typer.echo(f"BLOCKED (no ticket -- external precondition): {c['name']}: "
                   f"{'; '.join(c.get('problems') or [])[:160]}")
    filed, deduped = [], []
    for c in failed:
        title = _ticket_title(c["name"])
        if _open_ticket_exists(title):
            deduped.append(c["name"])
            typer.echo(f"TICKET_EXISTS: {title}")
            continue
        evidence = "; ".join((c.get("problems") or [])[:4])[:400] or "see report trials"
        rerun = (
            "cd skills/ask && python3 - <<'PYEOF'\n"
            "import json\n"
            "f = json.load(open('fixtures/agentic_eval_live.json'))\n"
            "by = {c['name']: c for c in f['cases']}\n"
            f"want = ['{c['name']}', 'ladder-red-team-false-greens-stay-red']\n"
            "sub = {k: v for k, v in f.items() if k != 'cases'}\n"
            "sub['trials'] = 2\n"
            "sub['cases'] = [by[n] for n in want]\n"
            "open('fixtures/agentic_eval_live_subset.json', 'w').write(json.dumps(sub, indent=2))\n"
            "PYEOF\n"
            "cd ../agentic-evals && ./run.sh run ../ask/fixtures/agentic_eval_live_subset.json "
            "--output /tmp/eval-regression-proof.json"
        )
        cmd = [str(SKILLS_ROOT / "ticket" / "run.sh"), "bug", title,
               "--target", "skills/ask",
               "--observed", f"agentic-eval case failed {c.get('passed_trials', 0)}"
                             f"/{len(c.get('trials') or [])} trials: {evidence}",
               "--expected", "the case passes 2/2 trials through the agentic-evals runner "
                             "with its oracle unchanged (do not weaken the eval to green it)",
               "--repro", f"see report {report_path} case {c['name']}; rerun via the proof command",
               "--proof", rerun,
               "--context-file", str(report_path),
               "--required-skill", "agentic-evals",
               "--required-skill", "best-practices-delivery-proof",
               "--route", "backend_python_or_skill_runtime",
               "--agent", "coder",
               "--label", "agentic-evals",
               ]
        if apply:
            cmd.append("--apply")
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=SKILLS_ROOT.parent)
        ok = proc.returncode == 0
        typer.echo(("TICKET_FILED: " if apply else "TICKET_PREVIEW: ") + title
                   + ("" if ok else f"  (ticket cli exit {proc.returncode}: {proc.stderr[-160:]})"))
        if ok:
            filed.append(c["name"])
    if dispatch_fix and apply and (filed or deduped):
        # One bounded watchdog tick per outstanding ticket, SEQUENTIALLY:
        # each tick leases one issue, dispatches the creator-reviewer Tau DAG
        # (creator = the operator-chosen gpt-5.5 high seat, reviewer a
        # different family), and posts its receipt before the next tick runs.
        import os
        env = dict(os.environ)
        env["PROJECT_WATCHDOG_REPAIR_CREATOR"] = repair_creator
        for i, _name in enumerate([*filed, *deduped], 1):
            typer.echo(f"DISPATCH_FIX tick {i}/{len(filed) + len(deduped)} "
                       f"(creator={repair_creator})")
            proc = subprocess.run(
                [str(SKILLS_ROOT / "project-watchdog" / "run.sh"),
                 "tick", "--apply", "--project", "agent-skills", "--max-tickets", "1"],
                capture_output=True, text=True, env=env,
                cwd=SKILLS_ROOT / "project-watchdog",
            )
            tail = (proc.stdout or proc.stderr)[-300:].replace("\n", " | ")
            typer.echo(f"  tick exit {proc.returncode}: {tail}")
    typer.echo(f"EVAL_LOOP_RESULT: {'CONVERGED' if not failed else 'OPEN'} "
               f"failed={len(failed)} filed={len(filed)} deduped={len(deduped)}")
    return len(failed)


@app.command()
def main(
    fixture: Path = typer.Option(SKILL_ROOT / "fixtures" / "agentic_eval_live_subset.json",
                                 "--fixture", help="Manifest to run."),
    apply: bool = typer.Option(False, "--apply", help="Actually file tickets (preview otherwise)."),
    dispatch_fix: bool = typer.Option(
        False, "--dispatch-fix",
        help="After filing, run one bounded project-watchdog tick per ticket with the "
             "chosen repair creator (diagnose, fix in an isolated worktree, close with "
             "proof; the reviewer seat stays a different model family). Sequential: one "
             "ticket, one tick, then the next. Requires --apply."),
    repair_creator: str = typer.Option(
        "gpt-5.5-high", "--repair-creator",
        help="Creator seat for dispatched repairs (operator default: gpt-5.5 high reasoning)."),
    until_pass: bool = typer.Option(
        False, "--until-pass",
        help="Keep looping run -> ticket -> fix -> re-run until every case passes or "
             "--max-iterations is hit. Implies --apply --dispatch-fix semantics per tick."),
    max_iterations: int = typer.Option(
        5, "--max-iterations",
        help="Hard cap on --until-pass ticks; a loop that cannot converge in this many "
             "rounds needs a human, not more rounds."),
    skip_run: Path = typer.Option(None, "--from-report",
                                  help="Skip running; ticket failures from this existing report."),
) -> None:
    if not until_pass:
        failed = _tick(fixture, apply, dispatch_fix, repair_creator, skip_run)
        raise typer.Exit(1 if failed else 0)
    if not apply:
        typer.echo("--until-pass requires --apply (the loop must file and fix, "
                   "not preview forever)", err=True)
        raise typer.Exit(2)
    for iteration in range(1, max_iterations + 1):
        typer.echo(f"=== EVAL_LOOP ITERATION {iteration}/{max_iterations} ===")
        failed = _tick(fixture, True, True, repair_creator, None)
        if not failed:
            typer.echo(f"EVAL_LOOP_CONVERGED after {iteration} iteration(s)")
            raise typer.Exit(0)
    typer.echo(f"EVAL_LOOP_EXHAUSTED: still {failed} failing after "
               f"{max_iterations} iterations -- needs a human", err=True)
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
