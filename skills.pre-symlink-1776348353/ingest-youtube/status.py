#!/usr/bin/env python3
"""Simple status checker for youtube-transcripts batch jobs.

For cross-agent monitoring of long-running transcript downloads.

Usage:
    python status.py /path/to/output/dir
    python status.py /path/to/output/dir --watch  # Continuous monitoring
"""
import json
import sys
import time
from pathlib import Path


def get_status(output_dir: str) -> dict:
    """Get status of a batch job from its output directory."""
    output_path = Path(output_dir)
    state_file = output_path / ".batch_state.json"

    if not state_file.exists():
        return {"error": "No batch state found", "output_dir": str(output_dir)}

    try:
        with open(state_file) as f:
            state = json.load(f)
    except Exception as e:
        return {"error": f"Failed to read state: {e}", "output_dir": str(output_dir)}

    # Count completed files
    json_files = list(output_path.glob("*.json"))
    completed_count = len([f for f in json_files if f.name != ".batch_state.json"])

    return {
        "output_dir": str(output_dir),
        "completed": completed_count,
        "stats": state.get("stats", {}),
        "current_video": state.get("current_video", ""),
        "current_method": state.get("current_method", ""),
        "last_updated": state.get("last_updated", ""),
        "consecutive_failures": state.get("consecutive_failures", 0),
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python status.py /path/to/output/dir [--watch]", file=sys.stderr)
        sys.exit(1)

    output_dir = sys.argv[1]
    watch = "--watch" in sys.argv

    if watch:
        try:
            while True:
                status = get_status(output_dir)
                print(f"\033[2J\033[H{json.dumps(status, indent=2)}")  # Clear screen
                time.sleep(5)
        except KeyboardInterrupt:
            pass
    else:
        print(json.dumps(get_status(output_dir), indent=2))


if __name__ == "__main__":
    main()
