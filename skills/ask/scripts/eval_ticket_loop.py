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


def _case_identity(case: dict) -> str:
    """Stable machine identity for dedupe (agent-skills#1457).

    An explicit ``case_id`` in the fixture survives renames; the name is only
    the fallback for cases that never declared one. The identity is stamped
    into the ticket body as an ``eval-case-id:`` marker and dedupe matches on
    THAT marker, so `old-name` and `new-name` reports with one identity keep
    one open ticket.
    """
    return str(case.get("case_id") or case.get("name"))


def _find_open_ticket(case: dict) -> int | None:
    """Return the open ticket number for this case identity, else None."""
    identity = _case_identity(case)
    proc = subprocess.run(
        ["gh", "issue", "list", "--repo", REPO, "--state", "open",
         "--search", f'"eval-case-id: {identity}" in:body', "--json", "number,body"],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode == 0:
        try:
            for row in json.loads(proc.stdout or "[]"):
                if f"eval-case-id: {identity}" in (row.get("body") or ""):
                    return int(row["number"])
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
    # Back-compat: tickets filed before the identity marker dedupe by title.
    title = _ticket_title(str(case.get("name")))
    proc = subprocess.run(
        ["gh", "issue", "list", "--repo", REPO, "--state", "open",
         "--search", f'in:title "{title}"', "--json", "number,title"],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        # Fail closed into filing: a dedupe check that cannot read GitHub must
        # not silently suppress a regression ticket.
        return None
    try:
        for row in json.loads(proc.stdout or "[]"):
            if row.get("title") == title:
                return int(row["number"])
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _issue_number_from_output(text: str) -> int | None:
    import re
    m = re.search(r"/issues/(\d+)", text or "")
    return int(m.group(1)) if m else None


def _prior_attempt_summary(issue: int) -> str | None:
    """Bounded summary of the LAST watchdog dispatch for this issue.

    Stateless repair agents repeat identical attempts when nothing tells them
    what was already tried (agent-skills#1460). Reads the watchdog's own
    receipts (newest first) and returns one short block: run id, status, and
    the receipt's summary line when present. Returns None when no prior
    dispatch receipt exists.
    """
    import os
    state_root = Path(os.environ.get("PROJECT_WATCHDOG_STATE_ROOT",
                                     str(Path.home() / ".local" / "state" / "project-watchdog")))
    receipts = state_root / "receipts"
    if not receipts.is_dir():
        return None
    for run_dir in sorted(receipts.iterdir(), key=lambda d: d.name, reverse=True):
        rp = run_dir / "receipt.json"
        if not rp.is_file():
            continue
        try:
            receipt = json.loads(rp.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for handled in receipt.get("handled_issues") or []:
            if isinstance(handled, dict) and int(handled.get("issue_number", -1)) == int(issue):
                return (
                    f"prior-attempt: run {receipt.get('run_id', run_dir.name)} "
                    f"status={handled.get('status') or receipt.get('status')} "
                    f"ok={handled.get('ok')} "
                    f"summary={str(handled.get('summary') or receipt.get('summary') or '')[:300]}"
                )
    return None


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
    ticket_numbers: dict[str, int] = {}
    ticketing_incomplete: list[str] = []
    ticket_runner = str(SKILLS_ROOT / "ticket" / "run.sh")
    import os as _os
    ticket_runner = _os.environ.get("ASK_EVAL_TICKET_CMD", ticket_runner)
    for c in failed:
        title = _ticket_title(c["name"])
        existing = _find_open_ticket(c)
        if existing:
            deduped.append(c["name"])
            ticket_numbers[c["name"]] = existing
            typer.echo(f"TICKET_EXISTS: #{existing} {title}")
            continue
        evidence = "; ".join((c.get("problems") or [])[:4])[:400] or "see report trials"
        evidence += f" | eval-case-id: {_case_identity(c)}"
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
        cmd = [ticket_runner, "bug", title,
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
            num = _issue_number_from_output(proc.stdout)
            if num:
                ticket_numbers[c["name"]] = num
        elif apply:
            ticketing_incomplete.append(c["name"])
    # Atomic ticketing (agent-skills#1458): a FAIL case with neither an open
    # ticket nor a successful filing has no repair unit. Dispatching for the
    # others would let partial coverage masquerade as loop progress.
    if apply and ticketing_incomplete:
        typer.echo("EVAL_LOOP_TICKETING_INCOMPLETE: no dispatch this iteration; "
                   "unticketed FAIL cases: " + ", ".join(ticketing_incomplete), err=True)
        raise typer.Exit(4)
    if dispatch_fix and apply and (filed or deduped):
        # One bounded watchdog tick per outstanding ticket, SEQUENTIALLY:
        # each tick leases one issue, dispatches the creator-reviewer Tau DAG
        # (creator = the operator-chosen gpt-5.5 high seat, reviewer a
        # different family), and posts its receipt before the next tick runs.
        import os
        env = dict(os.environ)
        env["PROJECT_WATCHDOG_REPAIR_CREATOR"] = repair_creator
        for i, name in enumerate([*filed, *deduped], 1):
            issue = ticket_numbers.get(name)
            typer.echo(f"DISPATCH_FIX tick {i}/{len(filed) + len(deduped)} "
                       f"(creator={repair_creator}, issue={issue or 'unknown'})")
            if issue and name in deduped:
                # Persistent regression: forward what the LAST attempt did so
                # the next stateless repair agent does not repeat it
                # (agent-skills#1460). The comment lands on the ticket, which
                # is the only context the repair node receives.
                summary = _prior_attempt_summary(issue)
                if summary:
                    subprocess.run(
                        ["gh", "issue", "comment", str(issue), "--repo", REPO,
                         "--body", f"eval-loop {summary}"],
                        capture_output=True, text=True, timeout=60,
                    )
                    typer.echo(f"  PRIOR_ATTEMPT_FORWARDED to #{issue}: {summary[:120]}")
            tick_cmd = [str(SKILLS_ROOT / "project-watchdog" / "run.sh"),
                        "tick", "--apply", "--project", "agent-skills", "--max-tickets", "1"]
            if issue:
                # Targeted repair (agent-skills#1456): this tick may lease ONLY
                # the ticket for this iteration's regression, or refuse.
                tick_cmd += ["--issue", str(issue)]
            proc = subprocess.run(
                tick_cmd,
                capture_output=True, text=True, env=env,
                cwd=SKILLS_ROOT / "project-watchdog",
            )
            tail = (proc.stdout or proc.stderr)[-300:].replace("\n", " | ")
            typer.echo(f"  tick exit {proc.returncode}: {tail}")
    typer.echo(f"EVAL_LOOP_RESULT: {'CONVERGED' if not failed else 'OPEN'} "
               f"failed={len(failed)} filed={len(filed)} deduped={len(deduped)}")
    return [c["name"] for c in failed], [c["name"] for c in passed]


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
    stability: int = typer.Option(
        2, "--stability",
        help="Consecutive passing iterations a previously-failed case must hold before "
             "the loop may declare CONVERGED (flap detection, agent-skills#1459)."),
    max_eval_runs: int = typer.Option(
        0, "--max-eval-runs",
        help="Budget: maximum runner invocations this loop may consume; 0 = unlimited. "
             "Refuses further iterations BEFORE running (agent-skills#1462)."),
    skip_run: Path = typer.Option(None, "--from-report",
                                  help="Skip running; ticket failures from this existing report."),
) -> None:
    if not until_pass:
        failed, _passed = _tick(fixture, apply, dispatch_fix, repair_creator, skip_run)
        raise typer.Exit(1 if failed else 0)
    if not apply:
        typer.echo("--until-pass requires --apply (the loop must file and fix, "
                   "not preview forever)", err=True)
        raise typer.Exit(2)
    import os
    # Fault-injection hook: a comma-separated report sequence stands in for
    # live runner invocations, one per iteration, so convergence semantics are
    # testable without hours of browser time. Each consumed report still
    # counts against the eval-run budget.
    reports_seq = [Path(x) for x in os.environ.get("ASK_EVAL_LOOP_REPORTS_SEQ", "").split(",") if x]
    ever_failed: set[str] = set()
    pass_streak: dict[str, int] = {}
    runs_done = 0
    failed: list[str] = []
    for iteration in range(1, max_iterations + 1):
        # Budget gate (agent-skills#1462): refuse BEFORE the runner and before
        # any dispatch when another eval run cannot be afforded. Iteration
        # count is a weak proxy for expensive live/browser work.
        if max_eval_runs and runs_done >= max_eval_runs:
            typer.echo(f"EVAL_LOOP_BUDGET_EXHAUSTED: {runs_done}/{max_eval_runs} eval runs "
                       f"consumed; refusing iteration {iteration} before invoking the runner "
                       "or the watchdog", err=True)
            raise typer.Exit(5)
        typer.echo(f"=== EVAL_LOOP ITERATION {iteration}/{max_iterations} ===")
        seq_report = reports_seq[iteration - 1] if len(reports_seq) >= iteration else None
        failed, passed = _tick(fixture, True, True, repair_creator, seq_report)
        runs_done += 1
        # Flap detection (agent-skills#1459): a case that has EVER failed in
        # this invocation must pass --stability consecutive iterations before
        # the loop may declare CONVERGED; current-iteration state alone lets an
        # intermittent regression slip through as green.
        for name in failed:
            ever_failed.add(name)
            pass_streak[name] = 0
        for name in passed:
            if name in ever_failed:
                pass_streak[name] = pass_streak.get(name, 0) + 1
        unstable = sorted(n for n in ever_failed if pass_streak.get(n, 0) < stability)
        if not failed and not unstable:
            typer.echo(f"EVAL_LOOP_CONVERGED after {iteration} iteration(s)")
            raise typer.Exit(0)
        if not failed and unstable:
            typer.echo("EVAL_LOOP_FLAPPING: all green this iteration, but these cases have "
                       f"not yet held {stability} consecutive passes: " + ", ".join(unstable))
    typer.echo(f"EVAL_LOOP_EXHAUSTED: still failing={failed} "
               f"unstable={sorted(n for n in ever_failed if pass_streak.get(n, 0) < stability)} "
               f"after {max_iterations} iterations -- needs a human", err=True)
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
