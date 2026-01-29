"""
Job registry - storage and management of scheduled jobs.

Handles CRUD operations for jobs stored in JSON format.
"""
import json
import time
from pathlib import Path
from typing import Any, Optional

from config import JOBS_FILE
from utils import ensure_dirs, HAS_YAML

# Lazy import yaml only when needed
if HAS_YAML:
    import yaml


def load_jobs() -> dict[str, Any]:
    """
    Load jobs from JSON file.

    Returns:
        Dictionary of jobs keyed by job name.
    """
    if JOBS_FILE.exists():
        return json.loads(JOBS_FILE.read_text())
    return {}


def save_jobs(jobs: dict[str, Any]) -> None:
    """
    Save jobs to JSON file.

    Args:
        jobs: Dictionary of jobs to save.
    """
    ensure_dirs()
    JOBS_FILE.write_text(json.dumps(jobs, indent=2))


def get_job(name: str) -> Optional[dict[str, Any]]:
    """
    Get a specific job by name.

    Args:
        name: Job name to retrieve.

    Returns:
        Job dictionary if found, None otherwise.
    """
    jobs = load_jobs()
    return jobs.get(name)


def register_job(
    name: str,
    command: str,
    cron: Optional[str] = None,
    interval: Optional[str] = None,
    workdir: Optional[str] = None,
    description: Optional[str] = None,
    enabled: bool = True,
    timeout: Optional[int] = None,
) -> dict[str, Any]:
    """
    Register a new job.

    Args:
        name: Unique job name.
        command: Shell command to execute.
        cron: Cron expression for scheduling.
        interval: Interval string (e.g., '1h', '30m').
        workdir: Working directory for command execution.
        description: Human-readable description.
        enabled: Whether the job is enabled.
        timeout: Command timeout in seconds.

    Returns:
        The created job dictionary.

    Raises:
        ValueError: If neither cron nor interval is specified.
    """
    if not cron and not interval:
        raise ValueError("Must specify either cron or interval")

    jobs = load_jobs()

    job: dict[str, Any] = {
        "name": name,
        "command": command,
        "enabled": enabled,
        "created_at": int(time.time()),
    }

    if cron:
        job["cron"] = cron
    if interval:
        job["interval"] = interval
    if workdir:
        job["workdir"] = workdir
    if description:
        job["description"] = description
    if timeout:
        job["timeout"] = timeout

    jobs[name] = job
    save_jobs(jobs)

    return job


def unregister_job(name: str) -> bool:
    """
    Remove a job from the registry.

    Args:
        name: Job name to remove.

    Returns:
        True if job was removed, False if not found.
    """
    jobs = load_jobs()
    if name not in jobs:
        return False

    del jobs[name]
    save_jobs(jobs)
    return True


def set_job_enabled(name: str, enabled: bool) -> bool:
    """
    Enable or disable a job.

    Args:
        name: Job name.
        enabled: New enabled state.

    Returns:
        True if job was updated, False if not found.
    """
    jobs = load_jobs()
    if name not in jobs:
        return False

    jobs[name]["enabled"] = enabled
    save_jobs(jobs)
    return True


def update_job_run_status(
    name: str,
    status: str,
    duration: Optional[float] = None,
) -> bool:
    """
    Update job run status after execution.

    Args:
        name: Job name.
        status: Execution status ('success', 'failed', 'timeout').
        duration: Execution duration in seconds.

    Returns:
        True if job was updated, False if not found.
    """
    jobs = load_jobs()
    if name not in jobs:
        return False

    jobs[name]["last_run"] = int(time.time())
    jobs[name]["last_status"] = status
    if duration is not None:
        jobs[name]["last_duration"] = duration

    save_jobs(jobs)
    return True


def load_services_yaml(yaml_path: Path) -> dict[str, Any]:
    """
    Load services configuration from YAML file.

    Args:
        yaml_path: Path to the YAML configuration file.

    Returns:
        Parsed configuration dictionary.

    Raises:
        RuntimeError: If PyYAML is not installed.
        FileNotFoundError: If the YAML file doesn't exist.
    """
    if not HAS_YAML:
        raise RuntimeError("PyYAML not installed. Run: pip install pyyaml")

    if not yaml_path.exists():
        raise FileNotFoundError(f"Services file not found: {yaml_path}")

    with open(yaml_path) as f:
        config = yaml.safe_load(f)

    return config


def import_from_yaml(
    yaml_path: Path,
    include_disabled: bool = False,
) -> tuple[int, int]:
    """
    Import jobs from a services.yaml file.

    Args:
        yaml_path: Path to the YAML configuration file.
        include_disabled: Whether to import disabled jobs.

    Returns:
        Tuple of (loaded_count, skipped_count).
    """
    from cron_parser import is_cron_expression

    config = load_services_yaml(yaml_path)
    workdir = config.get("workdir", str(yaml_path.parent))
    jobs = load_jobs()
    loaded = 0
    skipped = 0

    # Process scheduled jobs
    scheduled = config.get("scheduled", {})
    for name, job_config in scheduled.items():
        if not job_config.get("enabled", True) and not include_disabled:
            skipped += 1
            continue

        job: dict[str, Any] = {
            "name": name,
            "command": job_config["command"],
            "workdir": job_config.get("workdir", workdir),
            "enabled": job_config.get("enabled", True),
            "description": job_config.get("description", ""),
            "created_at": int(time.time()),
            "source": str(yaml_path),
        }

        # Schedule (cron or interval)
        if "schedule" in job_config:
            schedule = job_config["schedule"]
            if is_cron_expression(schedule):
                job["cron"] = schedule
            else:
                job["interval"] = schedule

        if "timeout" in job_config:
            job["timeout"] = job_config["timeout"]
        if "env" in job_config:
            job["env"] = job_config["env"]
        if "depends_on" in job_config:
            job["depends_on"] = job_config["depends_on"]

        jobs[name] = job
        loaded += 1

    # Process hook-triggered jobs (store but don't schedule)
    hooks = config.get("hooks", {})
    for name, hook_config in hooks.items():
        if not hook_config.get("enabled", True) and not include_disabled:
            skipped += 1
            continue

        job = {
            "name": name,
            "command": hook_config["command"],
            "workdir": hook_config.get("workdir", workdir),
            "enabled": hook_config.get("enabled", True),
            "description": hook_config.get("description", ""),
            "trigger": hook_config.get("trigger", "on-demand"),
            "created_at": int(time.time()),
            "source": str(yaml_path),
            "is_hook": True,
        }

        if "timeout" in hook_config:
            job["timeout"] = hook_config["timeout"]
        if "depends_on" in hook_config:
            job["depends_on"] = hook_config["depends_on"]

        jobs[name] = job
        loaded += 1

    save_jobs(jobs)
    return loaded, skipped
