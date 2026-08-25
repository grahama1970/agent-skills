"""Gate: /ask --help must not contradict what run.sh actually dispatches.

Motivating incident (2026-08-13): --help advertised `webgpt <question>` as a
supported shortcut on one line and declared "WebGPT has been removed from /ask.
Use $surf webgpt.submit ... directly" 70 lines later. Both statements shipped
for months. An agent read the removal paragraph, believed the documented route
was dead, and bypassed the Tau harness with raw surf calls — exactly the
layering violation /ask exists to prevent. Docs that contradict dispatch are
not cosmetic: they route callers around the harness.

Checks (compares two INDEPENDENT sources — the help text and the dispatch
code — so it cannot pass by our code agreeing with itself):
  1. every handler shortcut advertised in --help has a real dispatch case
  2. --help contains no blanket "removed from /ask" claim for a command it
     still advertises
  3. the advertised browser-handler shortcut really compiles to a Tau DAG
     (proves /ask executes browser handlers through Tau, not around it)
  4. that DAG's timeouts can actually cover a normal webgpt Pro call
     (15-20 min); a flat 300s node default made failure certain
  5. every browser submit path passes --stable-stall-ms, so a silently
     reasoning model is not mistaken for a stalled one
  6. the low-cognitive-load help contains correct one-shot, roundtable, and
     compete examples so project agents do not invent the invocation shape

Usage: python check_help_dispatch_consistency.py [--skip-compile]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ASK_DIR = Path(__file__).resolve().parents[1]
RUN_SH = ASK_DIR / "run.sh"

FAILURES: list[str] = []


def gate(name: str, ok: bool, detail: str) -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    if not ok:
        FAILURES.append(name)


def _help_text() -> str:
    proc = subprocess.run(
        [str(RUN_SH), "--help"], capture_output=True, text=True, timeout=120
    )
    return proc.stdout + proc.stderr


def check_advertised_shortcuts_dispatch(help_text: str, run_src: str) -> None:
    """Anything --help lists as a handler shortcut must have a dispatch case."""
    advertised = set(re.findall(r"^\s+(web[a-z]+) <question>", help_text, re.M))
    # the shortcut line also names siblings in prose: "(also webclaude/webkimi/...)"
    for m in re.finditer(r"\(also ([a-z/]+)\)", help_text):
        advertised.update(p for p in m.group(1).split("/") if p.startswith("web"))
    if not advertised:
        gate("shortcuts-advertised", False, "--help advertises no handler shortcut at all")
        return
    # Behavioral probe, not text matching: invoking the shortcut with no
    # question must print its own usage naming the tau-dag route. Text
    # matching missed the alternation case (webgpt|webclaude|...) and would
    # break again on any dispatch-syntax change.
    missing = []
    for h in sorted(advertised):
        proc = subprocess.run(
            [str(RUN_SH), h], capture_output=True, text=True, timeout=120
        )
        blob = proc.stdout + proc.stderr
        if "tau-dag" not in blob or f"--handler {h}" not in blob:
            missing.append(h)
    gate(
        "advertised-shortcuts-dispatch",
        not missing,
        f"advertised={sorted(advertised)}; not routed to tau-dag={missing}",
    )


def check_no_contradictory_removal(help_text: str) -> None:
    """No blanket 'removed from /ask' claim about a still-advertised command."""
    advertised = set(re.findall(r"^\s+(web[a-z]+) <question>", help_text, re.M))
    offenders = []
    for line in help_text.splitlines():
        low = line.lower()
        if "removed from /ask" not in low and "has been removed" not in low:
            continue
        # A precise statement naming the removed SUBCOMMAND is fine; a blanket
        # claim about a command still advertised as a shortcut is not.
        for h in advertised:
            if h in low and "-project" not in low and "direct" not in low:
                offenders.append(line.strip()[:100])
    gate(
        "no-contradictory-removal-claim",
        not offenders,
        f"{len(offenders)} line(s) declare a still-advertised command removed: {offenders[:2]}",
    )


def check_simple_mode_examples(help_text: str) -> None:
    required = {
        "one-shot-example": [
            "./run.sh one-shot",
            "--handler webkimi",
            "--handler webgpt",
            "--attach-file",
            "--out-dir",
        ],
        "roundtable-example": [
            "./run.sh tau-dag",
            "--dag-template roundtable",
            "--topology concurrent",
            "--immutable-goal",
            "--execute",
            "--json",
        ],
        "compete-example": [
            "./run.sh compete",
            "--criterion correctness",
            "--criterion minimality",
            "--immutable-goal",
            "--execute",
            "--json",
        ],
        "browser-window-policy-note": [
            "one reviewer window per seat",
            "ASK_REVIEWER_DESKTOP=1",
            "Desktop 2",
        ],
    }
    missing = {
        name: [token for token in tokens if token not in help_text]
        for name, tokens in required.items()
    }
    missing = {name: tokens for name, tokens in missing.items() if tokens}
    gate("simple-mode-examples-present", not missing, f"missing={missing}")


def check_shortcut_compiles_to_tau(skip: bool) -> None:
    """The advertised shortcut must really compile to a Tau DAG."""
    if skip:
        gate("shortcut-compiles-to-tau-dag", True, "skipped by --skip-compile")
        return
    proc = subprocess.run(
        [str(RUN_SH), "webgpt", "--compile-only", "What is 2 + 2?"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    out = proc.stdout
    ok = proc.returncode == 0 and '"schema": "ask.tau_dag_cli_result.v1"' in out
    gate(
        "shortcut-compiles-to-tau-dag",
        ok,
        f"exit={proc.returncode}; tau_dag_cli_result schema present={'yes' if ok else 'no'}",
    )


def check_browser_timeouts_are_viable(skip: bool) -> None:
    """A browser handler's timeouts must cover a normal webgpt Pro call.

    Graham: "a webgpt call normally takes 15-20 minutes". The DAG shipped a flat
    limits.default_timeout_seconds=300 and a 900s worker budget, so a normal
    call was ~certain to be killed mid-generation (2026-08-13). Require both to
    cover a 20-minute answer with margin.
    """
    if skip:
        gate("browser-timeouts-viable", True, "skipped by --skip-compile")
        return
    min_required = 1200  # 20 minutes, the top of a normal webgpt Pro call
    proc = subprocess.run(
        [str(RUN_SH), "webgpt", "--compile-only", "timeout gate probe"],
        capture_output=True,
        text=True,
        timeout=400,
    )
    try:
        payload = json.loads(proc.stdout[proc.stdout.find("{") :])
        bundle = payload["bundle"]
        # dag_path may point at the run directory OR at dag.json inside it.
        dag_path = Path(bundle["dag_path"])
        run_root = dag_path.parent if dag_path.name.endswith(".json") else dag_path
        dag = (
            bundle["dag"]
            if isinstance(bundle.get("dag"), dict)
            else json.loads((run_root / "dag.json").read_text(encoding="utf-8"))
        )
        node_default = int(dag["limits"]["default_timeout_seconds"])
        spec = json.loads(
            (
                run_root / "command-specs" / "handler-webgpt" / "tau-dispatch-command.json"
            ).read_text(encoding="utf-8")
        )
        cmd = spec["command"]
        worker_timeout = int(cmd[cmd.index("--timeout") + 1])
    except Exception as exc:  # noqa: BLE001 - any parse failure is a gate failure
        gate("browser-timeouts-viable", False, f"could not read compiled timeouts: {exc}")
        return
    ok = node_default >= min_required and worker_timeout >= min_required
    gate(
        "browser-timeouts-viable",
        ok,
        f"node default={node_default}s, webgpt worker={worker_timeout}s "
        f"(both must be >= {min_required}s for a 15-20 min Pro call)",
    )


def check_reasoning_stall_guard(skip: bool) -> None:
    """Browser submits must not abandon a quiet reasoning model.

    surf's --stable-stall-ms defaults to 30s: if assistant text stops changing
    for that long WITHOUT the sentinel, it returns empty. ChatGPT Pro thinks
    silently for minutes, so on 2026-08-13 a complete 15k-character answer was
    discarded twice (lane-diagnostics: response_rendered_capture_missed /
    missing_sentinel) — the sentinel was in the tab both times. Every browser
    submit path must therefore pass --stable-stall-ms explicitly.
    """
    worker = ASK_DIR / "scripts" / "tau_roundtable_worker.py"
    src = worker.read_text(encoding="utf-8")
    # Count real submit argv builds, not dict lookups: every submit command
    # interpolates str(args.stable_polls) exactly once. Counting the flag string
    # instead would also catch the argparse definition; counting
    # HANDLER_SUBMIT_COMMANDS[...] would catch an error string and a return.
    submits = src.count("str(args.stable_polls),")
    guards = src.count("--stable-stall-ms")
    ok = submits > 0 and guards >= submits
    gate(
        "reasoning-stall-guard",
        ok,
        f"{guards} --stable-stall-ms guard(s) for {submits} browser submit path(s)",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-compile", action="store_true")
    args = ap.parse_args()
    help_text = _help_text()
    run_src = RUN_SH.read_text(encoding="utf-8")
    check_advertised_shortcuts_dispatch(help_text, run_src)
    check_no_contradictory_removal(help_text)
    check_simple_mode_examples(help_text)
    check_shortcut_compiles_to_tau(args.skip_compile)
    check_browser_timeouts_are_viable(args.skip_compile)
    check_reasoning_stall_guard(args.skip_compile)
    if FAILURES:
        print("FAILED GATES: " + ", ".join(FAILURES))
        return 1
    print("HELP_DISPATCH_CONSISTENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
