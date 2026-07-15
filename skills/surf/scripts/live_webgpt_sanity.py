#!/usr/bin/env python3
"""Opt-in LIVE WebGPT transport gate for /surf.

- Real ./run.sh + Chrome + ChatGPT only.
- Every WebGPT submit/roundtrip uses --no-activate.
- release: one sentinel roundtrip, strict focus_invariant_ok.
- stress: failure-mode probes + e2e matrix + back-to-back roundtrips.
- Live ChatGPT submits are spaced by --roundtrip-interval (default 120s).
- No fixture/json contract checks (pytest only; not verification).
- Refuses foreground reviewer tabs unless --allow-foreground-diagnostic.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

import typer

SURF_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = SURF_ROOT / ".surf_artifacts" / "live-webgpt-sanity"
RUN_SH = SURF_ROOT / "run.sh"

PROFILES: dict[str, frozenset[str]] = {
    "smoke": frozenset(
        {
            "extension_native_fresh",
            "tab_list_available",
            "focus_state_available",
            "reviewer_tab_not_foreground",
            "webgpt_tab_id_background_sanity",
            "webgpt_preflight_passes",
            "local_path_prompt_preflight",
        }
    ),
    "release": frozenset(
        {
            "extension_native_fresh",
            "tab_list_available",
            "focus_state_available",
            "reviewer_tab_not_foreground",
            "webgpt_tab_id_background_sanity",
            "webgpt_preflight_passes",
            "local_path_prompt_preflight",
            "local_path_submit_blocked",
            "preflight_fail_closed",
            "webgpt_roundtrip_reviewer_tab",
            "roundtrip_transport_proof",
        }
    ),
    "failures": frozenset(
        {
            "back_to_back_roundtrip_reviewer",
            "regression_timeout_must_recover",
            "regression_proof_status_focus_drift",
        }
    ),
    "stress": frozenset(
        {
            "extension_native_fresh",
            "tab_list_available",
            "focus_state_available",
            "reviewer_tab_not_foreground",
            "local_path_prompt_preflight",
            "local_path_submit_blocked",
            "preflight_fail_closed",
            "preflight_nonexistent_url_fail_closed",
            "preflight_bare_tab_id_fail_closed",
            "prompt_control_char_sanitize",
            "no_activate_submit_requires_target",
            "webgpt_tab_id_background_sanity",
            "webgpt_preflight_passes",
            "webgpt_roundtrip_reviewer_tab",
            "roundtrip_transport_proof",
            "roundtrip_heartbeat_present",
            "back_to_back_roundtrip_reviewer",
            "webgpt_e2e_sanity_matrix",
        }
    ),
}

EXECUTION_ORDER = {
    "extension_native_fresh": 10,
    "tab_list_available": 20,
    "focus_state_available": 30,
    "reviewer_tab_not_foreground": 40,
    "local_path_prompt_preflight": 50,
    "preflight_fail_closed": 60,
    "local_path_submit_blocked": 70,
    "webgpt_tab_id_background_sanity": 200,
    "webgpt_preflight_passes": 210,
    "preflight_nonexistent_url_fail_closed": 55,
    "preflight_bare_tab_id_fail_closed": 56,
    "prompt_control_char_sanitize": 57,
    "no_activate_submit_requires_target": 58,
    "webgpt_roundtrip_reviewer_tab": 300,
    "roundtrip_transport_proof": 400,
    "roundtrip_heartbeat_present": 410,
    "back_to_back_roundtrip_reviewer": 500,
    "regression_timeout_must_recover": 510,
    "regression_proof_status_focus_drift": 520,
    "webgpt_e2e_sanity_matrix": 600,
}

ROUNDTRIP_CHECKS = frozenset(
    {
        "webgpt_roundtrip_reviewer_tab",
        "back_to_back_roundtrip_reviewer",
        "webgpt_e2e_sanity_matrix",
        "regression_timeout_must_recover",
    }
)


def throttle_roundtrips(last_at: float | None, interval_s: int) -> float:
    """Space live ChatGPT submits to avoid OpenAI rate limits."""
    now = time.monotonic()
    if last_at is not None and interval_s > 0:
        wait_s = interval_s - (now - last_at)
        if wait_s > 0:
            print(f"roundtrip throttle: sleeping {wait_s:.0f}s before next ChatGPT submit", flush=True)
            time.sleep(wait_s)
    return time.monotonic()


app = typer.Typer(add_completion=False, help="Opt-in LIVE WebGPT transport sanity (background-only).")


@dataclass(frozen=True)
class Check:
    name: str
    description: str
    timeout_seconds: int
    needs_reviewer: bool = False
    needs_roundtrip: bool = False


CHECKS: tuple[Check, ...] = (
    Check("extension_native_fresh", "extension.fresh reports status=fresh", 30),
    Check("tab_list_available", "tab.list --json returns a tab array", 30),
    Check("focus_state_available", "focus.state --json exposes activeTabId", 30),
    Check(
        "reviewer_tab_not_foreground",
        "Reviewer ChatGPT tab is not the foreground tab (background-safe)",
        15,
        needs_reviewer=True,
    ),
    Check(
        "webgpt_tab_id_background_sanity",
        "CDP js+click on --tab-id without changing activeTabId",
        120,
        needs_reviewer=True,
    ),
    Check(
        "webgpt_preflight_passes",
        "webgpt.preflight --no-activate passes for reviewer binding",
        90,
        needs_reviewer=True,
    ),
    Check("local_path_prompt_preflight", "Bare local paths fail before browser submit", 15),
    Check(
        "local_path_submit_blocked",
        "webgpt.submit --no-activate blocked on local-path prompt",
        30,
        needs_reviewer=True,
    ),
    Check(
        "preflight_fail_closed",
        "webgpt.preflight rejects fake tab id and wrong expect-url",
        45,
        needs_reviewer=True,
    ),
    Check(
        "webgpt_roundtrip_reviewer_tab",
        "ONE sentinel roundtrip on background reviewer tab (--no-activate)",
        180,
        needs_reviewer=True,
        needs_roundtrip=True,
    ),
    Check(
        "roundtrip_transport_proof",
        "transport summary + recover on roundtrip artifact dir",
        30,
        needs_roundtrip=True,
    ),
    Check(
        "preflight_nonexistent_url_fail_closed",
        "webgpt.preflight --url rejects closed/missing conversation",
        30,
    ),
    Check(
        "preflight_bare_tab_id_fail_closed",
        "bare --tab-id without expect-url fails when multiple ChatGPT tabs open",
        30,
        needs_reviewer=True,
    ),
    Check(
        "prompt_control_char_sanitize",
        "prompt-preflight sanitizes control chars in local paths",
        15,
    ),
    Check(
        "no_activate_submit_requires_target",
        "webgpt.submit --no-activate fails without --tab-id/--url/--create-tab",
        15,
    ),
    Check(
        "roundtrip_heartbeat_present",
        "webgpt_heartbeat.json written during live roundtrip submit",
        15,
        needs_roundtrip=True,
    ),
    Check(
        "regression_timeout_must_recover",
        "short timeout on slow hidden prompt must recover via hidden_recovery or extract retry",
        240,
        needs_reviewer=True,
    ),
    Check(
        "regression_proof_status_focus_drift",
        "focus drift must not map to proof_status=response_proven",
        15,
    ),
    Check(
        "back_to_back_roundtrip_reviewer",
        "two sentinel roundtrips on same background tab (hidden-tab stress)",
        360,
        needs_reviewer=True,
    ),
    Check(
        "webgpt_e2e_sanity_matrix",
        "webgpt.e2e-sanity fail-closed matrix (create-tab + reviewer tab)",
        600,
        needs_reviewer=True,
    ),
)


def reviewer_binding(args: SimpleNamespace) -> dict[str, str]:
    binding: dict[str, str] = {}
    tab_id = (args.tab_id or os.environ.get("SURF_WEBGPT_SANITY_TAB_ID") or "").strip()
    url = (args.url or os.environ.get("SURF_WEBGPT_REVIEWER_URL") or "").strip()
    expect_url = (args.expect_url or os.environ.get("SURF_WEBGPT_EXPECT_URL") or "").strip()
    if tab_id:
        binding["tab_id"] = tab_id
    if url:
        binding["url"] = url
    if expect_url:
        binding["expect_url"] = expect_url
    return binding


def binding_tab_args(binding: dict[str, str]) -> list[str]:
    if binding.get("tab_id"):
        return ["--tab-id", binding["tab_id"]]
    if binding.get("url"):
        return ["--url", binding["url"]]
    return []


def binding_cli_args(binding: dict[str, str]) -> list[str]:
    out: list[str] = []
    if binding.get("tab_id"):
        out.extend(["--tab-id", binding["tab_id"]])
    if binding.get("url"):
        out.extend(["--url", binding["url"]])
    if binding.get("expect_url"):
        out.extend(["--expect-url", binding["expect_url"]])
    return out


def run_subprocess(command: list[str], *, cwd: Path, timeout_seconds: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            env=os.environ.copy(),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        completed = subprocess.CompletedProcess(
            args=command,
            returncode=124,
            stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", "replace"),
            stderr=(exc.stderr or "") if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", "replace"),
        )
        timed_out = True
    return {
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "duration_seconds": round(time.monotonic() - started, 3),
        "timed_out": timed_out,
    }


def parse_json_blob(text: str) -> Any | None:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def get_active_tab_id() -> str:
    run = run_subprocess([str(RUN_SH), "focus.state", "--json"], cwd=SURF_ROOT, timeout_seconds=15)
    payload = parse_json_blob(run["stdout"])
    return str(payload.get("activeTabId") or "") if isinstance(payload, dict) else ""


def count_chatgpt_conversation_tabs() -> int:
    run = run_subprocess([str(RUN_SH), "tab.list"], cwd=SURF_ROOT, timeout_seconds=30)
    count = 0
    for line in run["stdout"].splitlines():
        if "	" not in line:
            continue
        _tid, _title, url = line.split("	", 2)
        if "chatgpt.com/c/" in url:
            count += 1
    return count


def resolve_binding_live(binding: dict[str, str]) -> tuple[dict[str, str], str | None]:
    active = get_active_tab_id()
    if binding.get("tab_id") and not binding.get("url"):
        return binding, None
    run = run_subprocess([str(RUN_SH), "tab.list"], cwd=SURF_ROOT, timeout_seconds=30)
    rows: list[tuple[str, str, str]] = []
    for line in run["stdout"].splitlines():
        if "\t" not in line:
            continue
        parts = line.split("\t", 2)
        if len(parts) >= 3:
            rows.append((parts[0], parts[1], parts[2]))
    target = binding.get("url", "")
    if target:
        target_path = urlparse(target).path.rstrip("/")
        matches = [
            (tid, url)
            for tid, _title, url in rows
            if target in url or (target_path and target_path in urlparse(url).path)
        ]
        if matches:
            tid, url = next(((t, u) for t, u in matches if t != active), matches[0])
            resolved = dict(binding)
            resolved["tab_id"] = tid
            resolved["url"] = url
            resolved.setdefault("expect_url", url)
            note = None if tid != active else "resolved_tab_is_foreground"
            return resolved, note
    for tid, _title, url in rows:
        if "chatgpt.com/c/" in url and tid != active:
            resolved = dict(binding)
            resolved["tab_id"] = tid
            resolved["url"] = url
            resolved.setdefault("expect_url", url)
            return resolved, f"fallback_background_tab={tid}"
    return binding, "no background chatgpt.com/c/ tab found"


def validate_roundtrip(payload: dict[str, Any] | None, *, strict: bool = True) -> tuple[bool, str]:
    """Strict background proof: pass only on clean sentinel + focus_invariant_ok."""
    if not isinstance(payload, dict):
        return False, "missing_payload"
    status = str(payload.get("status") or "")
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    diagnosis = payload.get("diagnosis") if isinstance(payload.get("diagnosis"), dict) else {}
    warnings = payload.get("warnings") if isinstance(payload.get("warnings"), list) else []
    sentinel_ok = bool(diagnosis.get("raw_contains_sentinel") or meta.get("raw_contains_sentinel"))
    tab_ok = bool(meta.get("controlled_tab_id"))
    if status == "pass":
        if meta.get("focus_invariant_ok") is False:
            return False, "false_pass:focus_drift"
        if meta.get("no_activate") is not True:
            return False, "no_activate not recorded"
        if strict and not sentinel_ok:
            return False, "missing_sentinel"
        if strict and not tab_ok:
            return False, "missing_controlled_tab_id"
        return True, f"pass sentinel={sentinel_ok} focus_ok={meta.get('focus_invariant_ok')}"
    if not strict and status == "degraded":
        if "focus_drift_completed" in warnings and meta.get("status") == "recovered_focus_changed":
            return sentinel_ok and tab_ok, "degraded focus_drift_completed"
        if warnings == ["reasoning_selector_unavailable"] and meta.get("status") == "completed":
            return sentinel_ok and tab_ok, "degraded reasoning_only"
    return False, f"status={status} warnings={warnings} meta={meta.get('status')}"


def write_result(path: Path, result: dict[str, Any]) -> None:
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@app.command()
def main(
    output_root: str = typer.Option(str(DEFAULT_OUTPUT_ROOT), "--output-root"),
    allow_live: bool = typer.Option(False, "--allow-live"),
    plan_only: bool = typer.Option(False, "--plan-only"),
    profile: str = typer.Option("release", "--profile", help="smoke | release | stress | failures"),
    timeout_scale: float = typer.Option(1.0, "--timeout-scale"),
    tab_id: str = typer.Option("", "--tab-id"),
    url: str = typer.Option("", "--url"),
    expect_url: str = typer.Option("", "--expect-url"),
    roundtrip_timeout: int = typer.Option(90, "--roundtrip-timeout"),
    roundtrip_interval: int = typer.Option(
        0,
        "--roundtrip-interval",
        help="Seconds between live ChatGPT submits (default: SURF_LIVE_WEBGPT_ROUNDTRIP_INTERVAL or 120)",
    ),
    allow_foreground_diagnostic: bool = typer.Option(False, "--allow-foreground-diagnostic"),
    only: list[str] | None = typer.Option(None, "--only"),
) -> None:
    if profile not in PROFILES:
        raise typer.BadParameter("profile must be one of: smoke, release, stress, failures")
    if not allow_live and not plan_only and os.environ.get("SURF_LIVE_WEBGPT_SANITY") != "1":
        raise SystemExit(
            "Refusing live checks without --allow-live, --plan-only, or SURF_LIVE_WEBGPT_SANITY=1."
        )

    args = SimpleNamespace(
        tab_id=tab_id,
        url=url,
        expect_url=expect_url,
        allow_foreground_diagnostic=allow_foreground_diagnostic,
    )
    binding: dict[str, str] = {}
    binding_note: str | None = None
    if not plan_only:
        binding = reviewer_binding(args)
        binding, binding_note = resolve_binding_live(binding)

    selected = [c for c in CHECKS if c.name in PROFILES[profile]]
    selected.sort(key=lambda c: EXECUTION_ORDER.get(c.name, 999))
    if only:
        filters = tuple(x.lower() for x in only)
        selected = [c for c in selected if any(f in c.name.lower() for f in filters)]

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(output_root).resolve() / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    checks_dir = run_dir / "checks"
    checks_dir.mkdir(exist_ok=True)

    roundtrip_interval_effective = roundtrip_interval
    if roundtrip_interval_effective <= 0:
        roundtrip_interval_effective = int(os.environ.get("SURF_LIVE_WEBGPT_ROUNDTRIP_INTERVAL", "120"))
    last_roundtrip_at: float | None = None

    reviewer_dir = run_dir / "roundtrip-reviewer-tab"
    tab_bg_dir = run_dir / "tab-id-background"
    roundtrip_dir: Path | None = None
    results: list[dict[str, Any]] = []

    for check in selected:
        artifact = checks_dir / f"{check.name}.json"
        timeout_s = max(5, int(check.timeout_seconds * timeout_scale))

        if plan_only:
            results.append({"name": check.name, "status": "planned", "execution_status": "planned"})
            continue

        if check.needs_reviewer and not (binding.get("tab_id") or binding.get("url")):
            results.append({
                "name": check.name,
                "status": "skipped",
                "detail": "No background reviewer tab; pass --url to an open chatgpt.com/c/ tab",
            })
            continue

        if check.name == "extension_native_fresh":
            run = run_subprocess([str(RUN_SH), "extension.fresh", "--json"], cwd=SURF_ROOT, timeout_seconds=timeout_s)
            payload = parse_json_blob(run["stdout"])
            ok = run["exit_code"] == 0 and isinstance(payload, dict) and payload.get("status") == "fresh"
            detail = f"status={(payload or {}).get('status')} exit={run['exit_code']}"
        elif check.name == "tab_list_available":
            run = run_subprocess([str(RUN_SH), "tab.list", "--json"], cwd=SURF_ROOT, timeout_seconds=timeout_s)
            ok = run["exit_code"] == 0 and isinstance(parse_json_blob(run["stdout"]), list)
            detail = f"exit={run['exit_code']}"
        elif check.name == "focus_state_available":
            run = run_subprocess([str(RUN_SH), "focus.state", "--json"], cwd=SURF_ROOT, timeout_seconds=timeout_s)
            payload = parse_json_blob(run["stdout"])
            ok = run["exit_code"] == 0 and isinstance(payload, dict) and bool(payload.get("activeTabId"))
            detail = f"active={payload.get('activeTabId') if isinstance(payload, dict) else None}"
        elif check.name == "reviewer_tab_not_foreground":
            active = get_active_tab_id()
            tab = str(binding.get("tab_id") or "")
            if args.allow_foreground_diagnostic:
                ok, detail = True, "allow-foreground-diagnostic"
            elif not tab:
                ok, detail = False, "no reviewer tab resolved"
            elif tab == active:
                ok, detail = False, f"reviewer tab {tab} is foreground; use a background reviewer tab"
            else:
                ok, detail = True, f"reviewer={tab} active={active or 'unknown'}"
        elif check.name == "webgpt_tab_id_background_sanity":
            cmd = [str(RUN_SH), "webgpt.tab-id-background-sanity", "--json", "--output-dir", str(tab_bg_dir)]
            cmd.extend(binding_tab_args(binding))
            run = run_subprocess(cmd, cwd=SURF_ROOT, timeout_seconds=timeout_s)
            ok = run["exit_code"] == 0
            detail = f"exit={run['exit_code']}"
        elif check.name == "webgpt_preflight_passes":
            cmd = [str(RUN_SH), "webgpt.preflight", "--json", "--no-activate", *binding_cli_args(binding)]
            run = run_subprocess(cmd, cwd=SURF_ROOT, timeout_seconds=timeout_s)
            payload = parse_json_blob(run["stdout"])
            ok = run["exit_code"] == 0 and isinstance(payload, dict) and payload.get("status") == "pass"
            detail = f"status={(payload or {}).get('status')} exit={run['exit_code']}"
        elif check.name == "local_path_prompt_preflight":
            bad = run_dir / "local-path-prompt.md"
            bad.write_text("See /mnt/storage12tb/readme.md\n", encoding="utf-8")
            run = run_subprocess([str(RUN_SH), "webgpt.prompt-preflight", "--input", str(bad), "--json"], cwd=SURF_ROOT, timeout_seconds=timeout_s)
            payload = parse_json_blob(run["stdout"])
            ok = run["exit_code"] != 0 and isinstance(payload, dict) and payload.get("status") == "fail"
            detail = f"exit={run['exit_code']}"
        elif check.name == "local_path_submit_blocked":
            bad = run_dir / "submit-local-path.md"
            bad.write_text("Review /home/graham/workspace/experiments/agent-skills/skills/surf/README.md\n", encoding="utf-8")
            out = run_dir / "blocked-submit.md"
            cmd = [
                str(RUN_SH), "webgpt.submit", "--no-activate", "--timeout", "10",
                "--input", str(bad), "--output", str(out), *binding_cli_args(binding),
            ]
            run = run_subprocess(cmd, cwd=SURF_ROOT, timeout_seconds=timeout_s)
            meta_path = Path(str(out) + ".meta.json")
            meta = parse_json_blob(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else None
            ok = run["exit_code"] == 7 and isinstance(meta, dict) and meta.get("failure") == "prompt_path_preflight_failed"
            detail = f"exit={run['exit_code']} failure={(meta or {}).get('failure') if isinstance(meta, dict) else None}"
        elif check.name == "preflight_fail_closed":
            run1 = run_subprocess([str(RUN_SH), "webgpt.preflight", "--tab-id", "999999999", "--no-activate", "--json"], cwd=SURF_ROOT, timeout_seconds=timeout_s)
            cmd2 = [str(RUN_SH), "webgpt.preflight", "--json", "--no-activate", "--expect-url", "https://chatgpt.com/c/00000000-0000-0000-0000-000000000000"]
            if binding.get("tab_id"):
                cmd2.extend(["--tab-id", binding["tab_id"]])
            run2 = run_subprocess(cmd2, cwd=SURF_ROOT, timeout_seconds=timeout_s)
            p1 = parse_json_blob(run1["stdout"])
            p2 = parse_json_blob(run2["stdout"])
            ok = (
                run1["exit_code"] != 0 and isinstance(p1, dict) and p1.get("status") == "fail"
                and run2["exit_code"] != 0 and isinstance(p2, dict) and p2.get("status") == "fail"
            )
            detail = f"fake_tab={run1['exit_code']} wrong_url={run2['exit_code']}"
        elif check.name == "webgpt_roundtrip_reviewer_tab":
            last_roundtrip_at = throttle_roundtrips(last_roundtrip_at, roundtrip_interval_effective)
            if not args.allow_foreground_diagnostic and binding.get("tab_id") == get_active_tab_id():
                ok, detail = False, "refusing roundtrip on foreground reviewer tab"
                run = {"exit_code": None, "stderr": detail}
            else:
                cmd = [
                    str(RUN_SH), "webgpt.roundtrip-preflight", "--no-activate", "--json",
                    "--timeout", str(roundtrip_timeout), "--output-dir", str(reviewer_dir),
                    *binding_cli_args(binding),
                ]
                run = run_subprocess(cmd, cwd=SURF_ROOT, timeout_seconds=max(timeout_s, roundtrip_timeout + 30))
                ok, detail = validate_roundtrip(parse_json_blob(run["stdout"]))
                detail = f"{detail} exit={run['exit_code']}"
                if ok and reviewer_dir.exists():
                    roundtrip_dir = reviewer_dir
                last_roundtrip_at = time.monotonic()
        elif check.name == "roundtrip_transport_proof":
            if roundtrip_dir is None:
                ok, detail = False, "no successful roundtrip artifact dir"
            else:
                summary_path = roundtrip_dir / "webgpt_transport_summary.json"
                if not summary_path.exists():
                    run = run_subprocess([
                        "python3", str(SURF_ROOT / "scripts/lib/webgpt_transport.py"), "write-summary",
                        "--artifact-dir", str(roundtrip_dir),
                    ], cwd=SURF_ROOT, timeout_seconds=20)
                    ok = run["exit_code"] == 0 and summary_path.exists()
                else:
                    ok = True
                recover = run_subprocess([str(RUN_SH), "webgpt.recover", "--artifact-dir", str(roundtrip_dir)], cwd=SURF_ROOT, timeout_seconds=30)
                payload = parse_json_blob(recover["stdout"])
                ok = ok and recover["exit_code"] == 0 and isinstance(payload, dict) and bool(payload.get("next_command"))
                detail = f"summary={summary_path.exists()} recover_state={(payload or {}).get('state') if isinstance(payload, dict) else None}"
        elif check.name == "preflight_nonexistent_url_fail_closed":
            ghost = "https://chatgpt.com/c/00000000-0000-0000-0000-000000000000"
            run = run_subprocess(
                [str(RUN_SH), "webgpt.preflight", "--url", ghost, "--no-activate", "--json"],
                cwd=SURF_ROOT,
                timeout_seconds=timeout_s,
            )
            payload = parse_json_blob(run["stdout"])
            ok = run["exit_code"] != 0 and isinstance(payload, dict) and payload.get("status") == "fail"
            detail = f"exit={run['exit_code']} failures={(payload or {}).get('failures')}"
        elif check.name == "preflight_bare_tab_id_fail_closed":
            chatgpt_tabs = count_chatgpt_conversation_tabs()
            if chatgpt_tabs < 2:
                result = {
                    "name": check.name,
                    "description": check.description,
                    "profile": profile,
                    "status": "skipped",
                    "execution_status": "skipped",
                    "detail": f"need>=2 chatgpt tabs; have={chatgpt_tabs}",
                    "artifact": str(artifact),
                    "live_only": True,
                    "mocked": False,
                    "expect_fail_closed": True,
                }
                write_result(artifact, result)
                results.append(result)
                continue
            elif not binding.get("tab_id"):
                ok, detail = False, "no reviewer tab_id for bare-tab-id probe"
            else:
                run = run_subprocess(
                    [
                        str(RUN_SH), "webgpt.preflight", "--json", "--no-activate",
                        "--tab-id", binding["tab_id"],
                    ],
                    cwd=SURF_ROOT,
                    timeout_seconds=timeout_s,
                )
                payload = parse_json_blob(run["stdout"])
                ok = run["exit_code"] != 0 and isinstance(payload, dict) and payload.get("status") == "fail"
                detail = f"chatgpt_tabs={chatgpt_tabs} exit={run['exit_code']} failures={(payload or {}).get('failures')}"
        elif check.name == "prompt_control_char_sanitize":
            bad = run_dir / "control-char-path.md"
            bad.write_bytes(b"Review \x00\x07/mnt/evil\x1fpath.md\n")
            run = run_subprocess(
                [str(RUN_SH), "webgpt.prompt-preflight", "--input", str(bad), "--json"],
                cwd=SURF_ROOT,
                timeout_seconds=timeout_s,
            )
            payload = parse_json_blob(run["stdout"])
            paths = payload.get("local_paths") if isinstance(payload, dict) else []
            sanitized = paths[0].get("path", "") if isinstance(paths, list) and paths else ""
            ok = (
                run["exit_code"] != 0
                and isinstance(payload, dict)
                and payload.get("status") == "fail"
                and sanitized
                and all(ord(ch) >= 32 for ch in sanitized)
                and "\x00" not in repr(sanitized)
            )
            detail = f"sanitized={sanitized!r} browser_submit_allowed={payload.get('browser_submit_allowed') if isinstance(payload, dict) else None}"
        elif check.name == "no_activate_submit_requires_target":
            req = run_dir / "no-target-request.md"
            req.write_text("pong\n", encoding="utf-8")
            out = run_dir / "no-target-response.md"
            run = run_subprocess(
                [
                    str(RUN_SH), "webgpt.submit", "--no-activate", "--timeout", "5",
                    "--input", str(req), "--output", str(out),
                ],
                cwd=SURF_ROOT,
                timeout_seconds=timeout_s,
            )
            ok = run["exit_code"] != 0
            detail = f"exit={run['exit_code']} stderr_tail={(run.get('stderr') or '')[-200:]}"
        elif check.name == "roundtrip_heartbeat_present":
            if roundtrip_dir is None:
                ok, detail = False, "no roundtrip artifact dir"
            else:
                heartbeat = roundtrip_dir / "webgpt_heartbeat.json"
                payload = parse_json_blob(heartbeat.read_text(encoding="utf-8")) if heartbeat.exists() else None
                ok = (
                    heartbeat.exists()
                    and isinstance(payload, dict)
                    and payload.get("schema") == "surf.webgpt_heartbeat.v1"
                    and bool(payload.get("phase"))
                    and bool(payload.get("updated_at") or payload.get("submitted_at"))
                )
                detail = f"heartbeat={heartbeat.exists()} phase={(payload or {}).get('phase') if isinstance(payload, dict) else None}"
        elif check.name == "back_to_back_roundtrip_reviewer":
            last_roundtrip_at = throttle_roundtrips(last_roundtrip_at, roundtrip_interval_effective)
            bb_root = run_dir / "roundtrip-back-to-back"
            runs_detail: list[str] = []
            ok = True
            for idx in (1, 2):
                bb_dir = bb_root / f"run-{idx}"
                cmd = [
                    str(RUN_SH), "webgpt.roundtrip-preflight", "--no-activate", "--json",
                    "--timeout", str(roundtrip_timeout), "--output-dir", str(bb_dir),
                    *binding_cli_args(binding),
                ]
                run = run_subprocess(cmd, cwd=SURF_ROOT, timeout_seconds=max(timeout_s, roundtrip_timeout + 30))
                run_ok, run_detail = validate_roundtrip(parse_json_blob(run["stdout"]))
                runs_detail.append(f"run{idx}={run_detail}")
                ok = ok and run_ok
                last_roundtrip_at = time.monotonic()
                if idx == 1:
                    last_roundtrip_at = throttle_roundtrips(last_roundtrip_at, roundtrip_interval_effective)
                    active = get_active_tab_id()
                    if binding.get("tab_id") and active == binding.get("tab_id"):
                        ok = False
                        runs_detail.append("run2_blocked=reviewer_became_foreground")
                        break
            detail = " ".join(runs_detail)
        elif check.name == "webgpt_e2e_sanity_matrix":
            last_roundtrip_at = throttle_roundtrips(last_roundtrip_at, roundtrip_interval_effective)
            e2e_dir = run_dir / "e2e-sanity"
            cmd = [
                str(RUN_SH), "webgpt.e2e-sanity", "--json", "--no-activate",
                "--timeout", str(roundtrip_timeout), "--output-dir", str(e2e_dir),
                *binding_cli_args(binding),
            ]
            run = run_subprocess(cmd, cwd=SURF_ROOT, timeout_seconds=max(timeout_s, roundtrip_timeout * 3 + 180))
            payload = parse_json_blob(run["stdout"])
            ok = run["exit_code"] == 0 and isinstance(payload, dict) and payload.get("status") == "pass"
            detail = (
                f"exit={run['exit_code']} status={(payload or {}).get('status')} "
                f"failure={(payload or {}).get('failure_code')}"
            )
            last_roundtrip_at = time.monotonic()
        elif check.name == "regression_timeout_must_recover":
            last_roundtrip_at = throttle_roundtrips(last_roundtrip_at, roundtrip_interval_effective)
            reg_dir = run_dir / "regression-timeout-recover"
            reg_dir.mkdir(parents=True, exist_ok=True)
            req = reg_dir / "01_slow_request.md"
            req.write_text(
                "Write a detailed 400-word essay about browser tab lifecycle throttling. "
                "End your answer with the completion marker from the prompt.\n",
                encoding="utf-8",
            )
            out = reg_dir / "02_response.md"
            env = os.environ.copy()
            env.setdefault("SURF_WEBGPT_HIDDEN_RECOVERY_POLLS", "40")
            env.setdefault("SURF_WEBGPT_HIDDEN_RECOVERY_IDLE_MS", "15000")
            env.setdefault("SURF_WEBGPT_EXTRACT_FALLBACK_BUDGET", "120")
            cmd = [
                str(RUN_SH), "webgpt.submit", "--no-activate", "--timeout", "12",
                "--stable-polls", "2", "--reasoning", "Pro",
                "--input", str(req), "--output", str(out),
                "--raw-output", str(reg_dir / "02_response.raw.md"),
                "--meta-output", str(reg_dir / "02_response.meta.json"),
                "--submitted-output", str(reg_dir / "02_response.submitted.md"),
                *binding_cli_args(binding),
            ]
            started = time.monotonic()
            try:
                completed = subprocess.run(
                    cmd, cwd=str(SURF_ROOT), env=env, text=True,
                    capture_output=True, timeout=max(timeout_s, 180), check=False,
                )
                run = {
                    "exit_code": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                    "timed_out": False,
                    "duration_seconds": round(time.monotonic() - started, 3),
                }
            except subprocess.TimeoutExpired as exc:
                run = {
                    "exit_code": 124,
                    "stdout": exc.stdout or "",
                    "stderr": exc.stderr or "",
                    "timed_out": True,
                    "duration_seconds": round(time.monotonic() - started, 3),
                }
            meta_path = reg_dir / "02_response.meta.json"
            meta = parse_json_blob(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
            raw_path = reg_dir / "02_response.raw.md"
            raw_text = raw_path.read_text(encoding="utf-8") if raw_path.exists() else ""
            sentinel = str((meta or {}).get("sentinel") or "")
            has_sentinel = bool(sentinel and sentinel in raw_text)
            recovered = bool(
                (meta or {}).get("hidden_recovery_used") is True
                or (meta or {}).get("extract_fallback_used") is True
                or (meta or {}).get("status") == "completed"
            )
            ok = has_sentinel and recovered
            detail = (
                f"status={(meta or {}).get('status')} failure={(meta or {}).get('failure')} "
                f"hidden_recovery={(meta or {}).get('hidden_recovery_used')} "
                f"extract={(meta or {}).get('extract_fallback_used')} "
                f"hidden_polls={(meta or {}).get('background_hidden_polls')} "
                f"exit={run['exit_code']}"
            )
            last_roundtrip_at = time.monotonic()
        elif check.name == "regression_proof_status_focus_drift":
            run = run_subprocess(
                [str(SURF_ROOT / ".venv/bin/python"), "-m", "pytest",
                 "tests/test_webgpt_submit_attach_preflight.py", "-k", "recovers_sentinel_output_when_focus_changed", "-q"],
                cwd=SURF_ROOT,
                timeout_seconds=timeout_s,
            )
            ok = run["exit_code"] == 0
            detail = f"pytest exit={run['exit_code']} tail={(run.get('stderr') or run.get('stdout') or '')[-200:]}"
        else:
            ok, detail = False, "unknown check"

        expect_fail = check.name in {
            "preflight_fail_closed",
            "local_path_prompt_preflight",
            "local_path_submit_blocked",
            "preflight_nonexistent_url_fail_closed",
            "preflight_bare_tab_id_fail_closed",
            "prompt_control_char_sanitize",
            "no_activate_submit_requires_target",
        }
        result = {
            "name": check.name,
            "description": check.description,
            "profile": profile,
            "status": "pass" if ok else "fail",
            "execution_status": "executed",
            "detail": detail,
            "artifact": str(artifact),
            "live_only": True,
            "mocked": False,
            "expect_fail_closed": expect_fail,
        }
        write_result(artifact, result)
        results.append(result)

    passed = sum(1 for r in results if r.get("status") == "pass")
    failed = sum(1 for r in results if r.get("status") == "fail")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    summary = {
        "schema": "surf.live_webgpt_sanity.v1",
        "run_dir": str(run_dir),
        "profile": profile,
        "reviewer_binding": binding or None,
        "reviewer_binding_note": binding_note,
        "checks": results,
        "totals": {
            "selected": len(results),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "live_reliability_rate": round(passed / max(1, passed + failed), 3),
        },
        "policy": {
            "all_webgpt_commands_use_no_activate": True,
            "max_chatgpt_roundtrips_per_run": (1 if profile == "release" else "many"),
            "roundtrip_interval_seconds": roundtrip_interval_effective,
            "fixture_contract_tests_included": False,
            "verified_means_live_report": True,
        },
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run_dir": str(run_dir), **summary["totals"]}, indent=2))
    raise typer.Exit(1 if failed else 0)


if __name__ == "__main__":
    app()
