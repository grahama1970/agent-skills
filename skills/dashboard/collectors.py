"""Dashboard data collectors.

Each collector is independent, returns a plain dict, handles its own errors.
collect_all() runs them in parallel via ThreadPoolExecutor.

Inputs: file paths under ~/.pi/, Unix socket, and subprocess calls to sibling skills.
Outputs: plain dicts with collector-specific keys; errors keyed as {"error": "reason"}.
Failure modes: each collector wraps in try/except — never crashes the aggregator.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import find_dotenv, load_dotenv
from loguru import logger

load_dotenv(find_dotenv(usecwd=True), override=False)

PI_DIR = Path.home() / ".pi"
SKILLS_DIR = Path(__file__).resolve().parent.parent


def collect_daemon_health() -> dict[str, Any]:
    """Query state-daemon /health/all via Unix socket."""
    import httpx

    uid = os.getuid()
    socket_path = f"/run/user/{uid}/embry/state.sock"
    if not os.path.exists(socket_path):
        return {"error": "state.sock not found"}

    try:
        transport = httpx.HTTPTransport(uds=socket_path)
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=5.0) as client:
            resp = client.get("/health/all")
            return resp.json()
    except Exception as exc:
        logger.warning("Collector error: {}", exc)
        return {"error": str(exc)}


def collect_llm_metrics(hours: int = 24) -> dict[str, Any]:
    """Parse ~/.pi/assistant/metrics.jsonl for recent LLM call stats."""
    metrics_path = PI_DIR / "assistant" / "metrics.jsonl"
    if not metrics_path.exists():
        return {"error": "metrics.jsonl not found"}

    try:
        cutoff = time.time() - (hours * 3600)
        calls = []
        for line in metrics_path.read_text().strip().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = entry.get("timestamp", entry.get("ts", 0))
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts).timestamp()
                except ValueError:
                    continue
            if ts >= cutoff:
                calls.append(entry)

        if not calls:
            return {"calls_today": 0, "avg_latency_ms": 0, "cache_hit_rate": 0, "tier_distribution": {}, "by_task": {}}

        latencies = [c.get("latency_ms", c.get("duration_ms", 0)) for c in calls if c.get("latency_ms") or c.get("duration_ms")]
        cache_hits = sum(1 for c in calls if c.get("cache_hit", False))

        tier_counts: dict[str, int] = {}
        task_counts: dict[str, int] = {}
        for c in calls:
            tier = c.get("tier", c.get("model_tier", "unknown"))
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
            task = c.get("task", c.get("skill", "unknown"))
            task_counts[task] = task_counts.get(task, 0) + 1

        return {
            "calls_today": len(calls),
            "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
            "cache_hit_rate": round(cache_hits / len(calls), 2) if calls else 0,
            "tier_distribution": tier_counts,
            "by_task": task_counts,
        }
    except Exception as exc:
        logger.warning("Collector error: {}", exc)
        return {"error": str(exc)}


def collect_shadow_agreement(n: int = 200) -> dict[str, Any]:
    """Parse last N entries from ~/.pi/assistant/shadow.jsonl."""
    shadow_path = PI_DIR / "assistant" / "shadow.jsonl"
    if not shadow_path.exists():
        return {"error": "shadow.jsonl not found"}

    try:
        lines = shadow_path.read_text().strip().splitlines()
        recent = lines[-n:] if len(lines) > n else lines

        entries = []
        for line in recent:
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        if not entries:
            return {"total": 0, "agreement_rate": 0, "by_task": {}}

        agreed = sum(1 for e in entries if e.get("agreed", e.get("agreement", False)))
        task_agreement: dict[str, dict[str, int]] = {}
        for e in entries:
            task = e.get("task", e.get("skill", "unknown"))
            if task not in task_agreement:
                task_agreement[task] = {"total": 0, "agreed": 0}
            task_agreement[task]["total"] += 1
            if e.get("agreed", e.get("agreement", False)):
                task_agreement[task]["agreed"] += 1

        return {
            "total": len(entries),
            "agreement_rate": round(agreed / len(entries), 2) if entries else 0,
            "by_task": task_agreement,
        }
    except Exception as exc:
        logger.warning("Collector error: {}", exc)
        return {"error": str(exc)}


def collect_cascade_state() -> dict[str, Any]:
    """Read skills/assistant/model_registry.json for cascade model counts."""
    registry_path = SKILLS_DIR / "assistant" / "model_registry.json"
    if not registry_path.exists():
        return {"error": "model_registry.json not found"}

    try:
        data = json.loads(registry_path.read_text())

        # Registry format: {validators: [...], classifiers: [...], regressors: [...]}
        # or flat list, or {models: [...]}
        if isinstance(data, dict) and any(k in data for k in ("validators", "classifiers", "regressors")):
            v_map = data.get("validators", {})
            c_map = data.get("classifiers", {})
            r_map = data.get("regressors", {})
            # Values may be dicts (keyed by name) or lists
            all_models = list((v_map if isinstance(v_map, dict) else {}).values()) + \
                         list((c_map if isinstance(c_map, dict) else {}).values()) + \
                         list((r_map if isinstance(r_map, dict) else {}).values())
            shadow_mode = sum(
                1 for m in all_models
                if isinstance(m, dict) and m.get("shadow_mode", False)
            )
            return {
                "validators": len(v_map),
                "classifiers": len(c_map),
                "regressors": len(r_map),
                "shadow_mode_count": shadow_mode,
                "total_models": len(v_map) + len(c_map) + len(r_map),
            }

        # Fallback: flat list or {models: [...]}
        models = data if isinstance(data, list) else data.get("models", [])
        validators = classifiers = regressors = shadow_mode = 0
        for m in models:
            if not isinstance(m, dict):
                continue
            role = m.get("role", m.get("type", "")).lower()
            if "valid" in role:
                validators += 1
            elif "class" in role:
                classifiers += 1
            elif "regress" in role:
                regressors += 1
            if m.get("shadow_mode", False):
                shadow_mode += 1

        return {
            "validators": validators,
            "classifiers": classifiers,
            "regressors": regressors,
            "shadow_mode_count": shadow_mode,
            "total_models": len(models),
        }
    except Exception as exc:
        logger.warning("Collector error: {}", exc)
        return {"error": str(exc)}


def collect_skill_health() -> dict[str, Any]:
    """Read ~/.pi/monitor-skill-health/latest_summary.json."""
    summary_path = PI_DIR / "monitor-skill-health" / "latest_summary.json"
    if not summary_path.exists():
        return {"error": "latest_summary.json not found"}

    try:
        data = json.loads(summary_path.read_text())
        return {
            "overall_status": data.get("overall_status", "unknown"),
            "total_skills": data.get("total_skills", 0),
            "status_counts": data.get("status_counts", {}),
            "top_issues": data.get("top_issues", [])[:5],
        }
    except Exception as exc:
        logger.warning("Collector error: {}", exc)
        return {"error": str(exc)}


_STALE_THRESHOLD_SECONDS = 24 * 3600  # 24 hours


def _is_task_active(state: dict[str, Any], state_file_mtime: float = 0) -> bool:
    """Check if task is genuinely active: status, progress, AND freshness.

    Tasks whose state file hasn't been updated in >24h are considered stale,
    even if completed < total.
    """
    # Staleness check: if state file is older than threshold, task is dead
    if state_file_mtime and (time.time() - state_file_mtime) > _STALE_THRESHOLD_SECONDS:
        return False

    stats = state.get("stats", {}) or {}
    status_val = str(stats.get("status", "") or "").lower()
    if status_val in {"running", "restarting", "active", "in_progress", "starting"}:
        return True
    total = state.get("total")
    completed = state.get("completed")
    if isinstance(total, (int, float)) and total > 0 and isinstance(completed, (int, float)):
        if completed < total:
            return True
    return False


def collect_active_tasks() -> dict[str, Any]:
    """Read ~/.pi/task-monitor/registry.json for active tasks (reads state files)."""
    registry_path = PI_DIR / "task-monitor" / "registry.json"
    if not registry_path.exists():
        return {"active": 0, "tasks": []}

    try:
        data = json.loads(registry_path.read_text())
        # Registry is {tasks: {name: {state_file, total, ...}, ...}}
        tasks_map = data.get("tasks", data) if isinstance(data, dict) else {}
        if not isinstance(tasks_map, dict):
            return {"active": 0, "tasks": []}

        active_tasks = []
        for name, cfg in tasks_map.items():
            if not isinstance(cfg, dict):
                continue
            # Skip completed tasks (have completed_at timestamp)
            if cfg.get("completed_at"):
                continue
            # Read external state file for progress
            state_file = cfg.get("state_file")
            if not state_file or not Path(state_file).exists():
                continue
            state_path = Path(state_file)
            try:
                state = json.loads(state_path.read_text())
                mtime = state_path.stat().st_mtime
            except (json.JSONDecodeError, OSError):
                continue
            if not _is_task_active(state, state_file_mtime=mtime):
                continue
            completed = state.get("completed", 0) or 0
            total = state.get("total", cfg.get("total", 0)) or 0
            pct = round(completed / total * 100, 1) if total else 0
            elapsed = state.get("elapsed_seconds", 0)
            # Truncate current_item — some tasks dump entire markdown here
            raw_item = state.get("current_item", "")
            current_item = raw_item.split("\n")[0][:60] if raw_item else ""
            description = state.get("description", cfg.get("description", ""))
            active_tasks.append({
                "name": name,
                "completed": completed,
                "total": total,
                "pct": pct,
                "elapsed_seconds": elapsed,
                "current_item": current_item,
                "description": description,
            })

        return {"active": len(active_tasks), "tasks": active_tasks}
    except Exception as exc:
        logger.warning("Collector error: {}", exc)
        return {"error": str(exc)}


def collect_backend_health() -> dict[str, Any]:
    """Ping claude/codex/gemini CLIs for availability."""
    backends: dict[str, Any] = {}
    checks = {
        "claude": ["claude", "--version"],
        "codex": ["codex", "--version"],
        "gemini": ["gemini", "--version"],
    }
    for name, cmd in checks.items():
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            backends[name] = {
                "available": proc.returncode == 0,
                "version": proc.stdout.strip().split("\n")[0][:40] if proc.returncode == 0 else None,
            }
        except FileNotFoundError:
            backends[name] = {"available": False, "version": None}
        except subprocess.TimeoutExpired:
            backends[name] = {"available": False, "version": "timeout"}
        except Exception:
            backends[name] = {"available": False, "version": None}

    available = sum(1 for b in backends.values() if b["available"])
    return {"backends": backends, "available": available, "total": len(backends)}


def collect_git_status() -> dict[str, Any]:
    """Get current branch, dirty files count, and last commit info."""
    result: dict[str, Any] = {}
    try:
        # Current branch
        proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        result["branch"] = proc.stdout.strip() if proc.returncode == 0 else "unknown"

        # Dirty files count (fast — no -uall)
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if proc.returncode == 0:
            lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
            result["dirty_files"] = len(lines)
        else:
            result["dirty_files"] = 0

        # Last commit age
        proc = subprocess.run(
            ["git", "log", "-1", "--format=%ct %s"],
            capture_output=True, text=True, timeout=5,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if proc.returncode == 0 and proc.stdout.strip():
            parts = proc.stdout.strip().split(" ", 1)
            commit_ts = int(parts[0])
            age_seconds = time.time() - commit_ts
            result["last_commit_age_seconds"] = age_seconds
            result["last_commit_subject"] = parts[1][:60] if len(parts) > 1 else ""
        else:
            result["last_commit_age_seconds"] = 0
            result["last_commit_subject"] = ""

    except Exception as exc:
        logger.warning("Collector error: {}", exc)
        return {"error": str(exc)}

    return result


def collect_chutes_quota() -> dict[str, Any]:
    """Run ops-chutes usage --json for quota data, plus slot status."""
    ops_chutes_run = SKILLS_DIR / "ops-chutes" / "run.sh"
    if not ops_chutes_run.exists():
        return {"error": "ops-chutes/run.sh not found"}

    result: dict[str, Any] = {}

    # Get quota via subprocess
    try:
        proc = subprocess.run(
            [str(ops_chutes_run), "usage", "--json"],
            capture_output=True, text=True, timeout=15,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if proc.returncode == 0 and proc.stdout.strip():
            result = json.loads(proc.stdout.strip(),
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
    except Exception as exc:
        result["error"] = f"quota: {exc}"

    # Get slot status from throttle
    try:
        from throttle import ChutesSemaphore
        result["slots_in_use"] = ChutesSemaphore.slots_in_use()
    except Exception:
        # Throttle not available — try reading slot dir directly
        slot_dir = Path.home() / ".pi" / "ops-chutes" / "semaphore"
        if slot_dir.exists():
            import fcntl
            in_use = 0
            for i in range(5):
                slot_file = slot_dir / f"slot_{i}"
                if slot_file.exists():
                    try:
                        fd = os.open(str(slot_file), os.O_RDONLY)
                        try:
                            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            fcntl.flock(fd, fcntl.LOCK_UN)
                        except OSError:
                            in_use += 1
                        finally:
                            os.close(fd)
                    except OSError:
                        pass
            result["slots_in_use"] = in_use

    return result



def collect_monitor_reports() -> dict[str, Any]:
    """Aggregate all monitor-* skill reports from ~/.pi/monitor-*/report.json.

    Each monitor writes its latest probe results + figure_data to a standard
    location.  This collector reads them all and returns a unified view.
    """
    monitors: dict[str, Any] = {}
    monitor_dir = Path.home() / ".pi"

    for report_file in sorted(monitor_dir.glob("monitor-*/report.json")):
        monitor_name = report_file.parent.name  # e.g. "monitor-workstation"
        try:
            data = json.loads(report_file.read_text())
            monitors[monitor_name] = {
                "health": data.get("health", "unknown"),
                "timestamp": data.get("timestamp", ""),
                "summary": data.get("summary", {}),
                "total_probes": data.get("total", len(data.get("probes", []))),
                "figure_data": data.get("figure_data", {}),
            }
        except (json.JSONDecodeError, OSError) as exc:
            monitors[monitor_name] = {"error": str(exc)}

    # Compute aggregate health
    healths = [m.get("health") for m in monitors.values() if isinstance(m, dict) and "health" in m]
    if any(h == "critical" for h in healths):
        overall = "critical"
    elif any(h == "warning" for h in healths):
        overall = "warning"
    elif healths:
        overall = "healthy"
    else:
        overall = "no_data"

    # Merge all figure_data.bar.metrics into one flat dict for dashboard charting
    merged_metrics: dict[str, float] = {}
    for name, m in monitors.items():
        if not isinstance(m, dict):
            continue
        bar_metrics = m.get("figure_data", {}).get("bar", {}).get("metrics", {})
        prefix = name.replace("monitor-", "")  # "workstation", "memory", etc.
        for key, val in bar_metrics.items():
            if isinstance(val, (int, float)):
                merged_metrics[f"{prefix}/{key}"] = val

    return {
        "overall_health": overall,
        "monitors_reporting": len([m for m in monitors.values() if "error" not in m]),
        "monitors_total": len(monitors),
        "monitors": monitors,
        "figure_data": {
            "bar": {"metrics": merged_metrics},
        },
    }


def collect_review_pdf() -> dict[str, Any]:
    """Parse shadow JSONL files for today's PDF review activity."""
    shadow_dir = PI_DIR / "skills" / "learn-datalake" / "state" / "shadow"
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        approvals = 0
        flags = 0
        corrections = 0
        latest_run = ""

        corrections_path = shadow_dir / "corrections.jsonl"
        if corrections_path.exists():
            for line in corrections_path.read_text().strip().splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = entry.get("timestamp", entry.get("ts", ""))
                if isinstance(ts, str) and ts.startswith(today):
                    corrections += 1
                    if ts > latest_run:
                        latest_run = ts

        reviews_path = shadow_dir / "reviews.jsonl"
        if reviews_path.exists():
            for line in reviews_path.read_text().strip().splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = entry.get("timestamp", entry.get("ts", ""))
                if isinstance(ts, str) and ts.startswith(today):
                    verdict = entry.get("verdict", entry.get("action", "")).lower()
                    if verdict in ("approve", "approved", "pass"):
                        approvals += 1
                    elif verdict in ("flag", "flagged", "fail", "warn"):
                        flags += 1
                    if ts > latest_run:
                        latest_run = ts

        return {
            "approvals_today": approvals,
            "flags_today": flags,
            "corrections_today": corrections,
            "latest_run": latest_run,
        }
    except Exception as exc:
        logger.warning("Collector error: {}", exc)
        return {"error": str(exc)}


def collect_quarantine() -> dict[str, Any]:
    """Read deferred_review.jsonl and quarantine.jsonl for quarantine status."""
    state_dir = PI_DIR / "skills" / "learn-datalake" / "state"
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        pending = 0
        resolved_today = 0
        by_reason: dict[str, int] = {
            "low_confidence": 0,
            "extraction_error": 0,
            "novel_layout": 0,
            "timeout": 0,
        }
        total_processed = 0

        deferred_path = state_dir / "deferred_review.jsonl"
        if deferred_path.exists():
            for line in deferred_path.read_text().strip().splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                total_processed += 1
                resolved = entry.get("resolved", entry.get("status", "")) in ("resolved", "done", True)
                if not resolved:
                    pending += 1
                    reason = entry.get("reason", "unknown")
                    if reason in by_reason:
                        by_reason[reason] += 1
                else:
                    ts = entry.get("resolved_at", entry.get("timestamp", entry.get("ts", "")))
                    if isinstance(ts, str) and ts.startswith(today):
                        resolved_today += 1

        quarantine_path = state_dir / "shadow" / "quarantine.jsonl"
        if quarantine_path.exists():
            for line in quarantine_path.read_text().strip().splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = entry.get("timestamp", entry.get("ts", ""))
                if isinstance(ts, str) and ts.startswith(today):
                    resolved_today += 1

        return {
            "pending": pending,
            "resolved_today": resolved_today,
            "by_reason": by_reason,
            "total_processed": total_processed,
        }
    except Exception as exc:
        logger.warning("Collector error: {}", exc)
        return {"error": str(exc)}


def collect_subagent_state() -> dict[str, Any]:
    """Read create-subagent task state for backend breakdown."""
    state_file = PI_DIR / "task-monitor" / "create-subagent_task_state.json"
    if not state_file.exists():
        return {"backends": {}, "running": 0, "completed": 0, "errored": 0}

    try:
        data = json.loads(state_file.read_text())
        stats = data.get("stats", {})
        return {
            "backends": stats.get("backends", {}),
            "running": stats.get("running", 0),
            "completed": stats.get("completed", 0),
            "errored": stats.get("errored", 0),
            "total": stats.get("total", 0),
            "status": stats.get("status", "idle"),
        }
    except Exception as exc:
        logger.warning("Collector error: {}", exc)
        return {"error": str(exc)}


def collect_cost_data() -> dict[str, Any]:
    """Read ops-costs cached results from ~/.pi/costs/last_run.json.

    The cache is written by ops-costs runs (nightly scheduler or manual).
    Reading the file is instant vs spawning ops-costs which takes 38s+
    due to ccusage scanning 29GB of conversation logs.
    """
    cache_path = Path.home() / ".pi" / "costs" / "last_run.json"
    if not cache_path.exists():
        return {"error": "no cost cache (~/.pi/costs/last_run.json)"}

    try:
        raw = json.loads(cache_path.read_text())
        age_s = time.time() - cache_path.stat().st_mtime
        stale = age_s > 24 * 3600

        # Build dashboard-friendly summary from cached data
        providers = raw.get("providers", {})
        by_provider: dict[str, float] = {}
        for name, info in providers.items():
            if isinstance(info, dict):
                by_provider[name] = info.get("total_usd", 0.0)

        total = raw.get("total_usd", sum(by_provider.values()))
        result: dict[str, Any] = {
            "today": total,
            "mtd": total,
            "by_provider": by_provider,
            "period": raw.get("period", ""),
            "cache_age_seconds": int(age_s),
        }
        if stale:
            result["stale"] = True
        return result
    except Exception as exc:
        logger.warning("Cost cache read failed: {}", exc)
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

_COLLECTORS = {
    "daemon_health": collect_daemon_health,
    "llm_metrics": collect_llm_metrics,
    "shadow_agreement": collect_shadow_agreement,
    "cascade_state": collect_cascade_state,
    "skill_health": collect_skill_health,
    "active_tasks": collect_active_tasks,
    "chutes_quota": collect_chutes_quota,
    "monitor_reports": collect_monitor_reports,
    "subagent_state": collect_subagent_state,
    "cost_data": collect_cost_data,
    "backend_health": collect_backend_health,
    "git_status": collect_git_status,
    "review_pdf": collect_review_pdf,
    "quarantine": collect_quarantine,
}


def collect_all(max_workers: int = 6) -> dict[str, Any]:
    """Run all collectors in parallel, return combined dict."""
    results: dict[str, Any] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fn): name for name, fn in _COLLECTORS.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as exc:
                results[name] = {"error": str(exc)}

    results["collected_at"] = datetime.now(timezone.utc).isoformat()
    return results
