"""Extract skill chains from git commits correlated with transcript skill mentions.

Three extraction methods (highest to lowest confidence):
1. Git trailer: `Skills: memory, checkpoint, taxonomy` in commit message
2. Commit-transcript correlation: ±15min window matching commit to transcript skill mentions
3. Commit message regex: skill names mentioned in commit message text

Usage:
    # Extract from a single repo (new commits since last run)
    python -m src.commit_chain_extractor extract --repo /path/to/repo

    # Extract from all registered projects
    python -m src.commit_chain_extractor extract-all

    # Extract from all, only new commits since last run
    python -m src.commit_chain_extractor extract-all --since-last

    # Dry run
    python -m src.commit_chain_extractor extract-all --dry-run
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

# Configure loguru
logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")

app = typer.Typer(name="commit-chain-extractor", no_args_is_help=True)

# Known skill names — canonical set
SKILL_RE = re.compile(r"(?:\.agents|\.pi)/skills/([a-z][a-z0-9-]+)/")
TRAILER_RE = re.compile(r"^Skills:\s*(.+)$", re.MULTILINE)
GRADE_RE = re.compile(r"^Grade:\s*(.+)$", re.MULTILINE)

# State file for incremental extraction
STATE_FILE = Path(__file__).parent.parent / "data" / "extractor_state.json"


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _git_log(repo: str, since: Optional[str] = None, limit: int = 5000) -> list[dict]:
    """Get git commits with hash, timestamp, message, files changed."""
    cmd = [
        "git", "-C", repo, "log",
        f"--max-count={limit}",
        "--format=%H|||%aI|||%s|||%b|||%D",
        "--name-only",
    ]
    if since:
        cmd.append(f"--since={since}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    commits = []
    current = None
    for line in result.stdout.split("\n"):
        if "|||" in line:
            if current:
                commits.append(current)
            parts = line.split("|||", 4)
            if len(parts) < 3:
                continue
            current = {
                "hash": parts[0],
                "timestamp": parts[1],
                "subject": parts[2],
                "body": parts[3] if len(parts) > 3 else "",
                "refs": parts[4] if len(parts) > 4 else "",
                "files": [],
            }
        elif current and line.strip():
            current["files"].append(line.strip())

    if current:
        commits.append(current)
    return commits


def _extract_skills_from_trailer(commit: dict) -> tuple[list[str], str, str]:
    """Extract skills from git trailer. Returns (skills, grade, source)."""
    full_msg = f"{commit['subject']}\n{commit['body']}"
    trailer_match = TRAILER_RE.search(full_msg)
    if not trailer_match:
        return [], "", ""
    skills = [s.strip() for s in trailer_match.group(1).split(",") if s.strip()]
    grade_match = GRADE_RE.search(full_msg)
    grade = grade_match.group(1).strip() if grade_match else ""
    return skills, grade, "commit-trailer"


def _extract_skills_from_message(commit: dict) -> tuple[list[str], str]:
    """Extract skill names from commit message text. Only returns known skill names."""
    full_msg = f"{commit['subject']}\n{commit['body']}"
    known = _get_known_skills()
    # Look for skill path patterns
    path_skills = [s for s in SKILL_RE.findall(full_msg) if s in known]
    # Look for /skill-name patterns (slash commands)
    slash_skills = [s for s in re.findall(r"/([a-z][a-z0-9-]{2,30})(?:\s|,|$)", full_msg) if s in known]
    # Deduplicate preserving order
    seen: set[str] = set()
    skills = []
    for s in path_skills + slash_skills:
        if s not in seen:
            seen.add(s)
            skills.append(s)
    return skills, "commit-message"


def _load_known_skills() -> set[str]:
    """Load the set of known skill names from disk."""
    skill_dirs = [
        Path.home() / "workspace/experiments/memory/.pi/skills",
        Path.home() / "workspace/experiments/memory/.agents/skills",
    ]
    names: set[str] = set()
    for d in skill_dirs:
        if d.exists():
            for child in d.iterdir():
                if child.is_dir() and (child / "SKILL.md").exists():
                    names.add(child.name)
    return names


_KNOWN_SKILLS: set[str] | None = None


def _get_known_skills() -> set[str]:
    global _KNOWN_SKILLS
    if _KNOWN_SKILLS is None:
        _KNOWN_SKILLS = _load_known_skills()
    return _KNOWN_SKILLS


def _extract_skills_from_files(commit: dict) -> list[str]:
    """Infer skills from files changed. Only returns known skill names."""
    skills = set()
    known = _get_known_skills()
    for f in commit.get("files", []):
        m = SKILL_RE.search(f)
        if m and m.group(1) in known:
            skills.add(m.group(1))
    return sorted(skills)


def _find_transcripts(repo: str, commit_time: str, window_minutes: int = 15) -> list[str]:
    """Find transcript files that overlap with commit timestamp ±window."""
    # Look for Pi/Claude JSONL transcripts
    transcript_dirs = [
        Path(repo) / ".pi" / "sessions",
        Path(repo) / ".claude" / "sessions",
        Path.home() / ".pi" / "sessions",
        Path.home() / ".claude" / "sessions",
    ]

    try:
        commit_dt = datetime.fromisoformat(commit_time).astimezone(timezone.utc)
    except ValueError:
        return []

    window = timedelta(minutes=window_minutes)
    matching = []

    for d in transcript_dirs:
        if not d.exists():
            continue
        for f in d.glob("*.jsonl"):
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                if abs(mtime - commit_dt) < window:
                    matching.append(str(f))
            except OSError:
                continue

    return matching


def _extract_skills_from_transcript(transcript_path: str) -> list[str]:
    """Extract skill names from a JSONL transcript file."""
    skills = set()
    try:
        with open(transcript_path) as f:
            text = f.read()
        # Brute-force regex against full transcript text
        for match in SKILL_RE.finditer(text):
            skills.add(match.group(1))
    except (OSError, UnicodeDecodeError):
        pass
    return sorted(skills)


def _store_chain(
    skills: list[str],
    commit: dict,
    source: str,
    repo_name: str,
    grade: str = "",
    dry_run: bool = False,
) -> bool:
    """Store chain via learn_chain()."""
    if len(skills) < 2:
        return False

    if dry_run:
        logger.info(f"[DRY] {repo_name} {commit['hash'][:7]} {source}: {' → '.join(skills)}")
        return True

    try:
        # Import here to avoid top-level dependency on graph_memory
        sys.path.insert(0, str(Path(__file__).parents[4] / "src"))
        from graph_memory.lessons.skill_chains import learn_chain

        learn_chain(
            skills=skills,
            task_description=commit["subject"],
            source=source,
            success=True,
            problem=commit["subject"],
            solution=commit.get("body", "")[:500] or commit["subject"],
            grade=grade or "clean",
            scope=repo_name,
            commit=commit["hash"],
            files_changed=commit.get("files", [])[:20],
        )
        return True
    except Exception as exc:
        logger.warning(f"Failed to store chain: {exc}")
        return False


def extract_repo(
    repo: str,
    since: Optional[str] = None,
    dry_run: bool = False,
    limit: int = 5000,
) -> dict:
    """Extract skill chains from a single repo's commits."""
    repo_name = Path(repo).name
    commits = _git_log(repo, since=since, limit=limit)
    logger.info(f"{repo_name}: {len(commits)} commits")

    stats = {"repo": repo_name, "commits": len(commits), "chains": 0, "by_source": {}}

    seen_hashes: set[str] = set()
    for commit in commits:
        if commit["hash"] in seen_hashes:
            continue

        # Method 1: Git trailer (highest confidence)
        skills, grade, source = _extract_skills_from_trailer(commit)
        if skills and 2 <= len(skills) <= 10:
            seen_hashes.add(commit["hash"])
            if _store_chain(skills, commit, source, repo_name, grade, dry_run):
                stats["chains"] += 1
                stats["by_source"][source] = stats["by_source"].get(source, 0) + 1
            continue

        # Method 2: Transcript correlation
        transcripts = _find_transcripts(repo, commit["timestamp"])
        if transcripts:
            transcript_skills = set()
            for t in transcripts:
                transcript_skills.update(_extract_skills_from_transcript(t))
            # Merge with file-based skills
            file_skills = _extract_skills_from_files(commit)
            all_skills = sorted(set(file_skills) | transcript_skills)
            if 2 <= len(all_skills) <= 10:
                seen_hashes.add(commit["hash"])
                if _store_chain(all_skills, commit, "commit-transcript", repo_name, dry_run=dry_run):
                    stats["chains"] += 1
                    stats["by_source"]["commit-transcript"] = stats["by_source"].get("commit-transcript", 0) + 1
                continue

        # Method 3: Commit message + files (lowest confidence)
        msg_skills, _ = _extract_skills_from_message(commit)
        file_skills = _extract_skills_from_files(commit)
        all_skills = sorted(set(msg_skills) | set(file_skills))
        if 2 <= len(all_skills) <= 10:
            seen_hashes.add(commit["hash"])
            if _store_chain(all_skills, commit, "commit-files", repo_name, dry_run=dry_run):
                stats["chains"] += 1
                stats["by_source"]["commit-files"] = stats["by_source"].get("commit-files", 0) + 1

    return stats


@app.command()
def extract(
    repo: str = typer.Option(..., "--repo", "-r", help="Path to git repo"),
    since: Optional[str] = typer.Option(None, "--since", help="Git --since date filter"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print but don't store"),
    limit: int = typer.Option(5000, "--limit", help="Max commits to process"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Extract skill chains from a single repo."""
    stats = extract_repo(repo, since=since, dry_run=dry_run, limit=limit)
    if as_json:
        print(json.dumps(stats, indent=2))
    else:
        logger.info(f"{stats['repo']}: {stats['chains']} chains from {stats['commits']} commits")


@app.command("extract-all")
def extract_all(
    since_last: bool = typer.Option(False, "--since-last", help="Only new commits since last run"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print but don't store"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Extract skill chains from all registered projects."""
    projects_file = Path.home() / ".agent-inbox" / "projects.json"
    if not projects_file.exists():
        logger.error("No projects.json found")
        raise typer.Exit(1)

    projects = json.loads(projects_file.read_text())
    state = _load_state() if since_last else {}

    all_stats = []
    total_chains = 0

    for name, path in sorted(projects.items()):
        if not Path(path).exists() or not (Path(path) / ".git").exists():
            continue

        since = state.get(name, {}).get("last_run") if since_last else None
        stats = extract_repo(path, since=since, dry_run=dry_run)
        all_stats.append(stats)
        total_chains += stats["chains"]

        # Update state
        if not dry_run:
            state[name] = {"last_run": datetime.now(timezone.utc).isoformat()}

    if not dry_run:
        _save_state(state)

    if as_json:
        print(json.dumps({"total_chains": total_chains, "repos": all_stats}, indent=2))
    else:
        logger.info(f"Total: {total_chains} chains from {len(all_stats)} repos")


if __name__ == "__main__":
    app()
