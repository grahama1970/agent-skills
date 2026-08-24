"""CLI entrypoint for the read-only Stage 0 opportunity monitor."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

import typer
from dotenv import load_dotenv
from loguru import logger

from . import __version__
from .buzz_review import (
    BuzzAgentReviewConfig,
    BuzzSummaryConfig,
    create_buzz_agent_review,
    create_buzz_summary,
)
from .contracts import CONTRACT_VERSION, IMMUTABLE_GOAL, STAGE, ContractError
from .decisions import append_decision
from .decisions import replay as replay_decisions
from .discovery import _merge_linkedin_top_candidate, sweep as sweep_sources
from .github_repo_intelligence import (
    DEFAULT_OWNER_NAMES as DEFAULT_GITHUB_INTELLIGENCE_OWNER_NAMES,
)
from .github_repo_intelligence import (
    DEFAULT_OWNERS as DEFAULT_GITHUB_INTELLIGENCE_OWNERS,
)
from .github_repo_intelligence import (
    DEFAULT_QUERIES as DEFAULT_GITHUB_INTELLIGENCE_QUERIES,
)
from .github_repo_intelligence import (
    DEFAULT_REPOS as DEFAULT_GITHUB_INTELLIGENCE_REPOS,
)
from .github_repo_intelligence import (
    GitHubRepoIntelligenceConfig,
    collect_github_repo_intelligence,
    write_degraded_github_repo_intelligence,
)
from .pipeline import (
    build_receipt_consistency,
    build_zero_effect_replay_receipt,
    prepare_run_output,
    run_stage0,
    status_for_run,
)
from .ranking import rank as rank_candidates
from .report import load_manifest, render_report
from .report_acceptance import validate_report_acceptance
from .semantic_addenda import install_semantic_addendum
from .service import serve as serve_report
from .tailoring import tailor as tailor_resume
from .tailoring import tailor_candidate
from .tau_semantic_prepare import prepare_tau_semantic_inputs
from .tau_semantic_provider import run_provider_semantic_eval
from .util import read_json, sha256_bytes, sha256_json, utc_now, write_json
from .verification import run_verification

load_dotenv(override=False)

app = typer.Typer(
    name="monitor-opportunities",
    help="Zero-network Stage 0 status, report, and verification kernel.",
    no_args_is_help=True,
)

IMPLEMENTED = [
    "status",
    "report",
    "verify",
    "sweep",
    "rank",
    "tailor",
    "decision",
    "replay",
    "run",
    "resume",
    "schedule",
    "serve",
    "buzz-review",
    "buzz-summary",
    "ats-inspect",
    "ats-prefill",
    "base-resume",
    "tailor-artifact",
    "memory-sync",
    "github-intelligence",
    "nightly",
    "apply",
    "tau-semantic-prepare",
    "tau-semantic-provider-eval",
    "tau-semantic-install",
    "report-acceptance",
    "scheduler-exec-check",
]
NOT_IMPLEMENTED: list[str] = []


def _configure_logging() -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO", colorize=False)


def _canonical_repo_root() -> Path:
    repo_root = Path(__file__).resolve().parents[4]
    parts = repo_root.parts
    if ".worktrees" in parts:
        marker = parts.index(".worktrees")
        return Path(*parts[:marker])
    return repo_root


def _split_env_list(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    normalized = value.replace("\n", ";").replace(",", ";")
    return tuple(item.strip() for item in normalized.split(";") if item.strip())


def _parse_owner_names(values: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for value in values:
        if "=" not in value:
            continue
        handle, name = value.split("=", 1)
        handle = handle.strip().lstrip("@")
        name = name.strip()
        if handle and name:
            pairs.append((handle, name))
    return tuple(pairs)


def _fail(exc: ContractError) -> NoReturn:
    typer.echo(json.dumps({"status": "ERROR", **exc.as_dict()}, sort_keys=True), err=True)
    raise typer.Exit(code=2)


def _resolve_cli_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    return path.expanduser().resolve()


def _nightly_subprocess_env(skill_dir: Path, steps: dict[str, object]) -> dict[str, str]:
    env = os.environ.copy()
    configured = env.get("MONITOR_CLAIM_SNAPSHOT_PATH")
    default_claim_snapshot = skill_dir / "local" / "nightly" / "authority" / "claim-snapshot.json"
    if configured:
        path = Path(configured).expanduser().resolve()
        steps["claim_snapshot_authority"] = {
            "source": "env",
            "path": str(path),
            "exists": path.is_file(),
        }
    elif default_claim_snapshot.is_file():
        path = default_claim_snapshot.resolve()
        env["MONITOR_CLAIM_SNAPSHOT_PATH"] = str(path)
        steps["claim_snapshot_authority"] = {
            "source": "default_authority",
            "path": str(path),
            "exists": True,
        }
    else:
        steps["claim_snapshot_authority"] = {
            "source": "missing",
            "path": str(default_claim_snapshot),
            "exists": False,
        }
    return env


def _scheduler_effect_policy(*, diagnostic: bool) -> dict[str, str]:
    return {
        "tracker": "SKIPPED",
        "prior_application_history": "ENABLED",
        "ats_selector_memory_write": "SKIPPED",
        "tau_semantic_provider": "LOCAL_PREP_ONLY" if diagnostic else "ENABLED",
        "gmail_send": "FORBIDDEN",
        "linkedin_action": "FORBIDDEN",
        "meetup_rsvp": "FORBIDDEN",
        "ats_submit": "FORBIDDEN",
        "buzz_summary": "SKIPPED" if diagnostic else "ENABLED",
    }


def _scheduler_command_from_intent(intent: dict[str, Any]) -> str:
    command_parts = ["source ~/.zshrc >/dev/null 2>&1"]
    for name, value in intent["environment"].items():
        command_parts.append(f"export {name}={shlex.quote(str(value))}")
    command_parts.append(
        "exec "
        + " ".join(
            [
                shlex.quote(str(intent["entrypoint"])),
                *[shlex.quote(str(arg)) for arg in intent["nightly_args"]],
            ]
        )
    )
    return "zsh -lc " + shlex.quote("; ".join(command_parts))


def _scheduler_equivalence_receipt(
    *,
    cron: str,
    command: str,
    repo_root: Path,
    intent: dict[str, Any],
    readback: dict[str, Any],
) -> dict[str, Any]:
    registered_command = str(readback.get("command") or "")
    expected_revision = str(intent.get("expected_revision") or "")
    effect_policy = intent.get("effect_policy") or {}
    environment = intent.get("environment") or {}
    forbidden_effects = {
        "gmail_send": "FORBIDDEN",
        "linkedin_action": "FORBIDDEN",
        "meetup_rsvp": "FORBIDDEN",
        "ats_submit": "FORBIDDEN",
    }
    checks = {
        "job_readback_present": bool(readback),
        "cron_matches": readback.get("cron") == cron,
        "command_matches": registered_command == command,
        "workdir_matches": readback.get("workdir") == str(repo_root),
        "enabled": readback.get("enabled", True) is True,
        "entrypoint_matches_monitor_run_sh": Path(str(intent["entrypoint"])).name == "run.sh",
        "requires_clean": "--require-clean" in intent["nightly_args"],
        "registered_requires_clean": "--require-clean" in registered_command,
        "expected_revision_pinned": "--expected-revision" in intent["nightly_args"]
        and bool(intent.get("expected_revision")),
        "registered_expected_revision_pinned": bool(expected_revision)
        and expected_revision in registered_command,
        "external_effects_false": intent.get("external_effects") is False,
        "tracker_disabled_in_environment": environment.get("MONITOR_TRACKER_ENABLED") == "0",
        "ats_memory_disabled_in_environment": environment.get("MONITOR_ATS_MEMORY_ENABLED")
        == "0",
        "relationship_signals_enabled": environment.get("MONITOR_RELATIONSHIP_SIGNALS_ENABLED")
        == "1",
        "forbidden_effect_policy": all(
            effect_policy.get(name) == expected for name, expected in forbidden_effects.items()
        ),
        "promoted_or_diagnostic_mode_explicit": (
            "--promoted-stage0" in intent["nightly_args"]
            or "--diagnostic" in intent["nightly_args"]
        ),
    }
    mode = str(intent["mode"])
    if mode == "PROMOTED_STAGE_0":
        checks["promoted_stage0_flag_matches"] = "--promoted-stage0" in intent["nightly_args"]
        checks["registered_promoted_stage0_flag_matches"] = (
            "--promoted-stage0" in registered_command
        )
        checks["tau_semantic_provider_flag_matches"] = (
            "--tau-semantic-provider" in intent["nightly_args"]
        )
        checks["registered_tau_semantic_provider_flag_matches"] = (
            "--tau-semantic-provider" in registered_command
        )
        checks["tau_semantic_handler_matches"] = (
            "--tau-semantic-handler" in intent["nightly_args"]
            and "gpt-5.5-high" in intent["nightly_args"]
        )
        checks["registered_tau_semantic_handler_matches"] = (
            "--tau-semantic-handler" in registered_command
            and "gpt-5.5-high" in registered_command
        )
        checks["diagnostic_flag_absent"] = "--diagnostic" not in intent["nightly_args"]
        checks["registered_diagnostic_flag_absent"] = "--diagnostic" not in registered_command
        checks["buzz_enabled_for_promoted"] = (
            intent["effect_policy"].get("buzz_summary") == "ENABLED"
        )
        checks["tau_semantic_provider_enabled_for_promoted"] = (
            intent["effect_policy"].get("tau_semantic_provider") == "ENABLED"
        )
    if mode == "DIAGNOSTIC":
        checks["diagnostic_flag_matches"] = "--diagnostic" in intent["nightly_args"]
        checks["registered_diagnostic_flag_matches"] = "--diagnostic" in registered_command
        checks["promoted_stage0_flag_absent"] = "--promoted-stage0" not in intent["nightly_args"]
        checks["registered_promoted_stage0_flag_absent"] = (
            "--promoted-stage0" not in registered_command
        )
        checks["buzz_skipped_for_diagnostic"] = (
            intent["effect_policy"].get("buzz_summary") == "SKIPPED"
        )
    status = "PASS" if all(checks.values()) else "FAIL"
    return {
        "schema": "monitor_opportunities.scheduler_equivalence_receipt.v1",
        "status": status,
        "mode": mode,
        "cron": cron,
        "name": "monitor-opportunities-nightly",
        "external_effects": False,
        "checks": checks,
        "intended_command_digest": sha256_json(command),
        "registered_command_digest": sha256_json(readback.get("command")),
        "intent_digest": sha256_json(intent),
        "intent": intent,
        "readback": readback,
        "mocked": False,
        "live": False,
    }


def _scheduler_data_dir() -> Path:
    return Path(os.environ.get("SCHEDULER_DATA_DIR", str(Path.home() / ".pi" / "scheduler")))


def _count_token(command: str, token: str) -> int:
    return command.count(token)


def _hash_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return sha256_bytes(path.read_bytes())


def _json_hash_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return sha256_json(read_json(path))


def _receipt_status(path: Path) -> str:
    if not path.is_file():
        return "MISSING"
    try:
        return str(read_json(path).get("status") or "MISSING")
    except (OSError, json.JSONDecodeError, AttributeError):
        return "UNREADABLE"


def _scheduler_execution_equivalence_preflight(
    *,
    schedule_receipt: dict[str, Any],
    schedule_receipt_path: Path,
    require_promoted_stage0: bool,
) -> tuple[dict[str, bool], dict[str, Any]]:
    readback = schedule_receipt.get("readback") or {}
    intent = schedule_receipt.get("scheduler_intent") or {}
    equivalence = schedule_receipt.get("scheduler_equivalence") or {}
    command = str(readback.get("command") or "")
    receipt_command = str(schedule_receipt.get("command") or "")
    workdir = Path(str(readback.get("workdir") or ""))
    expected_revision = str(schedule_receipt.get("expected_revision") or "")
    current_revision = ""
    skill_tree_dirty = True
    if workdir.exists():
        try:
            current_revision = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=workdir,
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
            ).stdout.strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            current_revision = ""
        try:
            status = subprocess.run(
                ["git", "status", "--porcelain=v1", "--", "skills/monitor-opportunities"],
                cwd=workdir,
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
            ).stdout
            skill_tree_dirty = bool(status.strip())
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            skill_tree_dirty = True
    effect_policy = schedule_receipt.get("effect_policy") or {}
    environment = intent.get("environment") or {}
    mode = str(schedule_receipt.get("mode") or "")
    checks = {
        "schedule_receipt_present": schedule_receipt_path.is_file(),
        "schedule_receipt_pass": schedule_receipt.get("status") == "PASS",
        "scheduler_equivalence_pass": equivalence.get("status") == "PASS",
        "readback_present": bool(readback),
        "command_byte_for_byte_matches_receipt": bool(command) and command == receipt_command,
        "command_digest_matches_receipt": sha256_bytes(command.encode("utf-8"))
        == sha256_bytes(receipt_command.encode("utf-8")),
        "enabled": readback.get("enabled", True) is True,
        "workdir_present": bool(readback.get("workdir")),
        "workdir_exists": workdir.is_dir(),
        "workdir_matches_receipt": str(readback.get("workdir") or "")
        == str(schedule_receipt.get("workdir") or ""),
        "expected_revision_present": bool(expected_revision),
        "expected_revision_in_command": bool(expected_revision) and expected_revision in command,
        "expected_revision_count_one": command.count(expected_revision) == 1
        if expected_revision
        else False,
        "current_revision_matches_expected": bool(expected_revision)
        and bool(current_revision)
        and (
            current_revision == expected_revision
            or current_revision.startswith(expected_revision)
            or expected_revision.startswith(current_revision)
        ),
        "skill_tree_clean": not skill_tree_dirty,
        "requires_clean_flag_present_once": _count_token(command, "--require-clean") == 1,
        "skip_tracker_flag_present_once": _count_token(command, "--skip-tracker") == 1,
        "skip_ats_memory_flag_present_once": _count_token(command, "--skip-ats-memory") == 1,
        "tracker_disabled_in_environment": environment.get("MONITOR_TRACKER_ENABLED") == "0",
        "ats_memory_disabled_in_environment": environment.get("MONITOR_ATS_MEMORY_ENABLED")
        == "0",
        "relationship_signals_enabled": environment.get("MONITOR_RELATIONSHIP_SIGNALS_ENABLED")
        == "1",
        "external_effects_false": schedule_receipt.get("external_effects") is False,
        "forbidden_effects": all(
            effect_policy.get(name) == "FORBIDDEN"
            for name in ("gmail_send", "linkedin_action", "meetup_rsvp", "ats_submit")
        ),
    }
    if require_promoted_stage0:
        checks.update(
            {
                "mode_promoted_stage0": mode == "PROMOTED_STAGE_0",
                "promoted_flag_present_once": _count_token(command, "--promoted-stage0") == 1,
                "tau_semantic_provider_flag_present_once": _count_token(command, "--tau-semantic-provider")
                == 1,
                "tau_semantic_handler_flag_present_once": _count_token(command, "--tau-semantic-handler")
                == 1,
                "tau_semantic_handler_is_gpt_5_5_high": "gpt-5.5-high" in command,
                "diagnostic_flag_absent": _count_token(command, "--diagnostic") == 0,
                "buzz_not_skipped": _count_token(command, "--skip-buzz") == 0,
                "buzz_summary_enabled": effect_policy.get("buzz_summary") == "ENABLED",
                "tau_semantic_provider_enabled": effect_policy.get("tau_semantic_provider")
                == "ENABLED",
            }
        )
    else:
        checks.update(
            {
                "mode_explicit": mode in {"PROMOTED_STAGE_0", "DIAGNOSTIC"},
                "one_mode_flag_present": (
                    _count_token(command, "--promoted-stage0")
                    + _count_token(command, "--diagnostic")
                )
                == 1,
            }
        )
    preflight = {
        "schedule_receipt": str(schedule_receipt_path),
        "mode": mode,
        "name": str(schedule_receipt.get("name") or ""),
        "cron": str(schedule_receipt.get("cron") or ""),
        "command": command,
        "command_sha256": sha256_bytes(command.encode("utf-8")) if command else None,
        "workdir": str(workdir) if str(workdir) else None,
        "expected_revision": expected_revision,
        "current_revision": current_revision,
        "scheduler_equivalence_status": equivalence.get("status"),
        "skill_tree_dirty": skill_tree_dirty,
    }
    return checks, preflight


def _default_nightly_out(workdir: Path) -> Path:
    return workdir / "skills" / "monitor-opportunities" / "local" / "nightly" / "latest"


NIGHTLY_RUNS_KEPT = 60


def _promote_nightly_latest(run_dir: Path) -> None:
    root = run_dir.parent
    link = root / "latest"
    try:
        if link.is_symlink() or link.exists():
            if link.is_symlink() or link.is_file():
                link.unlink()
            else:
                shutil.rmtree(link)
        link.symlink_to(run_dir.name)
    except OSError as exc:  # a broken link must never stop an already written run
        logger.warning("could not update nightly latest symlink: {}", exc)


def _prune_nightly_runs(root: Path) -> None:
    runs = sorted(
        (d for d in root.glob("run-*") if d.is_dir()),
        key=lambda d: d.name,
        reverse=True,
    )
    for stale in runs[NIGHTLY_RUNS_KEPT:]:
        try:
            shutil.rmtree(stale)
        except OSError:
            pass


def _new_nightly_run_dir(skill_dir: Path, *, promote_latest: bool = True) -> Path:
    """A dated directory per run, with `latest` pointing at the newest.

    Writing every run into a fixed `latest/` destroyed the previous night's
    receipts, so on 2026-08-18 the only recoverable evidence for a week of
    nightlies was a single file: there was no way to answer whether a run that
    exited 0 had actually delivered anything. Each run now gets its own dated
    directory and `latest` becomes a symlink, so readers keep working and
    history survives. Scheduled nightly publication uses ``promote_latest=False``
    and promotes only after the final report acceptance gate writes a receipt.
    """

    root = skill_dir / "local" / "nightly"
    root.mkdir(parents=True, exist_ok=True)
    run_dir = root / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)
    if promote_latest:
        _promote_nightly_latest(run_dir)
    _prune_nightly_runs(root)
    return run_dir


def _scheduler_execution_equivalence_receipt(
    *,
    schedule_receipt_path: Path,
    out_path: Path,
    require_promoted_stage0: bool,
    timeout_seconds: int,
    execute: bool,
) -> dict[str, Any]:
    started_at = None
    finished_at = None
    schedule_receipt = read_json(schedule_receipt_path)
    preflight_checks, preflight = _scheduler_execution_equivalence_preflight(
        schedule_receipt=schedule_receipt,
        schedule_receipt_path=schedule_receipt_path,
        require_promoted_stage0=require_promoted_stage0,
    )
    command = str(preflight.get("command") or "")
    workdir = Path(str(preflight.get("workdir") or ""))
    execution: dict[str, Any] = {"executed": False}
    if all(preflight_checks.values()) and execute:
        started_at = utc_now()
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            execution = {
                "executed": True,
                "exit_code": proc.returncode,
                "stdout_tail": proc.stdout[-4000:],
                "stderr_tail": proc.stderr[-4000:],
            }
        except subprocess.TimeoutExpired as exc:
            execution = {
                "executed": True,
                "exit_code": -1,
                "timeout": True,
                "stdout_tail": str(exc.stdout or "")[-4000:],
                "stderr_tail": str(exc.stderr or "")[-4000:],
            }
        finished_at = utc_now()
    elif not execute:
        execution["skipped_reason"] = "dry_run"
    else:
        execution["skipped_reason"] = "preflight_failed"

    nightly_out = _default_nightly_out(workdir) if workdir else Path()
    stdout_tail = str(execution.get("stdout_tail") or "")
    try:
        if stdout_tail.strip().startswith("{"):
            payload = json.loads(stdout_tail)
            if payload.get("out"):
                nightly_out = Path(str(payload["out"]))
    except (json.JSONDecodeError, TypeError):
        pass
    artifact_paths = {
        "run_attestation": nightly_out / "run-attestation.json",
        "nightly": nightly_out / "nightly-receipt.json",
        "run": nightly_out / "run-receipt.json",
        "report_manifest": nightly_out / "report-manifest.json",
        "tau_semantic_prepare": nightly_out / "tau-semantic" / "tau-semantic-prepare-receipt.json",
        "semantic_addenda_index": nightly_out / "semantic-addenda" / "index.json",
        "receipt_consistency": nightly_out / "receipt-consistency.json",
        "zero_effect_replay": nightly_out / "zero-effect-replay-receipt.json",
        "report_acceptance": nightly_out / "report-acceptance-receipt.json",
    }
    artifacts: dict[str, Any] = {}
    for name, path in artifact_paths.items():
        artifacts[name] = {
            "path": str(path),
            "present": path.is_file(),
            "sha256": _hash_file(path),
            "json_sha256": _json_hash_file(path),
            "status": _receipt_status(path) if path.name.endswith(".json") else None,
        }
    nightly_receipt = (
        read_json(artifact_paths["nightly"]) if artifact_paths["nightly"].is_file() else {}
    )
    acceptance_receipt = (
        read_json(artifact_paths["report_acceptance"])
        if artifact_paths["report_acceptance"].is_file()
        else {}
    )
    replay_receipt = (
        read_json(artifact_paths["zero_effect_replay"])
        if artifact_paths["zero_effect_replay"].is_file()
        else {}
    )
    consistency_receipt = (
        read_json(artifact_paths["receipt_consistency"])
        if artifact_paths["receipt_consistency"].is_file()
        else {}
    )
    attestation = (
        read_json(artifact_paths["run_attestation"])
        if artifact_paths["run_attestation"].is_file()
        else {}
    )
    expected_revision = str(preflight.get("expected_revision") or "")
    revision_full = str((attestation.get("code") or {}).get("git_revision_full") or "")
    report_acceptance_hash = _json_hash_file(artifact_paths["report_acceptance"])
    post_checks = {
        "execution_exit_code_zero": execution.get("exit_code") == 0,
        "nightly_receipt_present": artifact_paths["nightly"].is_file(),
        "nightly_status_pass": nightly_receipt.get("status") == "PASS",
        "nightly_mode_matches_schedule": nightly_receipt.get("mode")
        == schedule_receipt.get("mode"),
        "nightly_live_true": nightly_receipt.get("live") is True,
        "nightly_external_effects_false": nightly_receipt.get("external_effects") is False,
        "run_attestation_present": artifact_paths["run_attestation"].is_file(),
        "attestation_expected_revision_matches": (
            (attestation.get("runtime") or {}).get("expected_revision") == expected_revision
            or (nightly_receipt.get("steps") or {})
            .get("attestation", {})
            .get("expected_revision_matches")
            is True
        ),
        "attestation_revision_matches_scheduler": bool(expected_revision)
        and bool(revision_full)
        and (
            revision_full == expected_revision
            or revision_full.startswith(expected_revision)
            or expected_revision.startswith(revision_full)
        ),
        "attestation_skill_tree_clean": (attestation.get("code") or {}).get("skill_tree_dirty")
        is False,
        "receipt_consistency_present": artifact_paths["receipt_consistency"].is_file(),
        "receipt_consistency_pass": consistency_receipt.get("status") == "PASS",
        "zero_effect_replay_present": artifact_paths["zero_effect_replay"].is_file(),
        "zero_effect_replay_pass": replay_receipt.get("status") == "PASS",
        "zero_effect_replay_external_effects_false": replay_receipt.get("external_effects")
        is False,
        "report_acceptance_present": artifact_paths["report_acceptance"].is_file(),
        "report_acceptance_pass": acceptance_receipt.get("status") == "PASS",
        "report_acceptance_external_effects_false": acceptance_receipt.get("external_effects")
        is False,
        "report_acceptance_hash_bound_in_nightly": bool(report_acceptance_hash)
        and (nightly_receipt.get("artifact_hashes") or {}).get("report_acceptance")
        == report_acceptance_hash,
    }
    if require_promoted_stage0:
        tau_step = (nightly_receipt.get("steps") or {}).get("tau_semantic") or {}
        post_checks.update(
            {
                "tau_semantic_prepare_present": artifact_paths["tau_semantic_prepare"].is_file(),
                "tau_semantic_provider_live": tau_step.get("provider_live") is True,
                "tau_semantic_addenda_installed": int(tau_step.get("installed_addenda") or 0) > 0,
                "semantic_addenda_index_present": artifact_paths["semantic_addenda_index"].is_file(),
            }
        )
    checks = {**preflight_checks, **post_checks}
    receipt = {
        "schema": "monitor_opportunities.scheduler_execution_equivalence_receipt.v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "mocked": False,
        "live": execution.get("executed") is True,
        "external_effects": False,
        "started_at": started_at,
        "finished_at": finished_at,
        "require_promoted_stage0": require_promoted_stage0,
        "timeout_seconds": timeout_seconds,
        "preflight": preflight,
        "execution": execution,
        "nightly_out": str(nightly_out),
        "artifacts": artifacts,
        "checks": checks,
    }
    write_json(out_path, receipt)
    return {**receipt, "receipt": str(out_path)}


def status_payload() -> dict[str, object]:
    return {
        "schema": "monitor_opportunities.status.v1",
        "runtime_version": __version__,
        "contract_version": CONTRACT_VERSION,
        "immutable_goal": IMMUTABLE_GOAL,
        "stage": STAGE,
        "operational_readiness": "NOT_ESTABLISHED",
        "network_access": True,
        "external_effects": False,
        "implemented_commands": IMPLEMENTED,
        "not_implemented_commands": NOT_IMPLEMENTED,
        "capabilities": {
            "local_report": "IMPLEMENTED",
            "verification_receipt": "IMPLEMENTED",
            "live_discovery": "IMPLEMENTED_READ_ONLY",
            "eligibility_and_ranking": "IMPLEMENTED_LOCAL",
            "claim_bound_tailoring": "IMPLEMENTED_LOCAL",
            "decision_ledger": "IMPLEMENTED_LOCAL",
            "loopback_decision_service": "IMPLEMENTED_LOCAL",
            "scheduler_registration": "IMPLEMENTED_LOCAL_READBACK",
            "gmail_mailbox_draft": "BLOCKED_STAGE_0",
            "gmail_send": "PERMANENTLY_FORBIDDEN",
            "linkedin_handoff": "BLOCKED_STAGE_0",
            "linkedin_automation": "PERMANENTLY_FORBIDDEN",
            "ats_inspect": "BLOCKED_STAGE_0",
            "ats_prefill": "BLOCKED_STAGE_0",
            "ats_submit": "BLOCKED_STAGE_0",
            "tau_semantic_input_contract": "IMPLEMENTED_LOCAL",
            "tau_semantic_input_materializer": "IMPLEMENTED_NIGHTLY_LOCAL",
            "tau_semantic_provider_eval": "IMPLEMENTED_PROMOTED_REQUIRED_DIAGNOSTIC_SKIPPED",
            "tau_semantic_report_projection": "IMPLEMENTED_LOCAL",
            "github_repo_intelligence": "IMPLEMENTED_NIGHTLY_READ_ONLY",
        },
        "non_claims": [
            "Stage 0 does not prove long-run nightly reliability.",
            "No Gmail, LinkedIn, ATS, Memory, or scheduler effect is hidden behind report rendering.",
            "The Tau semantic input contract does not prove provider/model semantic quality.",
        ],
    }


@app.command()
def status(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    run: Path | None = typer.Option(None, "--run", exists=True, file_okay=False, readable=True),
) -> None:
    """Report exact Stage 0 implementation and authority state."""
    _configure_logging()
    if run is not None:
        payload = status_for_run(run)
        if json_output:
            typer.echo(json.dumps(payload, indent=2, sort_keys=True))
            return
        typer.echo(f"run: {payload['run_id']}")
        typer.echo(f"state: {payload['state']}")
        typer.echo(f"stale: {str(payload['current_stale']).lower()}")
        typer.echo(f"external effects: {str(payload['external_effects']).lower()}")
        return
    payload = status_payload()
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo(f"monitor-opportunities {payload['runtime_version']}")
    typer.echo(f"stage: {payload['stage']}")
    typer.echo(f"operational readiness: {payload['operational_readiness']}")
    typer.echo("implemented: " + ", ".join(IMPLEMENTED))
    typer.echo("external effects: blocked")


@app.command("tau-semantic-prepare")
def tau_semantic_prepare(
    run: Path = typer.Option(..., "--run", exists=True, file_okay=False, readable=True),
    out: Path = typer.Option(..., "--out", file_okay=False),
    top_n: int = typer.Option(3, "--top-n", min=1, max=8),
) -> None:
    """Materialize validated Tau semantic inputs without provider calls."""
    _configure_logging()
    try:
        receipt = prepare_tau_semantic_inputs(run_dir=run, out_dir=out, top_n=top_n)
    except ContractError as exc:
        _fail(exc)
    except FileNotFoundError as exc:
        _fail(ContractError("TAU_SEMANTIC_PREPARE_FAILED", str(exc)))
    typer.echo(json.dumps(receipt, indent=2, sort_keys=True))
    if receipt["status"] != "PASS":
        raise typer.Exit(code=1)


@app.command("tau-semantic-provider-eval")
def tau_semantic_provider_eval(
    input_path: Path = typer.Option(..., "--input", exists=True, dir_okay=False, readable=True),
    out: Path = typer.Option(..., "--out", file_okay=False),
    handler: str = typer.Option("webgpt", "--handler"),
    execute: bool = typer.Option(False, "--execute", help="Required acknowledgement for a real provider call."),
    timeout_seconds: int = typer.Option(3600, "--timeout-seconds", min=60),
    browser_lock_timeout: int = typer.Option(1800, "--browser-lock-timeout", min=60),
) -> None:
    """Run one provider-live semantic addendum sidecar through /ask Tau DAG."""
    _configure_logging()
    try:
        receipt = run_provider_semantic_eval(
            input_path=input_path,
            out_dir=out,
            handler=handler,
            execute=execute,
            timeout_seconds=timeout_seconds,
            browser_lock_timeout=browser_lock_timeout,
        )
    except (ContractError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        if isinstance(exc, ContractError):
            _fail(exc)
        _fail(ContractError("TAU_SEMANTIC_PROVIDER_FAILED", str(exc)))
    typer.echo(json.dumps(receipt, indent=2, sort_keys=True))
    if receipt["status"] != "PASS":
        raise typer.Exit(code=1)


@app.command("tau-semantic-install")
def tau_semantic_install(
    run: Path = typer.Option(..., "--run", exists=True, file_okay=False, readable=True),
    provider_receipt: Path = typer.Option(..., "--provider-receipt", exists=True, dir_okay=False, readable=True),
) -> None:
    """Install one passed semantic provider sidecar into a run-local projection."""
    _configure_logging()
    try:
        receipt = install_semantic_addendum(run_dir=run, provider_receipt_path=provider_receipt)
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        _fail(ContractError("TAU_SEMANTIC_INSTALL_FAILED", str(exc)))
    typer.echo(json.dumps(receipt, indent=2, sort_keys=True))


@app.command()
def report(
    input_path: Path = typer.Option(..., "--input", exists=True, dir_okay=False, readable=True),
    out: Path = typer.Option(..., "--out", file_okay=False),
) -> None:
    """Validate and render one self-contained Stage 0 report."""
    _configure_logging()
    try:
        manifest = load_manifest(input_path)
        artifacts = render_report(manifest, out)
    except ContractError as exc:
        _fail(exc)
    typer.echo(json.dumps({"status": "PASS", **artifacts}, indent=2, sort_keys=True))


@app.command("report-acceptance")
def report_acceptance(
    run: Path = typer.Option(..., "--run", exists=True, file_okay=False, readable=True),
    allow_missing_zero_effect_replay: bool = typer.Option(
        False,
        "--allow-missing-zero-effect-replay",
        help="Allow run-only receipts that were not produced by nightly.",
    ),
    require_stage_ledger: bool = typer.Option(
        False,
        "--require-stage-ledger",
        help="Require stage-ledger.json to exist and pass.",
    ),
) -> None:
    """Validate report-visible claims, provenance, degradation, and zero effects."""
    _configure_logging()
    receipt = validate_report_acceptance(
        run,
        require_zero_effect_replay=not allow_missing_zero_effect_replay,
        require_stage_ledger=require_stage_ledger,
    )
    typer.echo(json.dumps(receipt, indent=2, sort_keys=True))
    if receipt["status"] != "PASS":
        raise typer.Exit(code=1)


@app.command()
def verify(
    out: Path = typer.Option(..., "--out", file_okay=False),
    fixture: Path | None = typer.Option(
        None,
        "--fixture",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Optional contract fixture; built-in fixture is used when omitted.",
    ),
) -> None:
    """Run positive and adversarial local verification and write a receipt."""
    _configure_logging()
    try:
        receipt = run_verification(out, fixture)
    except ContractError as exc:
        _fail(exc)
    typer.echo(json.dumps(receipt, indent=2, sort_keys=True))
    if receipt["overall"] != "PASS":
        raise typer.Exit(code=1)


@app.command()
def sweep(
    lane: str = typer.Option("A,B,C", "--lane", help="Comma-separated lanes to attempt."),
    out: Path = typer.Option(..., "--out", file_okay=False),
    fixture_dir: Path | None = typer.Option(None, "--fixture-dir", file_okay=False),
    linkedin_evidence: Path | None = typer.Option(
        None,
        "--linkedin-evidence",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local human-supplied LinkedIn top-candidate evidence; no LinkedIn automation.",
    ),
    meetup_evidence: Path | None = typer.Option(
        None,
        "--meetup-evidence",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local read-only Meetup source-intel capture; no RSVP, join, message, or GraphQL action.",
    ),
    github_evidence: Path | None = typer.Option(
        None,
        "--github-evidence",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local read-only GitHub repository intelligence artifact; no GitHub mutation or outreach.",
    ),
    indeed_evidence: Path | None = typer.Option(
        None,
        "--indeed-evidence",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local read-only Indeed browser capture; source-health only, no apply.",
    ),
    hiddenjobs_evidence: Path | None = typer.Option(
        None,
        "--hiddenjobs-evidence",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local read-only HiddenJobs browser capture; source-health only.",
    ),
) -> None:
    """Run read-only source discovery and write local receipts."""
    _configure_logging()
    lanes = {item.strip().upper() for item in lane.split(",") if item.strip()}
    skill_dir = Path(__file__).resolve().parents[2]
    receipt = sweep_sources(
        skill_dir=skill_dir,
        lanes=lanes,
        out_dir=out,
        fixture_dir=fixture_dir,
        linkedin_evidence=linkedin_evidence,
        meetup_evidence=meetup_evidence,
        github_evidence=github_evidence,
        indeed_evidence=indeed_evidence,
        hiddenjobs_evidence=hiddenjobs_evidence,
    )
    typer.echo(json.dumps({"status": "PASS", **receipt}, indent=2, sort_keys=True))


@app.command("github-intelligence")
def github_intelligence(
    out: Path = typer.Option(..., "--out", dir_okay=False, help="JSON artifact consumed by --github-evidence."),
    query: list[str] | None = typer.Option(
        None,
        "--query",
        help="GitHub repository search query. Repeat for multiple bounded searches.",
    ),
    repo: list[str] | None = typer.Option(
        None,
        "--repo",
        help="Exact owner/repo to inspect. Repeat for important known repositories.",
    ),
    owner: list[str] | None = typer.Option(
        None,
        "--owner",
        help="GitHub owner handle whose public repositories should be inspected.",
    ),
    owner_name: list[str] | None = typer.Option(
        None,
        "--owner-name",
        help="Human-confirmed owner mapping as handle=Name. Repeat for multiple contacts.",
    ),
    max_repos: int = typer.Option(8, "--max-repos", min=1, max=25),
    max_contributors: int = typer.Option(12, "--max-contributors", min=0, max=50),
    max_issues: int = typer.Option(8, "--max-issues", min=0, max=50),
    max_pull_requests: int = typer.Option(8, "--max-pull-requests", min=0, max=50),
    max_commits: int = typer.Option(8, "--max-commits", min=0, max=50),
    max_readme_bytes: int = typer.Option(12000, "--max-readme-bytes", min=0, max=50000),
    max_readme_snippets: int = typer.Option(8, "--max-readme-snippets", min=0, max=20),
    timeout_seconds: int = typer.Option(45, "--timeout-seconds", min=10, max=180),
) -> None:
    """Produce bounded read-only GitHub repo/contact intelligence for relationship discovery."""
    _configure_logging()
    queries = tuple(query or ()) or _split_env_list(os.environ.get("MONITOR_GITHUB_INTEL_QUERIES"))
    if not queries:
        queries = DEFAULT_GITHUB_INTELLIGENCE_QUERIES
    repos = tuple(repo or ()) or _split_env_list(os.environ.get("MONITOR_GITHUB_INTEL_REPOS"))
    if not repos:
        repos = DEFAULT_GITHUB_INTELLIGENCE_REPOS
    owners = tuple(owner or ()) or _split_env_list(os.environ.get("MONITOR_GITHUB_INTEL_OWNERS"))
    if not owners:
        owners = DEFAULT_GITHUB_INTELLIGENCE_OWNERS
    owner_names = _parse_owner_names(tuple(owner_name or ())) or _parse_owner_names(
        _split_env_list(os.environ.get("MONITOR_GITHUB_INTEL_OWNER_NAMES"))
    )
    if not owner_names:
        owner_names = DEFAULT_GITHUB_INTELLIGENCE_OWNER_NAMES
    try:
        receipt = collect_github_repo_intelligence(
            GitHubRepoIntelligenceConfig(
                out=out,
                queries=queries,
                repos=repos,
                owners=owners,
                owner_names=owner_names,
                max_repos=max_repos,
                max_contributors=max_contributors,
                max_issues=max_issues,
                max_pull_requests=max_pull_requests,
                max_commits=max_commits,
                max_readme_bytes=max_readme_bytes,
                max_readme_snippets=max_readme_snippets,
                timeout_seconds=timeout_seconds,
            )
        )
    except ValueError as exc:
        _fail(ContractError("GITHUB_INTELLIGENCE_FAILED", str(exc)))
    typer.echo(json.dumps(receipt, indent=2, sort_keys=True))


@app.command()
def rank(
    input_dir: Path = typer.Option(..., "--input", exists=True, readable=True),
    limit: int = typer.Option(8, "--limit", min=0, max=8),
    out: Path = typer.Option(..., "--out", file_okay=False),
) -> None:
    """Hard-gate eligibility before deterministic ranking."""
    _configure_logging()
    receipt = rank_candidates(input_dir, limit, out)
    typer.echo(json.dumps({"status": "PASS", **receipt}, indent=2, sort_keys=True))


@app.command()
def tailor(
    posting: str = typer.Option(..., "--posting"),
    claims: Path = typer.Option(..., "--claims", exists=True, dir_okay=False, readable=True),
    out: Path = typer.Option(..., "--out", file_okay=False),
    ranked_run: Path | None = typer.Option(
        None,
        "--ranked-run",
        exists=True,
        file_okay=False,
        readable=True,
        help="Ranking output directory containing shortlist.json; posting selects a live-ranked candidate id.",
    ),
) -> None:
    """Compile a local claim-bound resume variant."""
    _configure_logging()
    try:
        if ranked_run is not None:
            shortlist = read_json(ranked_run / "shortlist.json")
            candidate = next((row for row in shortlist if row.get("candidate_id") == posting), None)
            if candidate is None:
                raise ValueError(f"ranked posting not found: {posting}")
            receipt = tailor_candidate(candidate, claims, out)
        else:
            receipt = tailor_resume(posting, claims, out)
    except ValueError as exc:
        _fail(ContractError("TAILORING_FAILED", str(exc)))
    typer.echo(json.dumps({"status": "PASS", **receipt}, indent=2, sort_keys=True))


@app.command()
def decision(
    run: Path = typer.Option(..., "--run", file_okay=False),
    item: str = typer.Option(..., "--item"),
    action: str = typer.Option(..., "--action"),
    actor: str = typer.Option("candidate", "--actor"),
    idempotency_key: str = typer.Option(..., "--idempotency-key"),
    reason: str | None = typer.Option(None, "--reason"),
) -> None:
    """Append one local decision event; external effects are impossible."""
    _configure_logging()
    try:
        event = append_decision(
            run_dir=run,
            item_id=item,
            action=action,
            actor=actor,
            idempotency_key=idempotency_key,
            reason=reason,
        )
    except ValueError as exc:
        _fail(ContractError("DECISION_REJECTED", str(exc)))
    typer.echo(json.dumps({"status": "PASS", **event}, indent=2, sort_keys=True))


@app.command()
def replay(
    run: Path = typer.Option(..., "--run", exists=True, file_okay=False, readable=True),
) -> None:
    """Replay the local decision ledger into the current projection."""
    _configure_logging()
    projection = replay_decisions(run)
    replay_receipt = build_zero_effect_replay_receipt(run, projection)
    replay_receipt_path = run / "zero-effect-replay-receipt.json"
    write_json(replay_receipt_path, replay_receipt)
    if replay_receipt["status"] != "PASS":
        _fail(
            ContractError(
                "ZERO_EFFECT_REPLAY_FAILED",
                f"Replay produced external-effect violations: {replay_receipt}",
            )
        )
    typer.echo(
        json.dumps(
            {
                "status": "PASS",
                **projection,
                "zero_effect_replay": replay_receipt,
                "zero_effect_replay_path": str(replay_receipt_path),
            },
            indent=2,
            sort_keys=True,
        )
    )


@app.command()
def serve(
    report: Path = typer.Option(..., "--report", exists=True, file_okay=False, readable=True),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port", min=1, max=65535),
    allow_remote: bool = typer.Option(
        False,
        "--allow-remote",
        help="Allow non-loopback bind for Tailscale/LAN review.",
    ),
) -> None:
    """Serve one token-gated morning report and decision loop."""
    _configure_logging()
    try:
        serve_report(report, host, port, allow_remote=allow_remote)
    except ValueError as exc:
        _fail(ContractError("SERVE_REJECTED", str(exc)))


@app.command("run")
def run_command(
    out: Path | None = typer.Option(None, "--out", file_okay=False),
    memory_url: str = typer.Option("http://127.0.0.1:8601", "--memory-url"),
    fixture_dir: Path | None = typer.Option(None, "--fixture-dir", file_okay=False),
    linkedin_evidence: Path | None = typer.Option(
        None,
        "--linkedin-evidence",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local human-supplied LinkedIn top-candidate evidence; no LinkedIn automation.",
    ),
    roundtable_receipts: Path | None = typer.Option(
        None,
        "--roundtable-receipts",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local Ask roundtable receipt map keyed by opportunity_id:channel.",
    ),
    federal_evidence: Path | None = typer.Option(
        None,
        "--federal-evidence",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Read-only SAM.gov website capture (used when the SAM API is down; API break must use the website).",
    ),
    meetup_evidence: Path | None = typer.Option(
        None,
        "--meetup-evidence",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Read-only Meetup source-intel capture; no RSVP, join, message, or GraphQL action.",
    ),
    github_evidence: Path | None = typer.Option(
        None,
        "--github-evidence",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Read-only GitHub repository intelligence artifact; no GitHub mutation or outreach.",
    ),
    linkedin_contact_evidence: Path | None = typer.Option(
        None,
        "--linkedin-contact-evidence",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Read-only LinkedIn 1st/2nd/3rd-degree contact graph evidence; no LinkedIn action.",
    ),
    indeed_evidence: Path | None = typer.Option(
        None,
        "--indeed-evidence",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local read-only Indeed browser capture; source-health only, no apply.",
    ),
    hiddenjobs_evidence: Path | None = typer.Option(
        None,
        "--hiddenjobs-evidence",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local read-only HiddenJobs browser capture; source-health only.",
    ),
    outreach_effects: Path | None = typer.Option(
        None,
        "--outreach-effects",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local outreach effect receipt(s); Gmail drafts must remain unsent.",
    ),
    disable_relationship_signals: bool = typer.Option(
        False,
        "--disable-relationship-signals",
        help="Do not emit relationship/reconnect signals in this run.",
    ),
    degrade_required_sources: bool = typer.Option(
        False,
        "--degrade-required-sources",
        help="Continue report generation after required-source contract violations; diagnostic cron only.",
    ),
) -> None:
    """Run one resumable Stage 0 transaction with no external effects."""
    _configure_logging()
    skill_dir = Path(__file__).resolve().parents[2]
    if out is None:
        out = _new_nightly_run_dir(skill_dir)
    else:
        out = out.expanduser().resolve()
    fixture_dir = _resolve_cli_path(fixture_dir)
    linkedin_evidence = _resolve_cli_path(linkedin_evidence)
    roundtable_receipts = _resolve_cli_path(roundtable_receipts)
    federal_evidence = _resolve_cli_path(federal_evidence)
    meetup_evidence = _resolve_cli_path(meetup_evidence)
    github_evidence = _resolve_cli_path(github_evidence)
    linkedin_contact_evidence = _resolve_cli_path(linkedin_contact_evidence)
    indeed_evidence = _resolve_cli_path(indeed_evidence)
    hiddenjobs_evidence = _resolve_cli_path(hiddenjobs_evidence)
    outreach_effects = _resolve_cli_path(outreach_effects)
    if disable_relationship_signals:
        import os

        os.environ["MONITOR_RELATIONSHIP_SIGNALS_ENABLED"] = "0"
    try:
        receipt = run_stage0(
            skill_dir=skill_dir,
            out_dir=out,
            fixture_dir=fixture_dir,
            linkedin_evidence=linkedin_evidence,
            roundtable_receipts_path=roundtable_receipts,
            outreach_effects_path=outreach_effects,
            federal_evidence=federal_evidence,
            meetup_evidence=meetup_evidence,
            github_evidence=github_evidence,
            linkedin_contact_evidence=linkedin_contact_evidence,
            indeed_evidence=indeed_evidence,
            hiddenjobs_evidence=hiddenjobs_evidence,
            memory_url=memory_url,
            degrade_required_source_failures=degrade_required_sources,
        )
    except ContractError as exc:
        _fail(exc)
    except ValueError as exc:
        _fail(ContractError("RUN_REJECTED", str(exc)))
    typer.echo(json.dumps({"status": "PASS", **receipt}, indent=2, sort_keys=True))


@app.command()
def resume(
    run: Path = typer.Option(..., "--run", exists=True, file_okay=False, readable=True),
) -> None:
    """Read back a prior Stage 0 run status."""
    _configure_logging()
    typer.echo(json.dumps(status_for_run(run), indent=2, sort_keys=True))


@app.command("buzz-review")
def buzz_review(
    run: Path = typer.Option(..., "--run", exists=True, file_okay=False, readable=True),
    channel: str = typer.Option(..., "--channel", help="Buzz channel UUID or configured channel id."),
    target_agent: str = typer.Option(..., "--target-agent", help="Buzz agent name to address."),
    report_url: str = typer.Option(..., "--report-url", help="Human-accessible report URL."),
    out: Path | None = typer.Option(None, "--out", file_okay=False),
    mention_pubkey: str | None = typer.Option(None, "--mention-pubkey"),
    ops_buzz_run: Path | None = typer.Option(None, "--ops-buzz-run", dir_okay=False),
    timeout_seconds: int = typer.Option(0, "--timeout-seconds", min=0, max=600),
    poll_interval_seconds: int = typer.Option(5, "--poll-interval-seconds", min=1, max=60),
    readback_limit: int = typer.Option(20, "--readback-limit", min=1, max=100),
) -> None:
    """Create a no-network Buzz agent-review request for one completed report run."""
    _configure_logging()
    if out is None:
        out = run / "buzz-review"
    try:
        receipt = create_buzz_agent_review(
            BuzzAgentReviewConfig(
                run_dir=run,
                out_dir=out,
                channel=channel,
                target_agent=target_agent,
                report_url=report_url,
                mention_pubkey=mention_pubkey,
                ops_buzz_run=ops_buzz_run,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
                readback_limit=readback_limit,
            )
        )
    except ContractError as exc:
        _fail(exc)
    typer.echo(json.dumps(receipt, indent=2, sort_keys=True))


@app.command("buzz-summary")
def buzz_summary(
    run: Path = typer.Option(..., "--run", exists=True, file_okay=False, readable=True),
    channel: str = typer.Option(..., "--channel", help="Buzz channel UUID or configured channel id."),
    report_url: str = typer.Option(..., "--report-url", help="Human-accessible report URL."),
    out: Path | None = typer.Option(None, "--out", file_okay=False),
    ops_buzz_run: Path | None = typer.Option(None, "--ops-buzz-run", dir_okay=False),
    post: bool = typer.Option(False, "--post", help="Post to Buzz instead of producing a no-network receipt."),
) -> None:
    """Create a Buzz shortlist summary for one completed report run."""
    _configure_logging()
    if out is None:
        out = run / "buzz-summary"
    try:
        receipt = create_buzz_summary(
            BuzzSummaryConfig(
                run_dir=run,
                out_dir=out,
                channel=channel,
                report_url=report_url,
                ops_buzz_run=ops_buzz_run,
                dry_run=not post,
            )
        )
    except ContractError as exc:
        _fail(exc)
    typer.echo(json.dumps(receipt, indent=2, sort_keys=True))


@app.command("tailor-artifact")
def tailor_artifact_command(
    run: Path = typer.Option(..., "--run", exists=True, file_okay=False, readable=True),
    opportunity_id: str = typer.Option(..., "--opportunity", help="opportunity_id from the run report."),
    out: Path | None = typer.Option(None, "--out", file_okay=False),
) -> None:
    """Render one claim-bound tailored resume PDF for one shortlisted opportunity."""
    _configure_logging()
    from .resume_artifact import ResumeArtifactError, tailor_artifact

    skill_dir = Path(__file__).resolve().parents[2]
    report_data = read_json(run / "report" / "report.json")
    opportunity = next(
        (item for item in report_data.get("opportunities", []) if item["opportunity_id"] == opportunity_id),
        None,
    )
    if opportunity is None:
        _fail(ContractError("OPPORTUNITY_NOT_IN_RUN", opportunity_id))
    posting_text = ""
    posting_url = opportunity.get("posting_url") or ""
    if "greenhouse.io" in posting_url:
        try:
            import html as html_mod
            import re as re_mod

            import httpx

            from .ats.greenhouse import greenhouse_questions_url

            board, job_id = posting_url.rstrip("/").split("/jobs/")[0].split("/")[-1], posting_url.rstrip("/").split("/")[-1]
            payload = httpx.get(greenhouse_questions_url(board, job_id), timeout=15.0).json()
            posting_text = html_mod.unescape(re_mod.sub(r"<[^>]+>", " ", payload.get("content") or ""))
        except Exception as exc:
            logger.error("posting text fetch failed; tailoring without alignment: {}", exc)
    try:
        receipt = tailor_artifact(
            skill_dir=skill_dir,
            opportunity=opportunity,
            out_dir=out or (run / "resume-artifacts"),
            posting_text=posting_text,
        )
    except ResumeArtifactError as exc:
        _fail(ContractError("TAILOR_ARTIFACT_REJECTED", str(exc)))
    typer.echo(json.dumps({"status": "PASS", **receipt}, indent=2, sort_keys=True))


@app.command("base-resume")
def base_resume(
    json_output: bool = typer.Option(True, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Resolve the active base resume (files + digests + memory key)."""
    _configure_logging()
    del json_output
    import hashlib

    skill_dir = Path(__file__).resolve().parents[2]
    source = read_json(skill_dir / "config" / "resume_source.json")
    payload: dict[str, object] = {
        "schema": "monitor_opportunities.base_resume.v1",
        "memory_key": source["memory_key"],
    }
    for kind in ("base_markdown", "base_pdf"):
        path = Path(source[kind])
        if not path.exists():
            _fail(ContractError("RESUME_ARTIFACT_MISSING", f"{kind}: {path}"))
        payload[kind] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
    typer.echo(json.dumps({"status": "PASS", **payload}, indent=2, sort_keys=True))


@app.command("ats-prefill")
def ats_prefill(
    plan: Path = typer.Option(..., "--plan", exists=True, dir_okay=False, readable=True),
    site_policy: Path = typer.Option(..., "--site-policy", exists=True, dir_okay=False, readable=True),
    out: Path = typer.Option(..., "--out", file_okay=False),
    close_tab: bool = typer.Option(False, "--close-tab", help="Close the tab instead of leaving it for human completion."),
    attach_resume: Path | None = typer.Option(
        None, "--attach-resume", exists=True, dir_okay=False, readable=True,
        help="Tailored resume PDF; must match the plan's resume_digest.",
    ),
) -> None:
    """Prefill exact-approved fields on the live form; submit is never touched.

    Selectors ride inside the plan fields (same DOM capture the plan digest is
    built from); the ats_selector_bindings memory collection is the recapture
    reference, not a runtime dependency.
    """
    _configure_logging()
    from .ats.prefill_executor import PrefillError, execute_prefill

    plan_data = read_json(plan)
    out.mkdir(parents=True, exist_ok=True)
    try:
        receipt = execute_prefill(
            plan=plan_data,
            bindings={},
            policy=read_json(site_policy),
            binding_digest=None,
            out_dir=out,
            keep_open=not close_tab,
            resume_pdf=attach_resume,
        )
    except PrefillError as exc:
        _fail(ContractError("ATS_PREFILL_REJECTED", str(exc)))
    typer.echo(json.dumps({"status": "PASS", **receipt}, indent=2, sort_keys=True))


def _decision_events_for(run: Path, item_id: str) -> list[dict[str, object]]:
    ledger = run / "decision-ledger.jsonl"
    if not ledger.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("item_id") == item_id:
            rows.append(event)
    return rows


@app.command("apply")
def apply_command(
    run: Path = typer.Option(..., "--run", exists=True, file_okay=False, readable=True),
    application: str | None = typer.Option(None, "--application", help="Application id from the report manifest."),
    packet: str | None = typer.Option(None, "--packet", help="Application packet id from the report manifest."),
    posting: str | None = typer.Option(None, "--posting", help="Opportunity id alias for the intended posting."),
    site_policy: Path | None = typer.Option(
        None,
        "--site-policy",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Future capability-promotion policy receipt; Stage 0 still refuses submit.",
    ),
) -> None:
    """Fail-closed local ATS application gate; Stage 0 never submits."""
    _configure_logging()
    from .application_packets import verify_application_packet

    manifest = read_json(run / "report-manifest.json")
    packets = manifest.get("application_packets", [])
    applications = manifest.get("applications", [])
    matches = []
    for row in packets:
        if packet and row.get("packet_id") == packet:
            matches.append(row)
        elif application and row.get("application_id") == application:
            matches.append(row)
        elif posting and row.get("opportunity_id") == posting:
            matches.append(row)
    if not any([packet, application, posting]) and len(packets) == 1:
        matches = list(packets)
    receipt: dict[str, object] = {
        "schema": "monitor_opportunities.apply_gate_receipt.v1",
        "command": "apply",
        "stage": STAGE,
        "run": str(run),
        "external_effects": False,
        "does_not_submit": True,
        "does_not_prefill": True,
        "candidate_transmits": True,
        "requested": {
            "application": application,
            "packet": packet,
            "posting": posting,
            "site_policy": str(site_policy) if site_policy else None,
        },
    }
    if not matches:
        receipt.update(
            {
                "status": "APPLICATION_PACKET_MISSING",
                "reason": "No exact report-visible application packet matched the request.",
                "application_count": len(applications),
                "application_packet_count": len(packets),
            }
        )
        typer.echo(json.dumps(receipt, indent=2, sort_keys=True), err=True)
        raise typer.Exit(code=2)
    if len(matches) > 1:
        receipt.update(
            {
                "status": "AMBIGUOUS_APPLICATION_PACKET",
                "reason": "Multiple application packets matched; pass --packet or --application.",
                "matches": [row.get("packet_id") for row in matches],
            }
        )
        typer.echo(json.dumps(receipt, indent=2, sort_keys=True), err=True)
        raise typer.Exit(code=2)

    selected = matches[0]
    drift = verify_application_packet(selected)
    app_id = str(selected["application_id"])
    application_row = next((row for row in applications if row.get("application_id") == app_id), {})
    unresolved_fields = [
        field.get("name")
        for field in application_row.get("fields", [])
        if field.get("required") is True and field.get("disposition") == "human_required"
    ]
    events = _decision_events_for(run, app_id)
    latest_action = str(events[-1].get("action")) if events else None
    human_authorized = latest_action == "AUTHORIZE_APPLICATION_PAYLOAD"
    receipt.update(
        {
            "application_id": app_id,
            "opportunity_id": selected.get("opportunity_id"),
            "packet_id": selected.get("packet_id"),
            "packet_ref": selected.get("packet_ref"),
            "approval_payload_digest": selected.get("approval_payload_digest"),
            "drift_check": drift,
            "human_authorized": human_authorized,
            "latest_decision_action": latest_action,
            "unresolved_required_fields": unresolved_fields,
            "site_policy_present": site_policy is not None,
            "capability_authority": {
                "ats_form_submit": "BLOCKED_STAGE_0",
                "ats_form_prefill": "BLOCKED_STAGE_0",
                "gmail_send": "PERMANENTLY_FORBIDDEN",
                "linkedin_action": "PERMANENTLY_FORBIDDEN",
            },
            "next_required_actions": [
                "Review the report-visible application packet.",
                "Resolve every human_required field.",
                "Authorize the exact application payload through the decision ledger.",
                "Promote a site/provider policy before any ATS prefill or submit effect.",
            ],
        }
    )
    if not drift["ok"]:
        receipt["status"] = "APPLICATION_PACKET_DRIFT"
        typer.echo(json.dumps(receipt, indent=2, sort_keys=True), err=True)
        raise typer.Exit(code=2)
    if unresolved_fields:
        receipt["status"] = "HUMAN_FIELDS_REQUIRED"
        receipt["reason"] = "Required application fields remain human_required; this skill must not auto-answer them."
        typer.echo(json.dumps(receipt, indent=2, sort_keys=True), err=True)
        raise typer.Exit(code=2)
    if not human_authorized:
        receipt["status"] = "HUMAN_AUTHORIZATION_REQUIRED"
        typer.echo(json.dumps(receipt, indent=2, sort_keys=True), err=True)
        raise typer.Exit(code=2)
    receipt["status"] = "CAPABILITY_BLOCKED_STAGE_0"
    receipt["reason"] = "Exact local payload is authorized, but Stage 0 has no ATS submit authority."
    typer.echo(json.dumps(receipt, indent=2, sort_keys=True), err=True)
    raise typer.Exit(code=2)




@app.command("commit-ashby")
def commit_ashby_command(
    tab_id: str = typer.Option(..., "--tab-id", help="surf tab id already on the live Ashby application page."),
    candidate_id: str = typer.Option(..., "--candidate-id", help="Ranked candidate id; keys the duplicate-submission ledger."),
    site: str = typer.Option("jobs.ashbyhq.com", "--site"),
    posting_id: str = typer.Option(..., "--posting-id"),
    url: str = typer.Option(..., "--url"),
    allow_duplicate: bool = typer.Option(False, "--allow-duplicate", help="Override the already-applied guard (default: refuse)."),
    resume: Path = typer.Option(..., "--resume", exists=True, dir_okay=False, readable=True),
    promotion: Path = typer.Option(..., "--promotion", exists=True, dir_okay=False, readable=True,
                                   help="Scoped human promotion receipt: ats_form_submit:ashby:<site>."),
    human_answers: Path | None = typer.Option(None, "--human-answers", exists=True, dir_okay=False, readable=True,
                                              help="JSON map of human-supplied answers for required human_required fields (e.g. clearance)."),
) -> None:
    """Submit one live Ashby application through the gated receipt chain.

    Requires a scoped human promotion and refuses to submit while any required
    human_required field (e.g. clearance) is unanswered. The effect state comes
    from a DOM read-back of the provider confirmation, never a self-report.
    """
    _configure_logging()
    from .ats.ashby_apply import AshbyApplyError, commit_ashby_application

    answers = read_json(human_answers) if human_answers else {}
    try:
        receipt = commit_ashby_application(
            tab_id=tab_id,
            candidate_id=candidate_id,
            site=site,
            posting_id=posting_id,
            url=url,
            resume_path=resume,
            promotion=read_json(promotion),
            human_answers=answers,
            allow_duplicate=allow_duplicate,
        )
    except AshbyApplyError as exc:
        _fail(ContractError("ASHBY_COMMIT_REFUSED", str(exc)))
    except Exception as exc:  # noqa: BLE001
        _fail(ContractError("ASHBY_COMMIT_FAILED", repr(exc)))
    typer.echo(json.dumps({"status": receipt["state"], **receipt}, indent=2, sort_keys=True))


@app.command("commit-linkedin")
def commit_linkedin_command(
    tab_id: str = typer.Option(..., "--tab-id", help="surf tab id on the LinkedIn job page (authenticated session)."),
    candidate_id: str = typer.Option(..., "--candidate-id"),
    posting_id: str = typer.Option(..., "--posting-id"),
    apply_url: str = typer.Option(..., "--apply-url"),
    promotion: Path = typer.Option(..., "--promotion", exists=True, dir_okay=False, readable=True,
                                   help="Scoped human promotion receipt: ats_form_submit:linkedin:linkedin.com."),
    allow_duplicate: bool = typer.Option(False, "--allow-duplicate"),
) -> None:
    """Auto-submit one LinkedIn Easy Apply through the gated receipt chain.

    Fills only known-answerable required fields (identity + answer-bank
    eligibility); any unrecognized required screening question stops with
    NEEDS_HUMAN and is surfaced to Graham -- never auto-answered. COMMITTED only
    after reading LinkedIn's 'application was sent' confirmation back.
    """
    _configure_logging()
    from .ats.linkedin_easy_apply import LinkedInEasyApplyError, commit_linkedin_easy_apply

    try:
        receipt = commit_linkedin_easy_apply(
            tab_id=tab_id,
            candidate_id=candidate_id,
            posting_id=posting_id,
            apply_url=apply_url,
            promotion=read_json(promotion),
            allow_duplicate=allow_duplicate,
        )
    except LinkedInEasyApplyError as exc:
        _fail(ContractError("LINKEDIN_COMMIT_REFUSED", str(exc)))
    except Exception as exc:  # noqa: BLE001
        _fail(ContractError("LINKEDIN_COMMIT_FAILED", repr(exc)))
    typer.echo(json.dumps({"status": receipt["state"], **receipt}, indent=2, sort_keys=True))


@app.command("memory-sync")
def memory_sync(
    run: Path = typer.Option(..., "--run", exists=True, file_okay=False, readable=True),
    memory_url: str = typer.Option("http://127.0.0.1:8601", "--memory-url"),
    include_relationship_signals: bool = typer.Option(
        True,
        "--include-relationship-signals/--skip-relationship-signals",
        help="Publish relationship graph documents to Memory.",
    ),
) -> None:
    """Publish one run's shortlist into the memory service (chat is the interface)."""
    _configure_logging()
    from .memory_sync import MemorySyncError, sync_run_to_memory

    try:
        receipt = sync_run_to_memory(
            run,
            memory_url,
            include_relationship_signals=include_relationship_signals,
        )
    except MemorySyncError as exc:
        _fail(ContractError("MEMORY_SYNC_REJECTED", str(exc)))
    except Exception as exc:
        _fail(ContractError("MEMORY_SYNC_TRANSPORT_FAILED", repr(exc)))
    receipt_path = run / "memory-sync-receipt.json"
    write_json(receipt_path, receipt)
    typer.echo(
        json.dumps(
            {"status": "PASS", "receipt_path": str(receipt_path), **receipt},
            indent=2,
            sort_keys=True,
        )
    )


@app.command()
def nightly(
    out: Path | None = typer.Option(None, "--out", file_okay=False),
    memory_url: str = typer.Option("http://127.0.0.1:8601", "--memory-url"),
    diagnostic: bool = typer.Option(False, "--diagnostic", help="Run with external publication effects disabled."),
    promoted_stage0: bool = typer.Option(
        False,
        "--promoted-stage0",
        help="Publish the gated Stage 0 report, digest, Memory graph, and Buzz summary.",
    ),
    require_clean: bool = typer.Option(False, "--require-clean", help="Fail before capture if this skill tree is dirty."),
    expected_revision: str | None = typer.Option(None, "--expected-revision", help="Fail unless the running commit matches."),
    skip_tracker: bool = typer.Option(False, "--skip-tracker", help="Do not create or update tracker issues."),
    skip_ats_memory: bool = typer.Option(False, "--skip-ats-memory", help="Do not persist learned ATS forms to Memory."),
    skip_memory_sync: bool = typer.Option(False, "--skip-memory-sync", help="Do not publish the run summary to Memory."),
    skip_relationship_memory: bool = typer.Option(False, "--skip-relationship-memory", help="Exclude relationship graph docs from Memory sync."),
    skip_buzz: bool = typer.Option(False, "--skip-buzz", help="Skip the Buzz shortlist post."),
    skip_tau_semantic_prepare: bool = typer.Option(
        False,
        "--skip-tau-semantic-prepare",
        help="Do not materialize Tau semantic inputs for the report run.",
    ),
    tau_semantic_top_n: int = typer.Option(3, "--tau-semantic-top-n", min=1, max=8),
    tau_semantic_provider: bool = typer.Option(
        False,
        "--tau-semantic-provider",
        help="Run/install provider-live semantic addenda through /ask for prepared inputs.",
    ),
    tau_semantic_handler: str = typer.Option("webgpt", "--tau-semantic-handler"),
    tau_semantic_timeout_seconds: int = typer.Option(3600, "--tau-semantic-timeout-seconds", min=60),
    tau_semantic_browser_lock_timeout: int = typer.Option(1800, "--tau-semantic-browser-lock-timeout", min=60),
) -> None:
    """One nightly transaction: run, publish shortlist to memory, post Buzz summary.

    The rendered report stays in the run directory as a frozen receipt; the
    memory collection and Buzz post are the interaction surface.
    """
    _configure_logging()
    import shutil
    import subprocess

    skill_dir = Path(__file__).resolve().parents[2]
    promote_latest_on_success = out is None
    if out is None:
        out = _new_nightly_run_dir(skill_dir, promote_latest=False)
    else:
        out = out.expanduser().resolve()
    run_sh = skill_dir / "run.sh"
    steps: dict[str, object] = {}
    run_env = _nightly_subprocess_env(skill_dir, steps)

    if diagnostic and promoted_stage0:
        _fail(ContractError("NIGHTLY_MODE_CONFLICT", "Choose diagnostic or promoted Stage 0, not both"))
    if diagnostic:
        skip_buzz = True
        skip_tracker = True
        skip_ats_memory = True
        require_clean = True
    elif promoted_stage0:
        if skip_memory_sync or skip_relationship_memory or skip_buzz:
            _fail(
                ContractError(
                    "PROMOTED_STAGE0_PUBLICATION_DISABLED",
                    "Promoted Stage 0 requires Memory, relationship graph, and Buzz publication",
                )
            )
        skip_tracker = True
        skip_ats_memory = True
        require_clean = True
        tau_semantic_provider = True

    # `latest/` is intentionally reused by cron. Clear prior generated artifacts
    # before capture so stale tailoring/application files cannot imply current
    # run capability when this invocation produced no opportunities.
    prepare_run_output(out, include_browser_capture=True)
    for stale_receipt in (
        out / "effect-policy-receipt.json",
        out / "memory-sync-receipt.json",
        out / "nightly-receipt.json",
        out / "buzz-summary" / "buzz-summary-receipt.json",
    ):
        if stale_receipt.exists():
            stale_receipt.unlink()
    for stale_dir in (out / "tau-semantic", out / "semantic-addenda"):
        if stale_dir.exists():
            shutil.rmtree(stale_dir)

    # Deployment attestation must happen before any browser/source capture so a
    # scheduled run cannot silently execute stale or dirty code.
    from .run_attestation import attest

    attestation = attest(skill_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "run-attestation.json").write_text(
        json.dumps(attestation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    revision_full = str(attestation["code"].get("git_revision_full") or "")
    revision_short = str(attestation["code"].get("git_revision") or "")
    expected_matches = (
        not expected_revision
        or expected_revision in {revision_full, revision_short}
        or revision_full.startswith(expected_revision)
    )
    steps["attestation"] = {
        "ok": attestation["ok"],
        "git_revision": revision_short,
        "git_revision_full": revision_full,
        "expected_revision": expected_revision,
        "expected_revision_matches": expected_matches,
        "skill_tree_dirty": attestation["code"]["skill_tree_dirty"],
        "environment": attestation["runtime"]["environment"],
        "missing_required_credentials": attestation["credentials"]["missing_required"],
        "diagnostic": diagnostic,
    }
    # A dirty tree is RECORDED, never fatal (Graham, 2026-08-18). The gate refused
    # two nightlies for changes that could not affect a run: untracked local/ run
    # artifacts, then a one-line "# Generated by test-lab" comment that another
    # skill stamped into 16 test files. The receipt still carries skill_tree_dirty
    # so provenance is visible; it just does not stop the work.
    if require_clean and attestation["code"]["skill_tree_dirty"]:
        logger.warning(
            "monitor-opportunities tree is dirty; continuing anyway and recording it in the receipt"
        )
    if not expected_matches:
        _fail(ContractError("NIGHTLY_REVISION_MISMATCH", f"Expected {expected_revision}, got {revision_full}"))
    if not attestation["ok"]:
        logger.error(
            "CREDENTIAL PREFLIGHT FAILED: missing {}. Results will be incomplete; "
            "this is a deployment failure, not an empty market.",
            attestation["credentials"]["missing_required"],
        )
    publication_mode = "PROMOTED_STAGE_0" if promoted_stage0 else ("DIAGNOSTIC" if diagnostic else "MANUAL")
    effect_policy_path = out / "effect-policy-receipt.json"
    effect_policy = {
        "schema": "monitor_opportunities.effect_policy_receipt.v1",
        "mode": publication_mode,
        "diagnostic": diagnostic,
        "promoted_stage0": promoted_stage0,
        "external_effects": False,
        "publications": {
            "local_report": "ENABLED",
            "digest": "ENABLED",
            "memory_summary": "SKIPPED" if skip_memory_sync else "ENABLED",
            "relationship_graph": "SKIPPED" if skip_relationship_memory else "ENABLED",
            "buzz_summary": "SKIPPED" if skip_buzz else "ENABLED",
        },
        "read_only_checks": {
            "prior_application_history": "ENABLED",
        },
        "separately_gated": {
            "tracker": "SKIPPED" if skip_tracker else "ENABLED",
            "ats_selector_memory_write": "SKIPPED" if skip_ats_memory else "ENABLED",
        },
        "forbidden_effects": {
            "gmail_send": "FORBIDDEN",
            "gmail_schedule_send": "FORBIDDEN",
            "gmail_forward": "FORBIDDEN",
            "linkedin_action": "FORBIDDEN",
            "meetup_rsvp": "FORBIDDEN",
            "ats_submit": "FORBIDDEN",
        },
    }
    write_json(effect_policy_path, effect_policy)
    steps["effect_policy"] = {**effect_policy, "receipt": str(effect_policy_path)}

    # Browser-capture no-API / broken-API sources (SAM.gov API 404s) so the run
    # satisfies the API-website-fallback rule autonomously. Requires Chrome open.
    from .browser_capture import (
        browser_control_summary,
        capture_hiddenjobs,
        capture_indeed_jobs,
        capture_linkedin_advanced_search,
        capture_linkedin_actively_hiring,
        capture_linkedin_who_viewed,
        capture_linkedin_top_applicant,
        capture_meetup_buffalo_isolated,
        capture_sales_navigator_saved,
        capture_sam,
        reset_browser_control_events,
    )

    capture_dir = out / "browser-capture"
    reset_browser_control_events()
    sam_receipt = capture_sam(capture_dir)
    steps["browser_capture_sam"] = {"status": sam_receipt.get("status"), "captured": sam_receipt.get("opportunities_captured")}
    federal_evidence = sam_receipt.get("evidence_path")

    # LinkedIn jobs: advanced search (primary, server-side filtered) + top-applicant.
    # Both best-effort; feed the run the evidence that captured the most rows.
    adv_receipt = capture_linkedin_advanced_search(capture_dir)
    steps["browser_capture_linkedin_advanced"] = {"status": adv_receipt.get("status"), "captured": adv_receipt.get("opportunities_captured")}
    li_receipt = capture_linkedin_top_applicant(capture_dir)
    steps["browser_capture_linkedin"] = {"status": li_receipt.get("status"), "captured": li_receipt.get("opportunities_captured")}
    linkedin_candidates = [r for r in (adv_receipt, li_receipt) if r.get("evidence_path")]
    linkedin_candidates.sort(key=lambda r: int(r.get("opportunities_captured") or 0), reverse=True)
    linkedin_evidence = linkedin_candidates[0].get("evidence_path") if linkedin_candidates else None
    # Merge the OTHER LinkedIn stream in rather than discarding it: picking only
    # the higher-row-count file silently dropped every top-applicant row (with
    # its top_candidate=True flag), so Graham's top-candidate roles never ranked.
    for other in linkedin_candidates[1:]:
        _merge_linkedin_top_candidate(Path(linkedin_evidence), Path(other["evidence_path"]))

    # LinkedIn Premium low-competition pass: same searches with f_EA=true (Under
    # 10 applicants), extracted via aria-labels. Rows carry the premium signals
    # (competition 0.1, warm_path from 'connection works here') and are MERGED
    # into the chosen evidence so ranking sees one deduped stream. Best-effort.
    from .browser_capture import capture_linkedin_premium

    prem_receipt = capture_linkedin_premium(capture_dir)
    steps["browser_capture_linkedin_premium"] = {
        "status": prem_receipt.get("status"),
        "captured": prem_receipt.get("opportunities_captured"),
        "warm_paths_found": prem_receipt.get("warm_paths_found"),
    }
    if prem_receipt.get("evidence_path") and linkedin_evidence:
        try:
            base = json.loads(Path(linkedin_evidence).read_text(encoding="utf-8"))
            prem = json.loads(Path(prem_receipt["evidence_path"]).read_text(encoding="utf-8"))
            seen_keys = {
                (o.get("title"), o.get("organization")) for o in base.get("opportunities", [])
            }
            merged = 0
            for o in prem.get("opportunities", []):
                if (o.get("title"), o.get("organization")) not in seen_keys:
                    base["opportunities"].append(o)
                    merged += 1
            Path(linkedin_evidence).write_text(json.dumps(base, indent=1), encoding="utf-8")
            steps["browser_capture_linkedin_premium"]["merged_into_evidence"] = merged
        except (OSError, ValueError) as exc:
            logger.warning("premium evidence merge skipped: {}", exc)
    elif prem_receipt.get("evidence_path") and not linkedin_evidence:
        linkedin_evidence = prem_receipt["evidence_path"]

    linkedin_contact_evidence = None
    contact_rows: list[dict[str, Any]] = []
    wv_receipt = capture_linkedin_who_viewed(capture_dir)
    steps["browser_capture_linkedin_who_viewed"] = {
        "status": wv_receipt.get("status"),
        "captured": wv_receipt.get("viewers_captured"),
    }
    if wv_receipt.get("evidence_path"):
        try:
            for row in read_json(Path(str(wv_receipt["evidence_path"]))).get("viewers", []):
                if isinstance(row, dict):
                    contact_rows.append({**row, "linkedin_contact_source": "who_viewed"})
        except (OSError, ValueError):
            pass
    ah_receipt = capture_linkedin_actively_hiring(capture_dir)
    steps["browser_capture_linkedin_actively_hiring"] = {
        "status": ah_receipt.get("status"),
        "captured": ah_receipt.get("contacts_captured"),
    }
    if ah_receipt.get("evidence_path"):
        try:
            for row in read_json(Path(str(ah_receipt["evidence_path"]))).get("contacts", []):
                if isinstance(row, dict):
                    contact_rows.append({**row, "linkedin_contact_source": "actively_hiring"})
        except (OSError, ValueError):
            pass
    if contact_rows:
        linkedin_contact_evidence_path = capture_dir / "linkedin-contact-graph-evidence.json"
        write_json(
            linkedin_contact_evidence_path,
            {
                "schema_version": "monitor_opportunities.linkedin_contact_graph_evidence.v1",
                "observed_at": utc_now(),
                "source": "human_authorized_linkedin_contact_graph",
                "automation_policy": "linkedin_authorized_read_only_no_actions",
                "external_effects": False,
                "contacts": contact_rows,
                "non_claims": [
                    "No LinkedIn connect, follow, message, InMail, email, application, or profile mutation occurred.",
                    "Relationship-degree evidence is for human review and report binding only.",
                ],
            },
        )
        linkedin_contact_evidence = str(linkedin_contact_evidence_path)
    steps["browser_capture_linkedin_contact_graph"] = {
        "captured": len(contact_rows),
        "evidence_path": linkedin_contact_evidence,
        "external_effects": False,
    }

    # Required aggregator/locator sources: capture visible browser evidence to
    # satisfy source-health contracts without admitting these rows as ranked
    # opportunities or performing any site action.
    indeed_receipt = capture_indeed_jobs(capture_dir)
    steps["browser_capture_indeed"] = {
        "status": indeed_receipt.get("status"),
        "captured": indeed_receipt.get("records_captured"),
    }
    indeed_evidence = indeed_receipt.get("evidence_path")
    hiddenjobs_receipt = capture_hiddenjobs(capture_dir)
    steps["browser_capture_hiddenjobs"] = {
        "status": hiddenjobs_receipt.get("status"),
        "captured": hiddenjobs_receipt.get("records_captured"),
    }
    hiddenjobs_evidence = hiddenjobs_receipt.get("evidence_path")

    # Client-prospecting engine (separate from jobs): Sales Navigator saved leads,
    # strictly read-only. Best-effort; captured to its own evidence, not fed to the
    # jobs run. Graham transmits every outreach himself.
    sn_receipt = capture_sales_navigator_saved(capture_dir)
    steps["browser_capture_sales_navigator"] = {"status": sn_receipt.get("status"), "captured": sn_receipt.get("prospects_captured")}

    meetup_max_group_pages = max(1, int(os.environ.get("MONITOR_MEETUP_MAX_GROUP_PAGES", "8")))
    meetup_receipt = capture_meetup_buffalo_isolated(
        capture_dir / "meetup",
        max_group_pages=meetup_max_group_pages,
    )
    steps["browser_capture_meetup_buffalo"] = {
        "status": meetup_receipt.get("status"),
        "captured": meetup_receipt.get("groups_captured"),
        "category_ids": meetup_receipt.get("category_ids"),
        "max_group_pages": meetup_max_group_pages,
    }
    meetup_evidence = meetup_receipt.get("evidence_path")
    steps["browser_control"] = browser_control_summary()

    github_queries = _split_env_list(os.environ.get("MONITOR_GITHUB_INTEL_QUERIES"))
    if not github_queries:
        github_queries = DEFAULT_GITHUB_INTELLIGENCE_QUERIES
    github_repos = _split_env_list(os.environ.get("MONITOR_GITHUB_INTEL_REPOS"))
    if not github_repos:
        github_repos = DEFAULT_GITHUB_INTELLIGENCE_REPOS
    github_owners = _split_env_list(os.environ.get("MONITOR_GITHUB_INTEL_OWNERS"))
    if not github_owners:
        github_owners = DEFAULT_GITHUB_INTELLIGENCE_OWNERS
    github_owner_names = _parse_owner_names(
        _split_env_list(os.environ.get("MONITOR_GITHUB_INTEL_OWNER_NAMES"))
    )
    if not github_owner_names:
        github_owner_names = DEFAULT_GITHUB_INTELLIGENCE_OWNER_NAMES
    try:
        github_max_repos = max(1, min(25, int(os.environ.get("MONITOR_GITHUB_INTEL_MAX_REPOS", "8"))))
    except ValueError:
        github_max_repos = 8
    try:
        github_max_participants = max(
            0, min(50, int(os.environ.get("MONITOR_GITHUB_INTEL_MAX_PARTICIPANTS", "12")))
        )
    except ValueError:
        github_max_participants = 12
    try:
        github_max_readme_bytes = max(
            0, min(50000, int(os.environ.get("MONITOR_GITHUB_INTEL_MAX_README_BYTES", "12000")))
        )
    except ValueError:
        github_max_readme_bytes = 12000
    try:
        github_max_readme_snippets = max(
            0, min(20, int(os.environ.get("MONITOR_GITHUB_INTEL_MAX_README_SNIPPETS", "8")))
        )
    except ValueError:
        github_max_readme_snippets = 8
    github_evidence_path = capture_dir / "github-repo-intelligence.json"
    github_config = GitHubRepoIntelligenceConfig(
        out=github_evidence_path,
        queries=github_queries,
        repos=github_repos,
        owners=github_owners,
        owner_names=github_owner_names,
        max_repos=github_max_repos,
        max_contributors=github_max_participants,
        max_issues=max(0, min(12, github_max_participants)),
        max_pull_requests=max(0, min(12, github_max_participants)),
        max_commits=max(0, min(12, github_max_participants)),
        max_readme_bytes=github_max_readme_bytes,
        max_readme_snippets=github_max_readme_snippets,
    )
    try:
        github_receipt = collect_github_repo_intelligence(github_config)
    except Exception as exc:  # pragma: no cover - exercised through nightly integration tests
        github_receipt = write_degraded_github_repo_intelligence(
            github_config,
            error=f"{type(exc).__name__}: {exc}",
        )
    write_json(capture_dir / "github-repo-intelligence-receipt.json", github_receipt)
    steps["github_repo_intelligence"] = {
        "status": github_receipt.get("status"),
        "artifact": github_receipt.get("artifact_path"),
        "repositories_captured": github_receipt.get("repositories_captured"),
        "contacts_captured": github_receipt.get("contacts_captured"),
        "degradation_count": github_receipt.get("degradation_count"),
        "owner_handles": github_receipt.get("owner_handles"),
        "owner_name_seeds": github_receipt.get("owner_name_seeds"),
        "external_effects": github_receipt.get("external_effects"),
    }
    github_evidence = github_receipt.get("artifact_path") if github_evidence_path.exists() else None

    run_cmd = [str(run_sh), "run", "--out", str(out)]
    if diagnostic:
        run_cmd.extend(["--memory-url", memory_url, "--degrade-required-sources"])
    if federal_evidence:
        run_cmd += ["--federal-evidence", str(federal_evidence)]
    if linkedin_evidence:
        run_cmd += ["--linkedin-evidence", str(linkedin_evidence)]
    if meetup_evidence:
        run_cmd += ["--meetup-evidence", str(meetup_evidence)]
    if github_evidence:
        run_cmd += ["--github-evidence", str(github_evidence)]
    if linkedin_contact_evidence:
        run_cmd += ["--linkedin-contact-evidence", str(linkedin_contact_evidence)]
    if indeed_evidence:
        run_cmd += ["--indeed-evidence", str(indeed_evidence)]
    if hiddenjobs_evidence:
        run_cmd += ["--hiddenjobs-evidence", str(hiddenjobs_evidence)]
    run_proc = subprocess.run(run_cmd, capture_output=True, text=True, timeout=3600, env=run_env)
    steps["run"] = {"exit_code": run_proc.returncode}
    if run_proc.returncode != 0:
        _fail(ContractError("NIGHTLY_RUN_FAILED", run_proc.stderr[-2000:]))
    run_receipt_path = out / "run-receipt.json"
    if run_receipt_path.exists():
        run_receipt = read_json(run_receipt_path)
        degraded_contracts = run_receipt.get("degraded_contracts") or []
        steps["run"]["receipt"] = str(run_receipt_path)
        steps["run"]["external_effects"] = run_receipt.get("external_effects")
        steps["run"]["degraded_contracts"] = degraded_contracts
        steps["run"]["degraded_contract_codes"] = [str(item.get("code")) for item in degraded_contracts if item.get("code")]
    if promoted_stage0:
        if not run_receipt_path.exists() or read_json(run_receipt_path).get("external_effects") is not False:
            _fail(ContractError("PROMOTED_STAGE0_RUN_RECEIPT_INVALID", "Run receipt missing external_effects=false"))
        if not (out / "report" / "report.json").exists() or not (out / "report" / "index.html").exists():
            _fail(ContractError("PROMOTED_STAGE0_REPORT_MISSING", "Stage 0 report artifacts were not written"))

    semantic_prepare_receipt: dict[str, object] | None = None
    semantic_installs: list[dict[str, object]] = []
    if skip_tau_semantic_prepare:
        steps["tau_semantic"] = {"skipped": True}
    else:
        tau_out = out / "tau-semantic"
        try:
            semantic_prepare_receipt = prepare_tau_semantic_inputs(
                run_dir=out,
                out_dir=tau_out,
                top_n=tau_semantic_top_n,
            )
        except (ContractError, FileNotFoundError, ValueError) as exc:
            if promoted_stage0:
                _fail(ContractError("PROMOTED_STAGE0_TAU_SEMANTIC_PREPARE_FAILED", str(exc)))
            steps["tau_semantic"] = {"status": "ERROR", "error": str(exc), "provider_live": False}
        else:
            steps["tau_semantic"] = {
                "status": semantic_prepare_receipt.get("status"),
                "receipt": str(tau_out / "tau-semantic-prepare-receipt.json"),
                "selected_count": semantic_prepare_receipt.get("selected_count"),
                "rejected_count": semantic_prepare_receipt.get("rejected_count"),
                "provider_live": False,
                "external_effects": False,
            }
            if promoted_stage0 and semantic_prepare_receipt.get("status") != "PASS":
                _fail(
                    ContractError(
                        "PROMOTED_STAGE0_TAU_SEMANTIC_PREPARE_FAILED",
                        "Tau semantic preparation produced no admissible provider inputs",
                    )
                )

        if tau_semantic_provider and semantic_prepare_receipt and semantic_prepare_receipt.get("status") == "PASS":
            provider_results: list[dict[str, object]] = []
            for selected in semantic_prepare_receipt.get("selected", []):  # type: ignore[union-attr]
                input_path = Path(str(selected["artifact"]))
                provider_dir = tau_out / "providers" / input_path.stem
                try:
                    provider_receipt = run_provider_semantic_eval(
                        input_path=input_path,
                        out_dir=provider_dir,
                        handler=tau_semantic_handler,
                        execute=True,
                        timeout_seconds=tau_semantic_timeout_seconds,
                        browser_lock_timeout=tau_semantic_browser_lock_timeout,
                    )
                    provider_results.append(
                        {
                            "opportunity_id": provider_receipt.get("opportunity_id"),
                            "handler": provider_receipt.get("handler"),
                            "status": provider_receipt.get("status"),
                            "receipt": str(provider_dir / "tau-semantic-provider-receipt.json"),
                            "provider_live": provider_receipt.get("provider_live"),
                        }
                    )
                    if provider_receipt.get("status") != "PASS":
                        raise ContractError(
                            "TAU_SEMANTIC_PROVIDER_FAILED",
                            f"provider status {provider_receipt.get('status')}",
                        )
                    install_receipt = install_semantic_addendum(
                        run_dir=out,
                        provider_receipt_path=provider_dir / "tau-semantic-provider-receipt.json",
                    )
                    semantic_installs.append(install_receipt)
                    if promoted_stage0:
                        break
                except (ContractError, FileNotFoundError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
                    provider_results.append(
                        {
                            "opportunity_id": str(selected.get("opportunity_id", "")),
                            "handler": tau_semantic_handler,
                            "status": "ERROR",
                            "error": str(exc),
                            "provider_live": False,
                        }
                    )
                    if not promoted_stage0:
                        break
                    continue
            steps["tau_semantic"]["provider_results"] = provider_results  # type: ignore[index]
            steps["tau_semantic"]["installed_addenda"] = len(semantic_installs)  # type: ignore[index]
            steps["tau_semantic"]["provider_live"] = bool(semantic_installs)  # type: ignore[index]
            if promoted_stage0 and not semantic_installs:
                _fail(
                    ContractError(
                        "PROMOTED_STAGE0_TAU_SEMANTIC_PROVIDER_FAILED",
                        "Promoted Stage 0 requires at least one provider-live Tau semantic addendum",
                    )
                )

    # Live ATS form capture: for each top job, read-only capture of the
    # application-form schema so a human-promoted site policy can later drive
    # inspect -> plan -> authorize -> commit. Best-effort, read-only, no submit.
    # Resumes are tailored for all top jobs (cheap, local). Browser-DOM ATS form
    # capture is ~30s each, so bound it to the top-K; the rest are captured on
    # human demand when a job is greenlit. Env-overridable.
    import os as _os

    from .browser_capture import capture_ats_form

    try:
        ats_capture_top_k = max(0, int(_os.environ.get("MONITOR_ATS_CAPTURE_TOP_K", "12")))
    except ValueError:
        ats_capture_top_k = 12
    apply_prep_path = out / "tailoring" / "apply-prep.json"
    ats_summary = []
    if apply_prep_path.exists():
        packets = json.loads(apply_prep_path.read_text(encoding="utf-8"))
        for idx, packet in enumerate(packets):
            apply_url = packet.get("apply_url")
            if idx >= ats_capture_top_k or not apply_url:
                packet["ats_form_status"] = "DEFERRED" if apply_url else "NO_URL"
                continue
            form_receipt = capture_ats_form(apply_url, capture_dir / "ats-forms")
            packet["ats_form_status"] = form_receipt.get("status")
            packet["ats_form_path"] = form_receipt.get("form_path")
            packet["ats_form_field_count"] = form_receipt.get("field_count")
            packet["ats_form_human_required"] = form_receipt.get("human_required_fields")
            if skip_ats_memory:
                learned = {"key": None, "stored": False, "skipped": "diagnostic_or_explicit_skip"}
            else:
                # Persist the learned apply form to /memory per opportunity
                # (digest-bound; real forms only, not LinkedIn-view stubs). Fail-soft.
                from .ats_store import store_learned_form

                learned = store_learned_form(str(packet.get("candidate_id") or ""), form_receipt)
            packet["ats_form_memory_key"] = learned.get("key")
            packet["ats_form_stored"] = learned.get("stored")
            ats_summary.append({"candidate_id": packet.get("candidate_id"), "status": form_receipt.get("status"), "fields": form_receipt.get("field_count"), "memory_stored": learned.get("stored")})
        apply_prep_path.write_text(json.dumps(packets, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    steps["ats_form_capture"] = {"captured": len(ats_summary), "top_k": ats_capture_top_k, "results": ats_summary}

    # Track each shortlisted opportunity as an issue in the PRIVATE tracker repo
    # (dedup by content_hash; a re-seen posting gets a re-eval comment, not a
    # duplicate). Fail-soft: a GitHub outage records the failure but never fails
    # the nightly. Disable with MONITOR_TRACKER_ENABLED=0.
    from .github_tracker import GithubTrackerError, file_or_update_opportunity

    tracker_repo = _os.environ.get("MONITOR_TRACKER_REPO", "grahama1970/opportunities")
    shortlist_path = out / "ranking" / "shortlist.json"
    tracked: list[dict[str, object]] = []
    # Track only the top slice, not the whole shortlist: the 2026-08-13 run filed
    # 150 issues in one night, which is noise rather than tracking. The board
    # should hold what Graham might act on. Env-overridable.
    try:
        tracker_top_n = max(1, int(_os.environ.get("MONITOR_TRACKER_TOP_N", "25")))
    except ValueError:
        tracker_top_n = 25
    if skip_tracker:
        steps["tracker"] = {"tracked": 0, "repo": tracker_repo, "top_n": tracker_top_n, "skipped": True}
    elif _os.environ.get("MONITOR_TRACKER_ENABLED", "1") == "1" and shortlist_path.exists():
        shortlist = json.loads(shortlist_path.read_text(encoding="utf-8"))
        for opp in shortlist[:tracker_top_n]:
            try:
                result = file_or_update_opportunity(
                    opp,
                    repo=tracker_repo,
                    state_label="state:shortlisted",
                    comment="Re-evaluated by tonight's nightly.",
                )
                tracked.append({"number": result.get("number"), "action": result.get("action")})
            except (GithubTrackerError, subprocess.TimeoutExpired) as exc:
                logger.warning("tracker skipped for {}: {}", opp.get("candidate_id"), exc)
        steps["tracker"] = {"tracked": len(tracked), "repo": tracker_repo, "top_n": tracker_top_n}
    else:
        steps["tracker"] = {"tracked": 0, "repo": tracker_repo, "top_n": tracker_top_n, "disabled": True}

    # Morning digest + lane health: extracted to nightly_digest (thin-function rule).
    from .nightly_digest import lane_health_phase, run_digest_phase

    try:
        run_digest_phase(out, skill_dir, capture_dir, memory_url, steps, degrade_digest_contract=diagnostic)
    except ContractError as exc:
        _fail(exc)
    lane_health_phase(out, steps)
    if promoted_stage0 and not (out / "morning-digest.json").exists():
        _fail(ContractError("PROMOTED_STAGE0_DIGEST_MISSING", "Validated morning digest was not written"))

    # Self-heal memory: if the service is down, restart its container and wait
    # for health rather than failing the nightly (no reason to fail on a
    # restartable dependency).
    import time as _time
    import urllib.request as _urlreq

    def _memory_healthy() -> bool:
        try:
            with _urlreq.urlopen(f"{memory_url}/health", timeout=5) as resp:
                return resp.status == 200
        except Exception:  # noqa: BLE001 - any failure means restart-and-retry
            return False

    if not skip_memory_sync and not _memory_healthy():
        logger.warning("memory service down; restarting embry-memory container")
        subprocess.run(["docker", "restart", "embry-memory"], capture_output=True, text=True, timeout=120)
        for _ in range(30):
            if _memory_healthy():
                break
            _time.sleep(5)
    steps["memory_healthy"] = _memory_healthy() if not skip_memory_sync else "SKIPPED"

    if skip_memory_sync:
        steps["memory_sync"] = {"skipped": True}
    else:
        memory_receipt_path = out / "memory-sync-receipt.json"
        sync_cmd = [str(run_sh), "memory-sync", "--run", str(out), "--memory-url", memory_url]
        if skip_relationship_memory:
            sync_cmd.append("--skip-relationship-signals")
        sync_proc = subprocess.run(
            sync_cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        steps["memory_sync"] = {
            "exit_code": sync_proc.returncode,
            "relationship_signals_included": not skip_relationship_memory,
            "receipt": str(memory_receipt_path),
        }
        if sync_proc.returncode != 0:
            _fail(ContractError("NIGHTLY_MEMORY_SYNC_FAILED", sync_proc.stderr[-2000:]))
        if memory_receipt_path.exists():
            memory_receipt = read_json(memory_receipt_path)
            steps["memory_sync"].update(
                {
                    "readback_found": memory_receipt.get("readback_found"),
                    "relationship_readback_found": memory_receipt.get("relationship_readback_found"),
                    "readback_external_effects_false": memory_receipt.get("readback_external_effects_false"),
                    "readback_missing_keys": memory_receipt.get("readback_missing_keys", []),
                    "stored_keys": memory_receipt.get("stored_keys", []),
                    "external_effects": memory_receipt.get("external_effects"),
                }
            )
        if promoted_stage0 and (
            not memory_receipt_path.exists()
            or memory_receipt.get("readback_found") is not True
            or memory_receipt.get("relationship_readback_found") is not True
            or memory_receipt.get("readback_external_effects_false") is not True
            or memory_receipt.get("relationship_signals_included") is not True
            or memory_receipt.get("external_effects") is not False
        ):
            _fail(
                ContractError(
                    "PROMOTED_STAGE0_MEMORY_READBACK_FAILED",
                    "Memory summary and relationship graph did not read back with external_effects=false",
                )
            )

    if skip_buzz:
        steps["buzz"] = {"skipped": True}
    else:
        buzz_receipt_path = out / "buzz-summary" / "buzz-summary-receipt.json"
        notifications = read_json(skill_dir / "config" / "notifications.json")
        buzz_proc = subprocess.run(
            [
                str(run_sh),
                "buzz-summary",
                "--run",
                str(out),
                "--channel",
                str(notifications["buzz_channel"]),
                "--report-url",
                f"file://{out}/report/index.html",
                "--post",
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        steps["buzz"] = {"exit_code": buzz_proc.returncode, "receipt": str(buzz_receipt_path)}
        if buzz_proc.returncode != 0:
            steps["buzz"]["error_tail"] = buzz_proc.stderr[-800:]
            if promoted_stage0:
                _fail(ContractError("PROMOTED_STAGE0_BUZZ_FAILED", buzz_proc.stderr[-2000:]))
        if buzz_receipt_path.exists():
            buzz_receipt = read_json(buzz_receipt_path)
            steps["buzz"].update(
                {
                    "posted": buzz_receipt.get("posted"),
                    "live": buzz_receipt.get("live"),
                    "external_effects": buzz_receipt.get("external_effects"),
                }
            )
        if promoted_stage0 and (
            not buzz_receipt_path.exists()
            or buzz_receipt.get("posted") is not True
            or buzz_receipt.get("live") is not True
            or buzz_receipt.get("dry_run") is not False
            or buzz_receipt.get("external_effects") is not False
        ):
            _fail(
                ContractError(
                    "PROMOTED_STAGE0_BUZZ_READBACK_FAILED",
                    "Buzz post receipt did not prove a live post with external_effects=false",
                )
            )

    consistency_path = out / "receipt-consistency.json"
    report_acceptance_path = out / "report-acceptance-receipt.json"
    if promoted_stage0 and run_receipt_path.exists():
        run_receipt = read_json(run_receipt_path)
        run_receipt["report_acceptance_required"] = True
        run_receipt["report_acceptance_receipt"] = str(report_acceptance_path)
        run_receipt["promoted_stage0_final_gate"] = "report_acceptance"
        write_json(run_receipt_path, run_receipt)
    if run_receipt_path.exists() and (out / "report-manifest.json").exists():
        consistency = build_receipt_consistency(
            run_dir=out,
            receipt=read_json(run_receipt_path),
            manifest=read_json(out / "report-manifest.json"),
        )
        write_json(consistency_path, consistency)
        if promoted_stage0 and consistency.get("status") != "PASS":
            _fail(
                ContractError(
                    "PROMOTED_STAGE0_RECEIPT_CONSISTENCY_FAILED",
                    f"Receipt consistency failed: {consistency}",
                )
            )
    else:
        consistency = None

    decision_projection = replay_decisions(out)
    replay_receipt_path = out / "zero-effect-replay-receipt.json"
    replay_receipt = build_zero_effect_replay_receipt(out, decision_projection)
    write_json(replay_receipt_path, replay_receipt)
    steps["zero_effect_replay"] = {
        "status": replay_receipt.get("status"),
        "receipt": str(replay_receipt_path),
        "event_count": replay_receipt.get("event_count"),
        "projection_digest": replay_receipt.get("projection_digest"),
        "external_effects": replay_receipt.get("external_effects"),
    }
    if promoted_stage0 and replay_receipt.get("status") != "PASS":
        _fail(
            ContractError(
                "PROMOTED_STAGE0_ZERO_EFFECT_REPLAY_FAILED",
                f"Zero-effect replay failed: {replay_receipt}",
            )
        )

    report_acceptance_receipt = validate_report_acceptance(
        out,
        require_zero_effect_replay=True,
        require_stage_ledger=promoted_stage0,
    )
    report_acceptance_sha256 = sha256_json(report_acceptance_receipt)
    steps["report_acceptance"] = {
        "status": report_acceptance_receipt.get("status"),
        "receipt": str(report_acceptance_path),
        "sha256": report_acceptance_sha256,
        "external_effects": report_acceptance_receipt.get("external_effects"),
        "failure_count": len(report_acceptance_receipt.get("failures") or []),
    }
    if promoted_stage0 and report_acceptance_receipt.get("status") != "PASS":
        _fail(
            ContractError(
                "PROMOTED_STAGE0_REPORT_ACCEPTANCE_FAILED",
                f"Report acceptance failed: {report_acceptance_receipt}",
            )
        )

    steps["browser_control"] = browser_control_summary()

    nightly_receipt = {
        "status": "PASS",
        "schema": "monitor_opportunities.nightly_receipt.v1",
        "mode": publication_mode,
        "mocked": False,
        "live": True,
        "external_effects": False,
        "out": str(out),
        "publication": {
            "latest_promoted": promote_latest_on_success,
            "latest_path": str(out.parent / "latest") if promote_latest_on_success else None,
            "published_run": str(out) if promote_latest_on_success else None,
        },
        "artifacts": {
            "effect_policy": str(effect_policy_path),
            "run": str(run_receipt_path),
            "report": str(out / "report" / "report.json"),
            "digest": str(out / "morning-digest.json"),
            "memory": str(out / "memory-sync-receipt.json") if not skip_memory_sync else None,
            "buzz": str(out / "buzz-summary" / "buzz-summary-receipt.json") if not skip_buzz else None,
            "tau_semantic_prepare": str(out / "tau-semantic" / "tau-semantic-prepare-receipt.json")
            if semantic_prepare_receipt is not None
            else None,
            "semantic_addenda_index": str(out / "semantic-addenda" / "index.json")
            if semantic_installs
            else None,
            "receipt_consistency": str(consistency_path) if consistency_path.exists() else None,
            "zero_effect_replay": str(replay_receipt_path),
            "report_acceptance": str(report_acceptance_path),
            "stage_ledger": str(out / "stage-ledger.json")
            if (out / "stage-ledger.json").exists()
            else None,
        },
        "artifact_hashes": {
            "report_acceptance": report_acceptance_sha256,
            "stage_ledger": _json_hash_file(out / "stage-ledger.json"),
        },
        "receipt_consistency_status": consistency.get("status") if consistency else "MISSING",
        "report_acceptance_status": report_acceptance_receipt.get("status"),
        "steps": steps,
    }
    nightly_receipt_path = out / "nightly-receipt.json"
    write_json(nightly_receipt_path, nightly_receipt)
    if promote_latest_on_success:
        _promote_nightly_latest(out)
    typer.echo(json.dumps({**nightly_receipt, "receipt": str(nightly_receipt_path)}, indent=2, sort_keys=True))


@app.command("ats-inspect")
def ats_inspect(
    board: str = typer.Option(..., "--board", help="Greenhouse board slug, e.g. discord."),
    job_id: str = typer.Option(..., "--job-id", help="Greenhouse job id."),
    site_policy: Path = typer.Option(
        ...,
        "--site-policy",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Human site-policy receipt promoting ats_form_inspect:greenhouse:<board>.",
    ),
    out: Path = typer.Option(..., "--out", file_okay=False),
) -> None:
    """Read-only ATS form inspection; captures the form schema, writes nothing to the site."""
    _configure_logging()
    from .application_plan import ApplicationGateError, inspect_ats_form
    from .ats.greenhouse import GreenhouseFormError, fetch_greenhouse_form

    try:
        form = fetch_greenhouse_form(board, job_id)
        inspection = inspect_ats_form(form, read_json(site_policy))
    except GreenhouseFormError as exc:
        _fail(ContractError("ATS_INSPECT_FETCH_FAILED", str(exc)))
    except ApplicationGateError as exc:
        _fail(ContractError("ATS_INSPECT_POLICY_REJECTED", str(exc)))
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"ats-inspection-greenhouse-{board}-{job_id}.json"
    path.write_text(json.dumps(inspection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    typer.echo(json.dumps({"status": "PASS", "path": str(path), **inspection}, indent=2, sort_keys=True))


@app.command()
def schedule(
    cron: str = typer.Option("0 2 * * *", "--cron"),
    diagnostic: bool = typer.Option(
        True,
        "--diagnostic/--promoted-stage0",
        help="Register diagnostic mode or the gated Stage 0 publication mode.",
    ),
    claim_snapshot: Path | None = typer.Option(
        None,
        "--claim-snapshot",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Approved non-fixture claim export required by promoted Stage 0.",
    ),
) -> None:
    """Register the single full-run transaction with the scheduler and read it back."""
    _configure_logging()
    import os
    import shutil
    import subprocess

    repo_root = _canonical_repo_root()
    scheduler = repo_root / "skills" / "scheduler" / "run.sh"
    run_sh = repo_root / "skills" / "monitor-opportunities" / "run.sh"
    default_claim_snapshot = (
        repo_root
        / "skills"
        / "monitor-opportunities"
        / "local"
        / "nightly"
        / "authority"
        / "claim-snapshot.json"
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    ).stdout.strip()
    nightly_args = ["nightly"]
    nightly_args.extend(
        [
            "--expected-revision",
            revision,
            "--require-clean",
            "--skip-tracker",
            "--skip-ats-memory",
        ]
    )
    if diagnostic:
        nightly_args.extend(["--diagnostic", "--skip-buzz"])
        buzz_bin = None
        if claim_snapshot is None and default_claim_snapshot.is_file():
            claim_snapshot = default_claim_snapshot
    else:
        if claim_snapshot is None:
            if not default_claim_snapshot.is_file():
                _fail(
                    ContractError(
                        "PROMOTED_STAGE0_CLAIM_SNAPSHOT_REQUIRED",
                        "Pass --claim-snapshot with an approved non-fixture export",
                    )
                )
            claim_snapshot = default_claim_snapshot
        buzz_bin = shutil.which("buzz")
        if not buzz_bin:
            _fail(
                ContractError(
                    "PROMOTED_STAGE0_BUZZ_BIN_REQUIRED",
                    "Promoted Stage 0 requires buzz-cli on PATH before scheduler registration",
                )
            )
        nightly_args.append("--promoted-stage0")
        nightly_args.append("--tau-semantic-provider")
        nightly_args.extend(["--tau-semantic-handler", "gpt-5.5-high"])
    if claim_snapshot is not None:
        claim_snapshot = claim_snapshot.resolve()
    environment: dict[str, str] = {
        "MONITOR_TRACKER_ENABLED": "0",
        "MONITOR_ATS_MEMORY_ENABLED": "0",
        "MONITOR_RELATIONSHIP_SIGNALS_ENABLED": "1",
    }
    if buzz_bin:
        environment["BUZZ_BIN"] = str(buzz_bin)
    if claim_snapshot is not None:
        environment["MONITOR_CLAIM_SNAPSHOT_PATH"] = str(claim_snapshot)
    effect_policy = _scheduler_effect_policy(diagnostic=diagnostic)
    scheduler_intent = {
        "schema": "monitor_opportunities.scheduler_intent.v1",
        "mode": "DIAGNOSTIC" if diagnostic else "PROMOTED_STAGE_0",
        "diagnostic": diagnostic,
        "promoted_stage0": not diagnostic,
        "external_effects": False,
        "entrypoint": str(run_sh),
        "nightly_args": nightly_args,
        "environment": environment,
        "expected_revision": revision,
        "claim_snapshot": str(claim_snapshot) if claim_snapshot is not None else None,
        "effect_policy": effect_policy,
        "workdir": str(repo_root),
        "cron": cron,
    }
    command = _scheduler_command_from_intent(scheduler_intent)
    register = subprocess.run(
        [
            str(scheduler),
            "register",
            "--name",
            "monitor-opportunities-nightly",
            "--cron",
            cron,
            "--command",
            command,
            "--workdir",
            str(repo_root),
            "--description",
            "Nightly Stage 0 opportunity publication" if not diagnostic else "Nightly Stage 0 diagnostic report",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    listing = subprocess.run(
        [str(scheduler), "list", "--json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    jobs = json.loads(listing.stdout)
    job = jobs.get("monitor-opportunities-nightly")
    scheduler_data_dir = Path(
        os.environ.get("SCHEDULER_DATA_DIR", str(Path.home() / ".pi" / "scheduler"))
    )
    scheduler_equivalence_path = (
        scheduler_data_dir / "receipts" / "monitor-opportunities-nightly-equivalence.json"
    )
    scheduler_equivalence = _scheduler_equivalence_receipt(
        cron=cron,
        command=command,
        repo_root=repo_root,
        intent=scheduler_intent,
        readback=job or {},
    )
    write_json(scheduler_equivalence_path, scheduler_equivalence)
    if scheduler_equivalence["status"] != "PASS":
        _fail(
            ContractError(
                "SCHEDULER_EQUIVALENCE_FAILED",
                f"Registered job does not match intended Stage 0 command: {scheduler_equivalence}",
            )
        )
    schedule_receipt = {
        "status": "PASS",
        "schema": "monitor_opportunities.scheduler_receipt.v1",
        "mode": "DIAGNOSTIC" if diagnostic else "PROMOTED_STAGE_0",
        "external_effects": False,
        "name": "monitor-opportunities-nightly",
        "cron": cron,
        "command": command,
        "diagnostic": diagnostic,
        "promoted_stage0": not diagnostic,
        "expected_revision": revision,
        "claim_snapshot": str(claim_snapshot) if claim_snapshot is not None else None,
        "workdir": str(repo_root),
        "register_stdout": register.stdout,
        "readback": job,
        "effect_policy": effect_policy,
        "scheduler_intent": scheduler_intent,
        "scheduler_equivalence": scheduler_equivalence,
    }
    schedule_receipt["scheduler_equivalence_receipt"] = str(scheduler_equivalence_path)
    schedule_receipt_path = (
        scheduler_data_dir / "receipts" / "monitor-opportunities-nightly-receipt.json"
    )
    write_json(schedule_receipt_path, schedule_receipt)
    typer.echo(
        json.dumps(
            {**schedule_receipt, "receipt": str(schedule_receipt_path)},
            indent=2,
            sort_keys=True,
        )
    )


@app.command("scheduler-exec-check")
def scheduler_exec_check(
    schedule_receipt: Path | None = typer.Option(
        None,
        "--schedule-receipt",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Scheduler registration receipt to execute byte-for-byte from readback.",
    ),
    out: Path | None = typer.Option(None, "--out", dir_okay=False),
    require_promoted_stage0: bool = typer.Option(
        True,
        "--require-promoted-stage0/--allow-diagnostic",
        help="Require the registered readback to be the promoted 2am Stage 0 command.",
    ),
    timeout_seconds: int = typer.Option(7200, "--timeout-seconds", min=60),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Write a preflight receipt without executing the registered command.",
    ),
) -> None:
    """Execute the exact scheduler-readback command and bind its receipts."""
    _configure_logging()
    scheduler_data_dir = _scheduler_data_dir()
    if schedule_receipt is None:
        schedule_receipt = (
            scheduler_data_dir / "receipts" / "monitor-opportunities-nightly-receipt.json"
        )
    if out is None:
        out = (
            scheduler_data_dir
            / "receipts"
            / "monitor-opportunities-nightly-execution-equivalence.json"
        )
    try:
        receipt = _scheduler_execution_equivalence_receipt(
            schedule_receipt_path=schedule_receipt,
            out_path=out,
            require_promoted_stage0=require_promoted_stage0,
            timeout_seconds=timeout_seconds,
            execute=not dry_run,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        _fail(ContractError("SCHEDULER_EXEC_CHECK_FAILED", str(exc)))
    if receipt["status"] != "PASS":
        _fail(
            ContractError(
                "SCHEDULER_EXECUTION_EQUIVALENCE_FAILED",
                f"Scheduler execution-equivalence failed; receipt: {out}",
            )
        )
    typer.echo(json.dumps(receipt, indent=2, sort_keys=True))


def _not_implemented(command: str) -> None:
    typer.echo(
        json.dumps(
            {
                "status": "NOT_IMPLEMENTED",
                "command": command,
                "stage": STAGE,
                "external_effects": False,
            },
            sort_keys=True,
        ),
        err=True,
    )
    raise typer.Exit(code=3)


def _register_not_implemented(command_name: str) -> None:
    def command(ctx: typer.Context) -> None:
        del ctx
        _not_implemented(command_name)

    command.__name__ = command_name.replace("-", "_")
    app.command(
        name=command_name,
        help="Not implemented; fails closed.",
        context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    )(command)


for _command_name in NOT_IMPLEMENTED:
    _register_not_implemented(_command_name)


@app.command("morning-interview")
def morning_interview_cmd(
    run: Path | None = typer.Option(None, "--run", help="Run directory; defaults to local/nightly/latest."),
    mode: str = typer.Option("auto", help="Interview surface: auto, html, or tui."),
    questions_only: bool = typer.Option(False, "--questions-only", help="Write questions.json and exit."),
) -> None:
    """Review the morning digest: dispositions feed ranking, identities become contacts."""

    from .morning_interview import build_questions, run_interview
    from .util import write_json

    skill_dir = Path(__file__).resolve().parents[2]
    run_dir = (run or skill_dir / "local" / "nightly" / "latest").resolve()
    if questions_only:
        questions = build_questions(run_dir)
        out = run_dir / "morning-interview-questions.json"
        write_json(out, questions)
        typer.echo(json.dumps({"questions": len(questions["questions"]), "path": str(out)}))
        return
    typer.echo(json.dumps(run_interview(run_dir, mode=mode), indent=2, sort_keys=True))


if __name__ == "__main__":  # pragma: no cover
    app()
