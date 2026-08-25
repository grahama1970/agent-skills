#!/usr/bin/env python3
"""/ask one-shot: the same question to N seats, answers per seat.

Not a roundtable and not a competition: no consensus step, no judge, no
quorum refusal. By default, browser seats are provisioned into one shared
reviewer window so the operator can inspect the web models in one place. The
legacy isolated layout remains available when per-window visibility isolation
is more important than a self-contained review surface. The deliverable is a
per-seat table: the answer (path + first line) or the named blocker.

Readiness semantics: exit 0 when at least --min-answered seats answered;
exit 3 when every lane was honest but answers fell below that floor; exit 1
only for dishonest lanes (no answer AND no named failure_code) or runner
errors. A one-shot with 1/3 answers is a usable result, not a failure.

Every lane is nonce-bound: the prompt embeds a fresh token the answer must
echo, so a stale artifact can never be graded as this run's answer.
"""
from __future__ import annotations

import concurrent.futures
import json
import subprocess
import uuid
from pathlib import Path

import typer

app = typer.Typer(add_completion=False)

SKILL_ROOT = Path(__file__).resolve().parents[1]


def _lane_from_run_dir(handler: str, run_dir: Path, nonce: str) -> dict:
    lane: dict = {"handler": handler, "ask_id": run_dir.name, "run_dir": str(run_dir)}
    response, failure = "", None
    node_dir = run_dir / "node-artifacts" / f"handler-{handler.replace('.', '-')}"
    candidate_dirs = [node_dir] if node_dir.is_dir() else sorted((run_dir / "node-artifacts").glob("handler-*"))
    for candidate in candidate_dirs:
        rp = candidate / "node-receipt.json"
        if rp.is_file():
            try:
                receipt = json.loads(rp.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                receipt = {}
            failure = receipt.get("failure_code") or failure
        resp = candidate / "response.md"
        if candidate.name == f"handler-{handler.replace('.', '-')}" and resp.is_file():
            response = resp.read_text(errors="replace")
            lane["response_path"] = str(resp)
            break
    if response.strip():
        if nonce not in response:
            lane.update({"state": "STALE_OR_UNBOUND",
                         "detail": "response does not echo this run's nonce"})
        else:
            first = next((ln for ln in response.splitlines() if ln.strip()), "")
            lane.update({"state": "ANSWERED", "chars": len(response), "first_line": first[:120]})
    elif failure:
        lane.update({"state": "NAMED_BLOCKER", "failure_code": failure})
    else:
        lane.update({"state": "DISHONEST", "detail": "no answer and no failure_code"})
    return lane


def _one(handler: str, question: str, nonce: str, timeout: int, out_root: Path,
         attachments: list[Path] | None = None, browser_tab_lifecycle: str = "auto") -> dict:
    prompt = (f"{question}\n\nEnd your reply with this exact line so the result "
              f"can be verified: {nonce}")
    ask_id = f"one-shot-{nonce.lower()}-{handler.replace('.', '-')}"
    cmd = [str(SKILL_ROOT / "run.sh"), "tau-dag", prompt,
           "--repo", "local/agent-skills", "--target", ask_id,
           "--immutable-goal", "Answer the question or name the blocker.",
           "--dag-template", "single-call", "--handler", handler,
           "--ask-id", ask_id,
           "--browser-tab-lifecycle", browser_tab_lifecycle,
           "--poll-timeout-seconds", str(timeout), "--execute", "--json"]
    for att in attachments or []:
        # The lane's tau worker runs from its own cwd; a relative path that is
        # readable here is unreadable there (browser_attachment_missing,
        # observed 2026-08-19). Resolve before handing over, and fail closed
        # NOW if the file does not exist rather than after a browser round.
        resolved = Path(att).resolve()
        if not resolved.is_file():
            raise typer.BadParameter(f"attachment not readable: {att}")
        cmd += ["--attach-file", str(resolved)]
    lane: dict = {"handler": handler, "ask_id": ask_id}
    proc = None
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout + 300, cwd=SKILL_ROOT)
        text = proc.stdout
        result = json.loads(text[text.index("{"):text.rindex("}") + 1])
    except Exception as exc:
        # A wrapper error MUST carry the child's own words, or the lane is a
        # dead end (observed 2026-08-20: 'substring not found' with the real
        # refusal discarded in the child's stderr).
        lane.update({
            "state": "RUNNER_ERROR",
            "error": str(exc)[:200],
            "child_exit": getattr(proc, "returncode", None),
            "child_stdout_tail": (getattr(proc, "stdout", "") or "")[-400:],
            "child_stderr_tail": (getattr(proc, "stderr", "") or "")[-400:],
        })
        return lane
    run_dir = Path(str(((result.get("execution") or {}).get("run_dir"))
                       or ((result.get("bundle") or {}).get("run_dir")) or ""))
    if run_dir.is_dir():
        return _lane_from_run_dir(handler, run_dir, nonce)
    else:
        # A zero-lane run whose seat removal WAS recorded is a named blocker
        # (same contract as live_seat_probe, 2026-08-19); an unrecorded dead
        # end stays dishonest.
        removed = result.get("removed_seats") or []
        if handler in removed:
            lane.update({"state": "NAMED_BLOCKER",
                         "failure_code": f"{handler}: removed by availability selection"})
        else:
            lane.update({"state": "DISHONEST", "detail": "no answer and no failure_code"})
    return lane


def _shared(
    handlers: list[str],
    question: str,
    nonce: str,
    timeout: int,
    attachments: list[Path] | None = None,
    browser_tab_lifecycle: str = "fresh-shared-keep",
) -> dict[str, dict]:
    prompt = (f"{question}\n\nEnd your reply with this exact line so the result "
              f"can be verified: {nonce}")
    ask_id = f"one-shot-{nonce.lower()}-shared"
    cmd = [str(SKILL_ROOT / "run.sh"), "tau-dag", prompt,
           "--repo", "local/agent-skills", "--target", ask_id,
           "--immutable-goal", "Each requested seat answers the question or names the blocker.",
           "--dag-template", "roundtable", "--topology", "concurrent",
           "--ask-id", ask_id,
           "--browser-tab-lifecycle", browser_tab_lifecycle,
           "--poll-timeout-seconds", str(timeout), "--execute", "--json"]
    for handler in handlers:
        cmd += ["--handler", handler]
    for att in attachments or []:
        resolved = Path(att).resolve()
        if not resolved.is_file():
            raise typer.BadParameter(f"attachment not readable: {att}")
        cmd += ["--attach-file", str(resolved)]
    proc = None
    lanes: dict[str, dict] = {}
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout + 300, cwd=SKILL_ROOT)
        text = proc.stdout
        result = json.loads(text[text.index("{"):text.rindex("}") + 1])
    except Exception as exc:
        for handler in handlers:
            lanes[handler] = {
                "handler": handler,
                "ask_id": ask_id,
                "state": "RUNNER_ERROR",
                "error": str(exc)[:200],
                "child_exit": getattr(proc, "returncode", None),
                "child_stdout_tail": (getattr(proc, "stdout", "") or "")[-400:],
                "child_stderr_tail": (getattr(proc, "stderr", "") or "")[-400:],
            }
        return lanes
    run_dir = Path(str(((result.get("execution") or {}).get("run_dir"))
                       or ((result.get("bundle") or {}).get("run_dir")) or ""))
    removed = set(result.get("removed_seats") or [])
    for handler in handlers:
        if handler in removed:
            lanes[handler] = {
                "handler": handler,
                "ask_id": ask_id,
                "run_dir": str(run_dir),
                "state": "NAMED_BLOCKER",
                "failure_code": f"{handler}: removed by availability selection",
            }
        elif run_dir.is_dir():
            lanes[handler] = _lane_from_run_dir(handler, run_dir, nonce)
        else:
            lanes[handler] = {
                "handler": handler,
                "ask_id": ask_id,
                "state": "DISHONEST",
                "detail": "no run_dir and no removed_seats entry",
            }
    return lanes


@app.command()
def main(
    question: str = typer.Argument(...),
    handler: list[str] = typer.Option(..., "--handler", help="Seat; repeat for several."),
    timeout: int = typer.Option(900, "--timeout"),
    min_answered: int = typer.Option(1, "--min-answered"),
    out_dir: Path = typer.Option(Path("/tmp/ask-one-shot"), "--out-dir"),
    attach_file: list[Path] = typer.Option(None, "--attach-file",
                                           help="Forwarded to each lane's browser submit. Repeat per file."),
    window_layout: str = typer.Option(
        "shared",
        "--window-layout",
        help="Browser layout: shared keeps all web model tabs in one reviewer window; isolated uses one Tau run/window per seat.",
    ),
    browser_tab_lifecycle: str = typer.Option(
        "",
        "--browser-tab-lifecycle",
        help="Override Tau browser lifecycle. Defaults to fresh-shared-keep for shared and auto for isolated.",
    ),
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    nonce = f"ONESHOT-{uuid.uuid4().hex[:8].upper()}"
    lanes: dict[str, dict] = {}
    layout = (window_layout or "shared").strip().lower()
    if layout not in {"shared", "isolated"}:
        raise typer.BadParameter("window_layout must be shared or isolated")
    if layout == "shared":
        lifecycle = browser_tab_lifecycle or "fresh-shared-keep"
        lanes = _shared(handler, question, nonce, timeout, list(attach_file or []), lifecycle)
        for h in handler:
            l = lanes[h]
            detail = l.get("first_line") or l.get("failure_code") or l.get("detail") or l.get("error") or ""
            if l["state"] == "RUNNER_ERROR" and l.get("child_stderr_tail"):
                detail = f"{detail} | child stderr: {l['child_stderr_tail'][-160:]}"
            typer.echo(f"SEAT {h}: {l['state']}  {detail}")
    else:
        lifecycle = browser_tab_lifecycle or "auto"
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(handler)) as pool:
            futures = {pool.submit(_one, h, question, nonce, timeout, out_dir, list(attach_file or []), lifecycle): h
                       for h in handler}
            for fut in concurrent.futures.as_completed(futures):
                h = futures[fut]
                lanes[h] = fut.result()
                l = lanes[h]
                detail = (l.get("first_line") or l.get("failure_code") or l.get("detail")
                          or l.get("error") or "")
                if l["state"] == "RUNNER_ERROR" and l.get("child_stderr_tail"):
                    detail = f"{detail} | child stderr: {l['child_stderr_tail'][-160:]}"
                typer.echo(f"SEAT {h}: {l['state']}  {detail}")
    answered = [h for h, l in lanes.items() if l["state"] == "ANSWERED"]
    dishonest = [h for h, l in lanes.items() if l["state"] in {"DISHONEST", "RUNNER_ERROR", "STALE_OR_UNBOUND"}]
    readiness = "READY" if len(answered) >= max(min_answered, 1) else "NOT_READY"
    if readiness == "READY" and len(answered) < len(handler) - len(dishonest):
        readiness = "DEGRADED"
    (out_dir / "one-shot-verdict.json").write_text(json.dumps({
        "schema": "ask.one_shot_verdict.v1", "nonce": nonce,
        "window_layout": layout,
        "browser_tab_lifecycle": lifecycle,
        "lanes": lanes, "answered": len(answered),
        "dishonest": dishonest, "readiness": readiness,
    }, indent=2) + "\n")
    typer.echo(f"ONE_SHOT: {len(answered)}/{len(handler)} answered, readiness {readiness}")
    for h in answered:
        typer.echo(f"ANSWER {h}: {lanes[h].get('response_path')}")
    if dishonest:
        typer.echo("DISHONEST_LANES: " + ", ".join(dishonest), err=True)
        raise typer.Exit(1)
    if readiness == "NOT_READY":
        typer.echo("ONE_SHOT_NOT_READY: honest, but below the answered floor", err=True)
        raise typer.Exit(3)


if __name__ == "__main__":
    app()
