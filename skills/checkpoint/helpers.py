"""Checkpoint helper functions: git operations, memory client, skill chain storage.

Extracted from checkpoint.py to stay under the 800-line limit.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger

# ---------------------------------------------------------------------------
# Constants (shared with checkpoint.py)
# ---------------------------------------------------------------------------

MEMORY_SOCK = "/run/user/1000/embry/memory.sock"
MEMORY_TCP_URL = "http://127.0.0.1:8601"
CHECKPOINT_PREFIX = "CHECKPOINT:"


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def git_exec(
    args: list[str],
    cwd: str | None = None,
    timeout: int = 10,
) -> tuple[int, str, str]:
    """Run a git command; return (returncode, stdout, stderr) or (1, '', '') on error."""
    try:
        r = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception:
        return 1, "", ""


def git(args: list[str], cwd: str | None = None) -> str:
    """Run a git command and return stdout, or empty string on failure."""
    _, stdout, _ = git_exec(args, cwd=cwd)
    return stdout


def detect_project_root() -> str:
    """Auto-detect the git project root from CWD."""
    root = git(["rev-parse", "--show-toplevel"])
    return root or os.getcwd()


def detect_scope(project_root: str) -> str:
    """Derive a scope name from the git remote or directory name."""
    remote = git(["remote", "get-url", "origin"], cwd=project_root)
    if remote:
        name = remote.rstrip("/").rsplit("/", 1)[-1]
        if name.endswith(".git"):
            name = name[:-4]
        return name
    return Path(project_root).name


def default_workspace_scope() -> str:
    """Default scope for recall/list/last: must match detect_scope() used by save."""
    root = detect_project_root()
    return detect_scope(root)


def git_context(project_root: str) -> dict:
    """Gather current git state for checkpoint context."""
    branch = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=project_root)
    commit = git(["rev-parse", "--short", "HEAD"], cwd=project_root)
    commit_msg = git(["log", "-1", "--format=%s"], cwd=project_root)
    recent_log = git(["log", "--oneline", "-5", "--no-decorate"], cwd=project_root)
    recent_commits = recent_log.splitlines() if recent_log else []
    diff_files = git(["diff", "--name-only", "HEAD"], cwd=project_root)
    modified = diff_files.splitlines() if diff_files else []
    return {
        "branch": branch,
        "commit": commit,
        "commit_message": commit_msg,
        "recent_commits": recent_commits,
        "modified_files": modified[:20],
    }


# ---------------------------------------------------------------------------
# Memory daemon interface (httpx Unix socket)
# ---------------------------------------------------------------------------


def memory_post(endpoint: str, payload: dict, console=None, retries: int = 0) -> dict:
    """POST to memory daemon and return parsed JSON.

    Primary:  Unix socket at MEMORY_SOCK.
    Fallback: TCP at MEMORY_TCP_URL when the socket file is absent.

    Args:
        retries: Number of retry attempts on transient failures (timeout, connect).
                 Default 0 for reads. Callers storing critical data (checkpoints)
                 should pass retries=2.
    """
    import time
    import typer

    sock_exists = Path(MEMORY_SOCK).exists()
    timeout = httpx.Timeout(30.0, connect=5.0)

    if sock_exists:
        transport: httpx.HTTPTransport | None = httpx.HTTPTransport(uds=MEMORY_SOCK)
        base_url = "http://localhost"
        location = MEMORY_SOCK
    else:
        transport = None
        base_url = MEMORY_TCP_URL
        location = MEMORY_TCP_URL

    requested_collection = payload.get("collection", "?")
    logger.debug("POST {}{} collection={} payload_keys={}", location, endpoint, requested_collection, list(payload.keys()))

    max_attempts = 1 + retries
    last_error = None

    for attempt in range(max_attempts):
        try:
            with httpx.Client(transport=transport, timeout=timeout) as client:
                response = client.post(f"{base_url}{endpoint}", json=payload)
                response.raise_for_status()
                result = response.json()
                # Log where the document actually landed
                if endpoint == "/store" and isinstance(result, dict):
                    actual_id = result.get("_id", "")
                    actual_key = result.get("_key", "")
                    actual_collection = actual_id.split("/")[0] if actual_id and "/" in actual_id else "unknown"
                    if requested_collection != "?" and actual_collection != "unknown" and actual_collection != requested_collection:
                        logger.error(
                            "COLLECTION MISMATCH: requested={} actual={} _id={} _key={}",
                            requested_collection, actual_collection, actual_id, actual_key,
                        )
                    else:
                        logger.info("Stored to {} _key={}", actual_collection or requested_collection, actual_key or actual_id)
                if attempt > 0:
                    logger.info("Succeeded on retry attempt {}/{}", attempt, retries)
                return result
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            last_error = exc
            if attempt < max_attempts - 1:
                wait = 2 ** attempt  # 1s, 2s
                logger.warning(
                    "memory_post{} failed (attempt {}/{}): {}. Retrying in {}s...",
                    endpoint, attempt + 1, max_attempts, type(exc).__name__, wait,
                )
                time.sleep(wait)
                continue
            # Final attempt failed
            if isinstance(exc, httpx.ConnectError):
                if console:
                    console.print(
                        f"[red]Memory daemon unavailable at {location} "
                        f"(is embry-agent.service running?) "
                        f"[{max_attempts} attempts exhausted][/red]"
                    )
            else:
                if console:
                    console.print(f"[red]Memory daemon timed out after 30s [{max_attempts} attempts exhausted][/red]")
            raise typer.Exit(1)
        except httpx.HTTPStatusError as exc:
            # HTTP errors (4xx/5xx) are not retried -- they indicate bad data, not transient failure
            if console:
                console.print(
                    f"[red]Memory daemon returned {exc.response.status_code}:[/red] "
                    f"{exc.response.text[:200]}"
                )
            raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Git commit + push (NON-NEGOTIABLE)
# ---------------------------------------------------------------------------


def detect_skills_root(project_root: str) -> str | None:
    """Return the canonical skills dir path, or None if not found."""
    env_skills = os.environ.get("SKILLS_DIR", "")
    if env_skills and os.path.isdir(env_skills):
        return env_skills
    candidate = os.path.join(project_root, ".pi", "skills")
    return candidate if os.path.isdir(candidate) else None


def stage_and_diff(cwd: str, extra_files: list[str] | None = None) -> tuple[bool, str]:
    """Stage all modified tracked files; return (has_staged, diff_stat)."""
    modified = git(["diff", "--name-only"], cwd=cwd).splitlines()
    staged_pre = git(["diff", "--cached", "--name-only"], cwd=cwd).splitlines()

    if not modified and not staged_pre and not extra_files:
        return False, ""

    for f in extra_files or []:
        abs_path = f if os.path.isabs(f) else os.path.join(cwd, f)
        if os.path.exists(abs_path):
            git(["add", f], cwd=cwd)

    if modified:
        git(["add", "-u"], cwd=cwd)

    staged_after = git(["diff", "--cached", "--name-only"], cwd=cwd)
    if not staged_after:
        return False, ""

    diff_raw = git(["diff", "--cached", "--stat"], cwd=cwd)
    diff_stat = ""
    if diff_raw:
        stat_lines = diff_raw.strip().splitlines()
        diff_stat = stat_lines[-1] if stat_lines else diff_raw[:200]

    return True, diff_stat


def commit_one_repo(cwd: str, msg: str, label: str = "", console=None) -> dict:
    """Commit staged changes in cwd; push best-effort. Return {commit_hash, diff_stat}."""
    info: dict = {}
    tag = f" ({label})" if label else ""

    rc, out, err = git_exec(["commit", "-m", msg], cwd=cwd, timeout=30)
    if rc != 0:
        if console:
            console.print(f"[yellow]GIT COMMIT{tag}: {out or err}[/yellow]")
        return info

    if console:
        console.print(f"[green]GIT COMMIT{tag}:[/green] {msg}")
    commit_hash = git(["rev-parse", "HEAD"], cwd=cwd)
    if commit_hash:
        info["commit_hash"] = commit_hash
    diff_raw = git(["diff", "--stat", "HEAD~1"], cwd=cwd)
    if diff_raw:
        stat_lines = diff_raw.strip().splitlines()
        info["diff_stat"] = stat_lines[-1] if stat_lines else diff_raw[:200]

    branch = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
    if branch:
        push_rc, _, push_err = git_exec(["push", "origin", branch], cwd=cwd, timeout=60)
        if push_rc == 0:
            if console:
                console.print(f"[green]GIT PUSH{tag}:[/green] origin/{branch}")
        else:
            if console:
                console.print(f"[yellow]GIT PUSH{tag} failed: {push_err[:100]}[/yellow]")

    return info


def git_commit_and_push(project_root: str, topic: str, files: list[str], console=None, skills: list[str] | None = None, grade: str = "") -> dict:
    """NON-NEGOTIABLE: Commit project + skills on every checkpoint.

    Returns dict with commit_hash, diff_stat, skills_commit_hash, skills_diff_stat.
    """
    result: dict = {}
    short_topic = topic[:60].replace('"', "'")

    has_staged, _ = stage_and_diff(project_root, extra_files=files)
    if has_staged:
        staged_count = len(git(["diff", "--cached", "--name-only"], cwd=project_root).splitlines())
        msg = f"checkpoint: {short_topic} ({staged_count} files)"
        # Append skill chain + grade as git trailers for commit-anchored extraction
        trailers = []
        if skills:
            trailers.append(f"Skills: {', '.join(s.lstrip('/') for s in skills)}")
        if grade:
            trailers.append(f"Grade: {grade}")
        if trailers:
            msg += "\n\n" + "\n".join(trailers)
        info = commit_one_repo(project_root, msg, console=console)
        result.update(info)

    skills_root = detect_skills_root(project_root)
    if skills_root:
        project_git_root = git(["rev-parse", "--show-toplevel"], cwd=project_root)
        skills_git_root = git(["rev-parse", "--show-toplevel"], cwd=skills_root)
        if skills_git_root and skills_git_root != project_git_root:
            s_staged, _ = stage_and_diff(skills_root)
            if s_staged:
                sc = len(git(["diff", "--cached", "--name-only"], cwd=skills_root).splitlines())
                s_msg = f"checkpoint: {short_topic} ({sc} files)"
                s_info = commit_one_repo(skills_root, s_msg, label="skills", console=console)
                if s_info.get("commit_hash"):
                    result["skills_commit_hash"] = s_info["commit_hash"]
                if s_info.get("diff_stat"):
                    result["skills_diff_stat"] = s_info["diff_stat"]
        else:
            logger.info("Skills dir shares repo with project — covered by project commit")

    return result


# ---------------------------------------------------------------------------
# Skill chain storage
# ---------------------------------------------------------------------------


def store_skill_chain(
    topic: str,
    summary: str,
    decisions: list[str],
    scope: str,
    outcome: str,
    explicit_skills: list[str] | None = None,
    console=None,
    checkpoint_key: str = "",
) -> list[str]:
    """Store skill chain for /recommend-skill-chain. Returns resolved chain.

    Handles all outcomes with polarity for recommendation.
    If checkpoint_key is provided, creates an edge linking the checkpoint
    to its skill chain so recall can follow the edge directly.
    """
    if explicit_skills:
        chain = [s.lstrip("/") for s in explicit_skills if s.strip()]
        source = "explicit"
    else:
        text = f"{summary} {' '.join(decisions)}"
        matches = re.findall(r'/([a-z][a-z0-9-]{1,30})', text)
        seen: set[str] = set()
        chain = [m for m in matches if m not in seen and not seen.add(m)]  # type: ignore[func-returns-value]
        source = "regex"

    if not chain:
        return []

    if outcome == "failed":
        confidence, polarity_tag = 1.0, "proven-failure"
    elif outcome == "partial":
        confidence, polarity_tag = 0.5, "partial-success"
    else:
        confidence = 1.0 if source == "explicit" else 0.8
        polarity_tag = "proven-success"

    tags = ["skill-chain", f"outcome:{outcome}", f"source:{source}", polarity_tag]
    timestamp = datetime.now(timezone.utc).isoformat()

    lesson_key = ""
    try:
        resp = memory_post("/learn", {
            "problem": f"SKILL-CHAIN: {outcome} for {scope}: {topic}",
            "solution": json.dumps({
                "chain": chain,
                "task": topic,
                "outcome": outcome,
                "confidence": confidence,
                "scope": scope,
                "timestamp": timestamp,
            }),
            "scope": "skill-chains",
            "tags": tags,
        }, console=console)
        if isinstance(resp, dict):
            # /learn returns {"items": [{"_key": "..."}]}
            items = resp.get("items", [])
            if items and isinstance(items[0], dict):
                lesson_key = items[0].get("_key", "")
            else:
                lesson_key = resp.get("_key", "")
        logger.info("Stored {} chain (conf={}) for '{}': {}", source, confidence, topic[:40], chain)
    except Exception:
        pass

    # Also store in the typed skill_chains collection (self-contained document)
    chain_key = ""
    if len(chain) >= 2:
        try:
            chain_key = _store_typed_skill_chain(
                chain, topic, outcome,
                summary=summary, grade=polarity_tag, scope=scope,
                tags=tags,
            )
        except Exception as exc:
            logger.warning("Typed skill_chain storage failed (non-fatal): {}", exc)

    # Create edges so recall can traverse to the chain deterministically
    # lesson → chain: "this lesson was solved by this chain"
    if lesson_key and chain_key:
        try:
            _link_to_chain(
                from_collection="lessons_v2", from_key=lesson_key,
                chain_key=chain_key, console=console,
            )
        except Exception as exc:
            logger.warning("lesson→chain edge failed (non-fatal): {}", exc)
    # checkpoint → chain: "this session produced this chain"
    if checkpoint_key and chain_key:
        try:
            _link_to_chain(
                from_collection="checkpoints", from_key=checkpoint_key,
                chain_key=chain_key, console=console,
            )
        except Exception as exc:
            logger.warning("checkpoint→chain edge failed (non-fatal): {}", exc)

    return chain


def _link_to_chain(from_collection: str, from_key: str, chain_key: str, console=None) -> None:
    """Create an edge in skill_chain_edges linking a source document to its chain.

    Edge: {from_collection}/{from_key} → skill_chains/{chain_key}
    This makes the chain recommendation deterministic — recall follows the
    edge instead of doing a separate semantic search.
    """
    edge_doc = {
        "_from": f"{from_collection}/{from_key}",
        "_to": f"skill_chains/{chain_key}",
        "type": "produced_by",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    memory_post("/store", {
        "document": edge_doc,
        "collection": "skill_chain_edges",
    }, console=console)
    logger.info("Linked {}/{} → skill_chains/{}", from_collection, from_key, chain_key)


def _store_typed_skill_chain(
    chain: list[str], topic: str, outcome: str,
    summary: str = "", grade: str = "", scope: str = "",
    commit: str = "", files_changed: list[str] | None = None,
    tags: list[str] | None = None,
) -> str:
    """Write self-contained skill chain to skill_chains collection.

    Returns the chain _key. Empty string on failure.
    The chain document includes problem, solution, grade, commit,
    files_changed, and tags — everything needed for recall without edges.
    """
    try:
        from graph_memory.lessons.skill_chains import learn_chain
    except ImportError:
        import subprocess
        skill_dir = Path(__file__).parent.parent / "memory"
        cmd = [
            str(skill_dir / "run.sh"), "chain-learn",
            "--skills", ",".join(chain),
            "--task", topic[:500],
            "--source", "production",
        ]
        if outcome in ("success", "partial"):
            cmd += ["--success"]
        else:
            cmd += ["--no-success"]
        subprocess.run(cmd, capture_output=True, timeout=30)
        return ""

    doc = learn_chain(
        skills=chain,
        task_description=topic[:500],
        source="production",
        success=outcome in ("success", "partial"),
        problem=topic,
        solution=summary,
        grade=grade,
        commit=commit,
        files_changed=files_changed,
        tags=tags,
        scope=scope,
    )
    return doc.get("_key", "")


# ---------------------------------------------------------------------------
# Auto-grading (RUBRIC.md decision tree)
# ---------------------------------------------------------------------------


def auto_grade(
    summary: str,
    decisions: list[str],
    next_steps: list[str],
    blockers: list[str],
    outcome: str,
) -> str:
    """Derive a grade from session signals using the RUBRIC.md decision tree."""
    text = f"{summary} {' '.join(decisions)} {' '.join(next_steps)}".lower()

    stop_signals = ("stop", "nevermind", "skip", "give up", "abandon", "blocked")
    if blockers or outcome in ("failed", "blocked") or any(s in text for s in stop_signals):
        return "unresolved"

    hack_signals = ("good enough", "for now", "hack", "workaround", "temporary", "bypass")
    if any(s in text for s in hack_signals) or outcome == "partial":
        return "workaround"

    correction_signals = (
        "correction", "rework", "multiple attempts", "fixed after",
        "had to redo", "try again", "not that",
    )
    if any(s in text for s in correction_signals):
        return "solved"

    reuse_signals = (
        "new skill", "created skill", "generalizable", "reusable",
        "stored for reuse", "skill created", "pattern for",
    )
    if any(s in text for s in reuse_signals):
        return "reusable"

    return "clean"


# ---------------------------------------------------------------------------
# Claude memory + mine-transcripts helpers
# ---------------------------------------------------------------------------


def detect_transcript_paths(project_root: str) -> list[str]:
    """Auto-detect transcript .jsonl files for the current Claude Code session.

    Claude Code stores transcripts at:
      ~/.claude/projects/-<sanitized-path>/<session-uuid>/*.jsonl
    plus subagent transcripts in a subagents/ subdirectory.

    Returns absolute paths to the main session transcript(s) only —
    subagent fragments are excluded since they lack full session context.
    """
    sanitized = project_root.lstrip("/").replace("/", "-")
    claude_dir = Path.home() / ".claude" / "projects" / f"-{sanitized}"
    if not claude_dir.exists():
        claude_dir = Path.home() / ".claude" / "projects" / sanitized
    if not claude_dir.exists():
        logger.debug("No Claude project dir at {}", claude_dir)
        return []

    # Find the most recently modified session directory (UUID-named)
    session_dirs = [
        d for d in claude_dir.iterdir()
        if d.is_dir() and len(d.name) == 36 and "-" in d.name
    ]
    if not session_dirs:
        return []

    latest = max(session_dirs, key=lambda d: d.stat().st_mtime)

    # Main transcript only — exclude subagents/ directory
    paths = sorted(
        str(p) for p in latest.glob("*.jsonl")
        if p.is_file()
    )
    logger.info("Detected {} transcript files in {}", len(paths), latest)
    return paths


def ingest_claude_memory(project_root: str, evidence: list[str]) -> list[str]:
    """Scan ~/.claude/ project memory for cross-references.

    Returns filenames of feedback/project memos (not full content).
    """
    refs: list[str] = []
    sanitized = project_root.replace("/", "-")
    claude_dir = Path.home() / ".claude" / "projects" / sanitized / "memory"
    if not claude_dir.exists():
        logger.debug("No Claude memory dir at {}", claude_dir)
        return refs

    for md_file in sorted(claude_dir.glob("*.md")):
        if md_file.name == "MEMORY.md":
            continue
        refs.append(f"claude-memory:{md_file.name}")

    if refs:
        logger.info("Found {} Claude memory files in {}", len(refs), claude_dir)
    return refs


def mine_session_skills(project_root: str) -> list[str]:
    """Extract skill chains from the most recent conversation transcript.

    Calls /mine-transcripts if available, else falls back to regex.
    """
    skills_dir = os.path.join(project_root, ".pi", "skills", "mine-transcripts")
    run_sh = os.path.join(skills_dir, "run.sh")
    if os.path.isfile(run_sh):
        try:
            result = subprocess.run(
                [run_sh, "mine", "--all-agents", "--latest", "--json"],
                capture_output=True, text=True, timeout=30,
                cwd=skills_dir,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout.strip())
                chains = data.get("skill_chains", [])
                if chains:
                    return chains[0] if isinstance(chains[0], list) else chains
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            pass

    sanitized = project_root.replace("/", "-")
    claude_dir = Path.home() / ".claude" / "projects" / sanitized
    if not claude_dir.exists():
        return []

    convos = sorted(claude_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not convos:
        return []

    try:
        text = convos[0].read_text(errors="ignore")[:50000]
        matches = re.findall(r'/([a-z][a-z0-9-]{1,30})', text)
        seen: set[str] = set()
        return [m for m in matches if m not in seen and not seen.add(m)][:10]  # type: ignore[func-returns-value]
    except Exception:
        return []
