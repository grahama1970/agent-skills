"""Passive signal collector: mines session transcripts for quality indicators.

Inputs: --all to scan all sessions (default: last 5), --dry-run for fixtures.
Outputs: signals.jsonl records grouped by collection run.
Failure modes: corrupt JSONL transcript (skipped), unreadable file (logged, skipped).

Uses a watermark file to avoid re-scanning already-processed transcript lines.
"""

import json
import re
import sys
import typing as t
from datetime import datetime, timezone
from pathlib import Path

import typer
from loguru import logger

DATA_DIR = Path.home() / ".embry" / "dum-dum"
WATERMARK_PATH = DATA_DIR / "watermarks.json"

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"

CORRECTION_PATTERNS = [
    r"\bno\b,?\s+(?:that's|thats|it's|its)\s+(?:wrong|incorrect|not right)",
    r"\bstop\b",
    r"\bdon'?t\s+do\s+that\b",
    r"\bwrong\b",
    r"\bthat'?s\s+not\s+what\s+I\b",
    r"\bundo\b",
    r"\brevert\b",
    r"\bno,?\s+I\s+(?:said|meant|want)",
]

CORRECTION_RE = re.compile("|".join(CORRECTION_PATTERNS), re.IGNORECASE)

app = typer.Typer(add_completion=False)


def _load_watermarks() -> dict[str, int]:
    """Load {transcript_path: last_processed_line} watermark map."""
    if not WATERMARK_PATH.exists():
        return {}
    try:
        return json.loads(WATERMARK_PATH.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load watermarks: {}", exc)
        return {}


def _save_watermarks(wm: dict[str, int]) -> None:
    """Persist watermark map."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WATERMARK_PATH.write_text(json.dumps(wm, indent=2))


def scan_transcript(path: Path, start_line: int = 0) -> tuple[list[dict], int]:
    """Scan a single JSONL transcript for quality signals starting after start_line.

    Returns (signals, last_line_processed).
    """
    signals: list[dict] = []
    read_files: dict[str, int] = {}
    tool_calls: list[str] = []
    last_line = start_line

    try:
        with open(path) as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError) as exc:
        logger.error("Cannot read {}: {}", path, exc)
        return signals, start_line

    for line_num, line in enumerate(lines, 1):
        if line_num <= start_line:
            continue
        last_line = line_num

        line = line.strip()
        if not line:
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_type = record.get("type", "")
        role = record.get("role", "")
        content = record.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                c.get("text", "") for c in content if isinstance(c, dict)
            )

        if msg_type == "hook_result" and record.get("denied", False):
            signals.append({
                "type": "hook_denial",
                "source": str(path),
                "line": line_num,
                "detail": record.get("reason", "unknown")[:200],
                "timestamp": record.get("timestamp", ""),
            })

        if role == "user" and CORRECTION_RE.search(content):
            signals.append({
                "type": "user_correction",
                "source": str(path),
                "line": line_num,
                "detail": content[:200],
                "timestamp": record.get("timestamp", ""),
            })

        if msg_type == "tool_use" and record.get("name") == "Read":
            tool_input = record.get("input", {})
            file_path = tool_input.get("file_path", "")
            if file_path:
                read_files[file_path] = read_files.get(file_path, 0) + 1
                if read_files[file_path] > 1:
                    signals.append({
                        "type": "duplicate_read",
                        "source": str(path),
                        "line": line_num,
                        "detail": f"{file_path} (read #{read_files[file_path]})",
                        "timestamp": record.get("timestamp", ""),
                    })

        if msg_type == "tool_result" and record.get("is_error", False):
            signals.append({
                "type": "tool_error",
                "source": str(path),
                "line": line_num,
                "detail": str(record.get("content", ""))[:200],
                "timestamp": record.get("timestamp", ""),
            })

        if msg_type == "tool_use":
            tool_name = record.get("name", "")
            tool_calls.append(tool_name)
            if (
                len(tool_calls) >= 3
                and len(set(tool_calls[-3:])) == 1
                and (len(tool_calls) < 4 or tool_calls[-4] != tool_name)
            ):
                signals.append({
                    "type": "retry_loop",
                    "source": str(path),
                    "line": line_num,
                    "detail": f"{tool_name} called 3+ times consecutively",
                    "timestamp": record.get("timestamp", ""),
                })

    return signals, last_line


def find_transcripts(all_sessions: bool = False) -> list[Path]:
    """Find Claude Code session transcript files."""
    transcripts = []
    if not CLAUDE_PROJECTS_DIR.exists():
        return transcripts

    for project_dir in CLAUDE_PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        for session_file in project_dir.glob("*.jsonl"):
            transcripts.append(session_file)

    transcripts.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    if not all_sessions:
        return transcripts[:5]
    return transcripts


# --- Fixture data for --dry-run ---

DRY_RUN_SIGNALS = [
    {
        "type": "hook_denial",
        "source": "fixture",
        "line": 42,
        "detail": "PreToolUse: blocked Bash command with rm -rf",
        "timestamp": "2026-04-09T10:00:00Z",
    },
    {
        "type": "user_correction",
        "source": "fixture",
        "line": 87,
        "detail": "no, that's wrong. I said to use httpx not requests",
        "timestamp": "2026-04-09T10:05:00Z",
    },
    {
        "type": "duplicate_read",
        "source": "fixture",
        "line": 123,
        "detail": "src/main.py (read #3)",
        "timestamp": "2026-04-09T10:10:00Z",
    },
    {
        "type": "tool_error",
        "source": "fixture",
        "line": 156,
        "detail": "FileNotFoundError: /nonexistent/path.py",
        "timestamp": "2026-04-09T10:12:00Z",
    },
    {
        "type": "retry_loop",
        "source": "fixture",
        "line": 200,
        "detail": "Bash called 3+ times consecutively",
        "timestamp": "2026-04-09T10:15:00Z",
    },
]


def format_report(signals: list[dict]) -> str:
    """Format collected signals as a human-readable report."""
    lines = [
        "=== dum-dum passive signal collection ===",
        f"Time:    {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Signals: {len(signals)} total",
        "",
    ]

    by_type: dict[str, list[dict]] = {}
    for s in signals:
        by_type.setdefault(s["type"], []).append(s)

    for signal_type, items in sorted(by_type.items()):
        lines.append(f"  {signal_type}: {len(items)}")
        for item in items[:5]:
            lines.append(f"    - {item['detail']}")
        if len(items) > 5:
            lines.append(f"    ... and {len(items) - 5} more")

    return "\n".join(lines)


def save_signals(signals: list[dict]) -> None:
    """Append signals to signals.jsonl."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signal_count": len(signals),
        "signals": signals,
    }
    outpath = DATA_DIR / "signals.jsonl"
    with open(outpath, "a") as f:
        f.write(json.dumps(record) + "\n")
    logger.info("Saved {} signals to {}", len(signals), outpath)


@app.command()
def main(
    dry_run: t.Annotated[bool, typer.Option("--dry-run", help="Use fixture data")] = False,
    all_sessions: t.Annotated[bool, typer.Option("--all", help="Scan all sessions")] = False,
    json_out: t.Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Collect passive quality signals from session transcripts."""
    if dry_run:
        signals = DRY_RUN_SIGNALS
    else:
        transcripts = find_transcripts(all_sessions)
        if not transcripts:
            logger.warning("No transcripts found")
            print("No transcripts found.", file=sys.stderr)
            raise typer.Exit(code=0)

        watermarks = _load_watermarks()
        signals = []
        for t_path in transcripts:
            key = str(t_path)
            start = watermarks.get(key, 0)
            new_signals, new_wm = scan_transcript(t_path, start_line=start)
            signals.extend(new_signals)
            watermarks[key] = new_wm

        _save_watermarks(watermarks)
        logger.info("Processed {} transcripts, {} new signals", len(transcripts), len(signals))

    save_signals(signals)

    if json_out:
        print(json.dumps({"signal_count": len(signals), "signals": signals}, indent=2))
    else:
        print(format_report(signals))


if __name__ == "__main__":
    app()
