#!/usr/bin/env python3
"""/ask one-shot: the same question to N seats concurrently, answers per seat.

Not a roundtable and not a competition: no consensus step, no judge, no
quorum refusal. Each seat runs as its own single-call Tau DAG, fully
independent, so one seat's failure cannot touch another lane even in
principle. The deliverable is a per-seat table: the answer (path + first
line) or the named blocker.

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


def _one(handler: str, question: str, nonce: str, timeout: int, out_root: Path) -> dict:
    prompt = (f"{question}\n\nEnd your reply with this exact line so the result "
              f"can be verified: {nonce}")
    ask_id = f"one-shot-{nonce.lower()}-{handler.replace('.', '-')}"
    cmd = [str(SKILL_ROOT / "run.sh"), "tau-dag", prompt,
           "--repo", "local/agent-skills", "--target", ask_id,
           "--immutable-goal", "Answer the question or name the blocker.",
           "--dag-template", "single-call", "--handler", handler,
           "--ask-id", ask_id,
           "--poll-timeout-seconds", str(timeout), "--execute", "--json"]
    lane: dict = {"handler": handler, "ask_id": ask_id}
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout + 300, cwd=SKILL_ROOT)
        text = proc.stdout
        result = json.loads(text[text.index("{"):text.rindex("}") + 1])
    except Exception as exc:
        lane.update({"state": "RUNNER_ERROR", "error": str(exc)[:200]})
        return lane
    run_dir = Path(str(((result.get("execution") or {}).get("run_dir"))
                       or ((result.get("bundle") or {}).get("run_dir")) or ""))
    lane["run_dir"] = str(run_dir)
    response, failure = "", None
    if run_dir.is_dir():
        for node_dir in sorted((run_dir / "node-artifacts").glob("handler-*")):
            rp = node_dir / "node-receipt.json"
            if rp.is_file():
                failure = json.loads(rp.read_text()).get("failure_code") or failure
            resp = node_dir / "response.md"
            if resp.is_file():
                response = resp.read_text(errors="replace")
                lane["response_path"] = str(resp)
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


@app.command()
def main(
    question: str = typer.Argument(...),
    handler: list[str] = typer.Option(..., "--handler", help="Seat; repeat for several."),
    timeout: int = typer.Option(900, "--timeout"),
    min_answered: int = typer.Option(1, "--min-answered"),
    out_dir: Path = typer.Option(Path("/tmp/ask-one-shot"), "--out-dir"),
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    nonce = f"ONESHOT-{uuid.uuid4().hex[:8].upper()}"
    lanes: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(handler)) as pool:
        futures = {pool.submit(_one, h, question, nonce, timeout, out_dir): h for h in handler}
        for fut in concurrent.futures.as_completed(futures):
            h = futures[fut]
            lanes[h] = fut.result()
            l = lanes[h]
            detail = l.get("first_line") or l.get("failure_code") or l.get("detail") or l.get("error") or ""
            typer.echo(f"SEAT {h}: {l['state']}  {detail}")
    answered = [h for h, l in lanes.items() if l["state"] == "ANSWERED"]
    dishonest = [h for h, l in lanes.items() if l["state"] in {"DISHONEST", "RUNNER_ERROR", "STALE_OR_UNBOUND"}]
    readiness = "READY" if len(answered) >= max(min_answered, 1) else "NOT_READY"
    if readiness == "READY" and len(answered) < len(handler) - len(dishonest):
        readiness = "DEGRADED"
    (out_dir / "one-shot-verdict.json").write_text(json.dumps({
        "schema": "ask.one_shot_verdict.v1", "nonce": nonce,
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
