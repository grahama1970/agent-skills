#!/usr/bin/env python3
"""Second rung of the live E2E ladder: a real task across mixed seats.

The human-equivalent prompt: "write a Python function that adds two numbers,
complying with best-practices-python". Seats run as a concurrent roundtable
through the real tau-dag path (browser and API lanes as peers).

The per-lane oracle is STRUCTURAL AND EXECUTED, not a regex smoke test
(review finding 2026-08-19): the response must carry a fenced python block
whose AST contains exactly one function with two annotated parameters, a
return annotation, and a docstring, with no classes or asserts -- and the
function must then actually add, proven by running it in a subprocess on
integer, negative, zero, and float vectors. A lane is honest when it meets
that bar OR names a failure_code. Self-declared success is worth nothing;
the artifact is executed.

Provenance: every run carries a fresh nonce that seats must echo as a comment
inside the code block; the probe refuses to score a run directory whose
request does not contain this invocation's nonce, so a stale green run can
never be graded in place of a failed current one.

Verdicts are written to <out-dir>/probe-verdict.json (authoritative for
status tables -- Tau's aggregate status alone must never stand in for it).
"""
from __future__ import annotations

import ast
import hashlib
import json
import random
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

import typer

app = typer.Typer(add_completion=False)

SKILL_ROOT = Path(__file__).resolve().parents[1]

PROMPT_TEMPLATE = (
    "Write one Python function that adds two numbers and return it in a single "
    "fenced python block. It must comply with best-practices-python: a module "
    "docstring naming purpose, inputs, outputs, and failure modes; type hints "
    "on the signature; a function docstring; no classes; no runtime asserts. "
    "The FIRST line inside the fenced block must be exactly this comment: "
    "# probe-nonce: {nonce} . No prose outside the fenced block."
)

FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S)

EXEC_VECTORS = [((2, 3), 5), ((-1, 1), 0), ((0, 0), 0), ((2.5, 3.5), 6.0)]


def _property_vectors(seed: str, count: int = 4) -> list[tuple[tuple[float, float], float]]:
    """Seed-derived vectors so an implementation cannot overfit the fixed set.

    The seed is the run nonce and is recorded in the verdict, so any grading
    decision can be reproduced exactly.
    """
    rng = random.Random(seed)
    vectors: list[tuple[tuple[float, float], float]] = []
    for _ in range(count):
        a = round(rng.uniform(-1e6, 1e6), 3)
        b = round(rng.uniform(-1e6, 1e6), 3)
        vectors.append(((a, b), a + b))
    return vectors


def _structural_verdict(code: str) -> tuple[str | None, list[str]]:
    """Return (function_name, problems). Structural floor via the AST."""
    problems: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return None, [f"syntax error: {exc.msg} (line {exc.lineno})"]
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    if len(funcs) != 1:
        problems.append(f"expected exactly one function, found {len(funcs)}")
    if any(isinstance(n, ast.ClassDef) for n in ast.walk(tree)):
        problems.append("contains a class")
    if any(isinstance(n, ast.Assert) for n in ast.walk(tree)):
        problems.append("contains a runtime assert")
    if not funcs:
        return None, problems
    fn = funcs[0]
    args = fn.args.args
    if len(args) != 2:
        problems.append(f"function takes {len(args)} args, expected 2")
    if any(a.annotation is None for a in args):
        problems.append("missing parameter type hints")
    if fn.returns is None:
        problems.append("missing return annotation")
    if ast.get_docstring(fn) is None:
        problems.append("missing function docstring")
    return fn.name, problems


def _execution_verdict(code: str, fn_name: str, seed: str) -> list[str]:
    """Run the delivered code in a subprocess and check it actually adds.

    Fixed canonical vectors plus seed-derived property vectors: the fixed set
    catches the obvious, the seeded set defeats overfitting to known inputs.
    """
    checks = "; ".join(
        f"assert {fn_name}(*{list(vec)!r}) == {expected!r}, 'add{vec}!={expected}'"
        for vec, expected in [*EXEC_VECTORS, *_property_vectors(seed)]
    )
    proc = subprocess.run(
        [sys.executable, "-c", code + "\n" + checks],
        capture_output=True, text=True, timeout=20,
    )
    if proc.returncode != 0:
        return [f"execution failed: {(proc.stderr or proc.stdout)[-200:].strip()}"]
    return []


def _floor_verdict(text: str, nonce: str) -> list[str]:
    problems, _digest = _floor_verdict_with_digest(text, nonce)
    return problems


def _floor_verdict_with_digest(text: str, nonce: str) -> tuple[list[str], str | None]:
    """Grade the response; return (problems, sha256 of the exact graded bytes).

    The digest goes into the verdict so any grading decision names precisely
    which bytes were executed -- a review pointed out that without it, an
    ambiguous extraction could display one candidate while executing another.
    """
    blocks = FENCE.findall(text)
    if not blocks:
        return ["no fenced python block"], None
    code = blocks[0]
    digest = hashlib.sha256(code.encode()).hexdigest()
    problems: list[str] = []
    if len(blocks) > 1:
        problems.append(f"expected exactly one fenced python block, found {len(blocks)}")
    if nonce not in code:
        problems.append("probe nonce missing from code block (response not bound to this run)")
    fn_name, structural = _structural_verdict(code)
    problems.extend(structural)
    if fn_name and not structural:
        problems.extend(_execution_verdict(code, fn_name, nonce))
    return problems, digest


@app.command()
def main(
    handler: list[str] = typer.Option(["webgpt", "webclaude", "deepseek-v4-flash"], "--handler"),
    timeout: int = typer.Option(1500, "--timeout"),
    out_dir: Path = typer.Option(Path("/tmp/live-task-probe"), "--out-dir"),
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    nonce = f"TOKEN-{uuid.uuid4().hex[:10]}"
    prompt = PROMPT_TEMPLATE.format(nonce=nonce)
    cmd = [str(SKILL_ROOT / "run.sh"), "tau-dag", prompt,
           "--repo", "local/agent-skills", "--target", f"eval-add-two-{nonce.lower()}",
           "--immutable-goal", "Each seat returns a floor-compliant function or names a blocker.",
           "--dag-template", "roundtable", "--topology", "concurrent",
           "--poll-timeout-seconds", str(timeout), "--execute", "--json"]
    for h in handler:
        cmd += ["--handler", h]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 300, cwd=SKILL_ROOT)
    text = proc.stdout
    try:
        result = json.loads(text[text.index("{"):text.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        typer.echo("TASK_LADDER_RUNNER_ERROR: unparseable tau-dag output", err=True)
        typer.echo(text[-400:], err=True)
        raise typer.Exit(1)
    run_dir = Path(str(((result.get("execution") or {}).get("run_dir"))
                       or ((result.get("bundle") or {}).get("run_dir")) or ""))
    (out_dir / "tau-result.json").write_text(json.dumps(result, indent=2))
    # Provenance gate: this run directory must be OUR run, proven by the nonce
    # in its recorded request. Otherwise refuse to grade it (stale-green risk).
    request_ok = False
    if run_dir.is_dir():
        req_path = run_dir / "request.json"
        if req_path.is_file() and nonce in req_path.read_text(errors="replace"):
            request_ok = True
    if not request_ok:
        typer.echo(f"TASK_LADDER_RUNNER_ERROR: run dir {run_dir} does not carry this "
                   f"invocation's nonce {nonce}; refusing to grade a stale run", err=True)
        raise typer.Exit(1)
    substitutions: dict[str, str] = {}
    removed_seats: set[str] = set()
    sel_path = run_dir / "browser-provider-selection.json"
    if sel_path.is_file():
        sel = json.loads(sel_path.read_text())
        for sub in sel.get("local_substitutions") or []:
            if sub.get("from") and sub.get("to"):
                substitutions[sub["from"]] = sub["to"]
        removed_seats = {
            (r if isinstance(r, str) else str(r.get("handler") or ""))
            for r in sel.get("removed_handlers") or []
        }
    run_alerts: list[str] = []
    exec_path = run_dir / "execution-status.json"
    if exec_path.is_file():
        ex = json.loads(exec_path.read_text())
        if ex.get("status") == "BLOCKED":
            run_alerts = [str(a.get("code")) for a in (ex.get("receipt") or {}).get("alerts") or []]
    lanes: dict[str, dict] = {}
    for node_dir in sorted((run_dir / "node-artifacts").glob("handler-*")):
        seat_id = node_dir.name.replace("handler-", "")
        receipt = {}
        rp = node_dir / "node-receipt.json"
        if rp.is_file():
            receipt = json.loads(rp.read_text())
        response = ""
        resp_path = node_dir / "response.md"
        if resp_path.is_file():
            response = resp_path.read_text(errors="replace")
        lanes[seat_id] = {"receipt": receipt, "response": response}
    claimed: set[str] = set()  # one artifact lane credits at most one requested seat
    verdicts: dict[str, dict] = {}
    violators: list[str] = []
    for seat in handler:
        effective = substitutions.get(seat, seat)
        # Tau normalizes node ids: dots become hyphens (gpt-5.5-low ->
        # handler-gpt-5-5-low). Receipts are the authority; match their naming.
        candidates = [effective, seat, effective.replace(".", "-"), seat.replace(".", "-")]
        lane_key = next((c for c in candidates if c in lanes and c not in claimed), None)
        lane = lanes.get(lane_key, {}) if lane_key else {}
        if lane_key:
            claimed.add(lane_key)
        note = f" (substituted -> {effective})" if effective != seat else ""
        seat_label = seat + note
        response = lane.get("response") or ""
        failure = (lane.get("receipt") or {}).get("failure_code")
        if response.strip():
            missing, graded_sha = _floor_verdict_with_digest(response, nonce)
            if missing:
                typer.echo(f"SEAT {seat_label}: answered but BELOW FLOOR ({'; '.join(missing)})")
                verdicts[seat] = {"state": "BELOW_FLOOR", "problems": missing,
                                  "graded_code_sha256": graded_sha}
                violators.append(seat)
            else:
                typer.echo(f"SEAT {seat_label}: answered, floor-compliant (AST + executed vectors)")
                verdicts[seat] = {"state": "ANSWERED", "problems": [],
                                  "graded_code_sha256": graded_sha}
        elif failure:
            # Rung 3, self-correction: a misnamed model must not dead-end. The
            # honest outcomes are a recorded substitution to a valid catalog
            # model, or a recovery packet relaying the transport's own course
            # correction (scillm's 400 enumerates valid ids).
            if failure == "scillm_model_not_found":
                lane_dir = run_dir / "node-artifacts" / f"handler-{effective.replace('.', '-')}"
                correction = ""
                for packet_name in ("handler-recovery-packet.json", "browser-recovery-packet.json"):
                    pp = lane_dir / packet_name
                    if pp.is_file():
                        packet = json.loads(pp.read_text())
                        correction = " ".join(str(packet.get(k) or "") for k in
                                              ("fallback_instruction", "next_command", "recommended_action"))
                receipt_text = json.dumps(lane.get("receipt") or {})
                has_valid_ids = bool(re.search(r"did you mean|available:|suggested_models|available_models",
                                               (correction + receipt_text), re.I))
                if substitutions.get(seat) or has_valid_ids:
                    typer.echo(f"SEAT {seat_label}: named_blocker {failure} WITH course correction")
                    verdicts[seat] = {"state": "NAMED_BLOCKER", "failure_code": failure,
                                      "course_correction": True}
                else:
                    typer.echo(f"SEAT {seat_label}: named_blocker {failure} but NO SELF-CORRECTION "
                               "(no substitution recorded, no valid-model course correction relayed)")
                    verdicts[seat] = {"state": "NO_SELF_CORRECTION", "failure_code": failure}
                    violators.append(seat)
            else:
                typer.echo(f"SEAT {seat_label}: named_blocker {failure}")
                verdicts[seat] = {"state": "NAMED_BLOCKER", "failure_code": failure}
        elif run_alerts:
            typer.echo(f"SEAT {seat_label}: never dispatched -- run BLOCKED by {','.join(run_alerts)}")
            verdicts[seat] = {"state": "RUN_BLOCKED", "alerts": run_alerts}
            violators.append(seat)
        elif seat in removed_seats:
            # Same contract as the ladder and one-shot (2026-08-20): a seat
            # whose removal IS recorded names its blocker; only an unrecorded
            # dead end is dishonest.
            typer.echo(f"SEAT {seat_label}: named_blocker removed by availability selection")
            verdicts[seat] = {"state": "NAMED_BLOCKER",
                              "failure_code": f"{seat}: removed by availability selection"}
        else:
            typer.echo(f"SEAT {seat_label}: NO ANSWER AND NO FAILURE CODE")
            verdicts[seat] = {"state": "DISHONEST"}
            violators.append(seat)
    answered = [s for s, v in verdicts.items() if v["state"] == "ANSWERED"]
    honesty = f"{len(handler) - len(violators)}/{len(handler)}"
    readiness = "READY" if answered else "NOT_READY"
    if readiness == "READY" and len(answered) < len(handler) - len(violators):
        readiness = "DEGRADED"
    # Bind the verdict to ITS run: request hash + receipt-tree digest mean a
    # copied or stale verdict cannot stand in for a different run's outcome
    # (review finding 2026-08-19). eval_status re-verifies this binding.
    request_sha = hashlib.sha256((run_dir / "request.json").read_bytes()).hexdigest()
    receipt_tree = hashlib.sha256()
    for rp in sorted((run_dir / "node-artifacts").glob("handler-*/node-receipt.json")):
        receipt_tree.update(rp.read_bytes())
    (out_dir / "probe-verdict.json").write_text(json.dumps({
        "schema": "ask.live_task_probe_verdict.v2",
        "nonce": nonce, "run_dir": str(run_dir),
        "run_id": run_dir.name,
        "request_sha256": request_sha,
        "receipt_tree_sha256": receipt_tree.hexdigest(),
        "property_vector_seed": nonce,
        "created_at": time.time(),
        "seats": verdicts, "honesty": honesty,
        "answered": len(answered), "readiness": readiness,
        "violators": violators,
    }, indent=2) + "\n")
    typer.echo(f"TASK_LADDER: {honesty} honest")
    typer.echo(f"TASK_READINESS: {readiness} ({len(answered)}/{len(handler)} answered)")
    if violators:
        if run_alerts:
            typer.echo("RUN_BLOCKED_PANEL: one lane's failure blocked healthy seats ("
                       + ",".join(run_alerts) + ") -- /ask contract requires lane-local degradation", err=True)
        typer.echo("FAILED_SEATS: " + ", ".join(violators), err=True)
        raise typer.Exit(1)
    typer.echo("ALL_SEATS_HONEST_ON_TASK")


if __name__ == "__main__":
    app()
