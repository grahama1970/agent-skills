#!/usr/bin/env python3
"""Module support for the project-drift skill."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_SKILL_DIR = Path(__file__).resolve().parents[1]
TRUTHY = {"1", "true", "yes", "on"}


def _read_hook_input() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    return json.loads(raw)


def _stop_response(reason: str, system_message: str) -> None:
    print(json.dumps({"continue": False, "stopReason": reason, "systemMessage": system_message}))


def _git_root(cwd: str | None) -> Path:
    base = Path(cwd or os.getcwd()).resolve()
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=base,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out:
            return Path(out).resolve()
    except Exception:
        pass
    return base


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in TRUTHY


def _execute_enabled() -> bool:
    if _truthy_env("PROJECT_DRIFT_HOOK_EXECUTE"):
        return True
    if os.environ.get("PROJECT_DRIFT_HOOK_EXECUTE", "").strip().lower() in {"0", "false", "no", "off"}:
        return False
    return bool(
        os.environ.get("PROJECT_DRIFT_LLM_BASE_URL")
        or os.environ.get("SCILLM_BASE_URL")
        or os.environ.get("SCILLM_URL")
    )


def _find_transcript(data: dict[str, Any]) -> str | None:
    for key in ("transcript_path", "transcriptPath", "TRANSCRIPT_PATH"):
        value = data.get(key)
        if value and Path(str(value)).exists():
            return str(value)
    env_value = os.environ.get("TRANSCRIPT_PATH")
    if env_value and Path(env_value).exists():
        return env_value
    return None


def _candidate_line(candidate: dict[str, Any]) -> str:
    kind = str(candidate.get("kind") or "drift")
    section = str(candidate.get("affected_section") or "PROJECT_KNOWLEDGE.md")
    action = str(candidate.get("recommended_action") or "review_update")
    why = str(candidate.get("why_it_matters") or "").strip()
    suffix = f": {why}" if why else ""
    return f"- {kind} in {section} ({action}){suffix}"


def _warning_message(summary: dict[str, Any], report: dict[str, Any] | None) -> str:
    out_dir = summary.get("out_dir") or "unknown output directory"
    if report:
        candidates = report.get("candidates") if isinstance(report.get("candidates"), list) else []
        lines = [
            f"project-drift {report.get('verdict', 'unknown')} ({report.get('severity', 'unknown')}): {report.get('summary', 'Review drift report.')}",
            f"Artifact: {out_dir}/drift_report.json",
        ]
        lines.extend(_candidate_line(candidate) for candidate in candidates[:3] if isinstance(candidate, dict))
        if len(candidates) > 3:
            lines.append(f"- plus {len(candidates) - 3} more candidate(s)")
        return "\n".join(lines)

    observations = summary.get("observations")
    return (
        f"project-drift found {observations} candidate evidence observation(s), but no LLM drift verdict was executed. "
        f"Review {out_dir}/prompt_payload.json or set PROJECT_DRIFT_LLM_BASE_URL/SCILLM_BASE_URL for automatic verdicts."
    )


def main() -> None:
    data = _read_hook_input()
    cwd = str(data.get("cwd") or os.getcwd())
    root = _git_root(cwd)
    skill_dir = Path(os.environ.get("PROJECT_DRIFT_SKILL_DIR", str(DEFAULT_SKILL_DIR))).resolve()
    run_sh = skill_dir / "run.sh"
    if not run_sh.exists():
        return

    out_dir = Path(os.environ.get("PROJECT_DRIFT_OUT_DIR", str(root / ".project-drift" / "latest"))).resolve()
    transcript = _find_transcript(data)
    execute = _execute_enabled()

    args = [
        str(run_sh),
        "scan",
        "--project-root",
        str(root),
        "--out-dir",
        str(out_dir),
        "--since",
        os.environ.get("PROJECT_DRIFT_SINCE", "auto"),
        "--trigger",
        "Codex Stop hook",
        "--execute" if execute else "--no-execute",
    ]
    if transcript:
        args.extend(["--transcript", transcript])

    env = os.environ.copy()
    env.setdefault("PROJECT_DRIFT_CWD", cwd)

    try:
        result = subprocess.run(
            args,
            cwd=root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=float(os.environ.get("PROJECT_DRIFT_HOOK_TIMEOUT", "90")),
            check=False,
        )
    except Exception:
        return

    summary = _load_json(out_dir / "scan_summary.json")
    observations = int(summary.get("observations") or 0)
    if result.returncode != 0:
        if execute:
            message = (
                "project-drift could not execute an LLM verdict. "
                f"Review {out_dir}/prompt_payload.json and hook output before treating project knowledge as current."
            )
            print(json.dumps({"continue": True, "systemMessage": message}))
        return

    report_path = out_dir / "drift_report.json"
    report = _load_json(report_path) if report_path.exists() else None
    verdict = str((report or {}).get("verdict") or summary.get("verdict") or "")

    if report and verdict == "block":
        _stop_response("Project knowledge drift requires review before finalizing.", _warning_message(summary, report))
        return

    if report and verdict in {"warn", "info"}:
        print(json.dumps({"continue": True, "systemMessage": _warning_message(summary, report)}))
        return

    if not execute and observations > 0:
        print(json.dumps({"continue": True, "systemMessage": _warning_message(summary, None)}))


if __name__ == "__main__":
    main()
