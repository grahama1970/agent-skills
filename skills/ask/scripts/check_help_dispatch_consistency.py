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

Usage: python check_help_dispatch_consistency.py [--skip-compile]
"""

from __future__ import annotations

import argparse
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-compile", action="store_true")
    args = ap.parse_args()
    help_text = _help_text()
    run_src = RUN_SH.read_text(encoding="utf-8")
    check_advertised_shortcuts_dispatch(help_text, run_src)
    check_no_contradictory_removal(help_text)
    check_shortcut_compiles_to_tau(args.skip_compile)
    if FAILURES:
        print("FAILED GATES: " + ", ".join(FAILURES))
        return 1
    print("HELP_DISPATCH_CONSISTENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
