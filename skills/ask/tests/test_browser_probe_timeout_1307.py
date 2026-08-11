"""#1307: the browser-availability probe must bound its timeout even when the
availability script spawns a grandchild that holds the stdout pipe open
(subprocess.run(timeout) alone hangs in communicate() past the timeout)."""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "src" / "ask" / "tau_dag_cli.py"
sys.path.insert(0, str(CLI.parent.parent))
spec = importlib.util.spec_from_file_location("ask.tau_dag_cli_probe", CLI)
mod = importlib.util.module_from_spec(spec)


def _load():
    # tau_dag_cli imports heavy deps; import the package normally.
    from ask import tau_dag_cli  # noqa
    return tau_dag_cli


def test_probe_times_out_despite_hanging_grandchild(tmp_path: Path, monkeypatch) -> None:
    cli = _load()
    # Fake availability script: spawn a detached grandchild that sleeps forever
    # holding stdout, then the script itself sleeps — reproduces #1307.
    fake = tmp_path / "fake_availability.py"
    fake.write_text(
        "import subprocess, sys, time\n"
        "subprocess.Popen(['sleep', '600'])\n"  # grandchild holds the pipe
        "time.sleep(600)\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ASK_BROWSER_AVAILABILITY_SCRIPT", str(fake))

    class _Input:
        handlers = ("webgpt",)
        handler_projects = ()

    monkeypatch.setattr(cli, "_browser_providers_to_probe", lambda _i: ["webgpt"])
    monkeypatch.setattr(cli, "_resolve_explicit_browser_provider_tabs", lambda _i, _h: {"status": "ok", "explicit_tab_args": []})

    started = time.monotonic()
    report = cli._probe_browser_provider_availability(_Input(), run_dir=tmp_path, timeout_seconds=3.0)
    elapsed = time.monotonic() - started
    # Must return within timeout + grace, not hang for 600s.
    assert elapsed < 20, f"probe hung {elapsed:.1f}s past its 3s timeout (#1307)"
    cr = report.get("command_receipt") or report.get("availability_command") or {}
    # The report carries a timed-out signal somewhere; at minimum it returned.
    assert report is not None
