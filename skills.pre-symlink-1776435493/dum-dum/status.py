"""Quick status: last probe results + drift state + watermark info.

Inputs: --json for machine-readable output.
Outputs: human-readable or JSON status summary.
Failure modes: missing data files (shows "none" gracefully).
"""

import json
import typing as t
from collections import deque
from pathlib import Path

import typer

DATA_DIR = Path.home() / ".embry" / "dum-dum"

app = typer.Typer(add_completion=False)


def last_line(path: Path) -> dict | None:
    """Read last non-empty line of a JSONL file without loading entire file."""
    if not path.exists():
        return None
    last = deque(maxlen=1)
    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                last.append(stripped)
    if not last:
        return None
    try:
        return json.loads(last[0])
    except json.JSONDecodeError:
        return None


@app.command()
def main(
    json_out: t.Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Show last probe results, signal collection, and drift state."""
    probe = last_line(DATA_DIR / "probes.jsonl")
    signal = last_line(DATA_DIR / "signals.jsonl")
    drift = last_line(DATA_DIR / "drift.jsonl")

    status: dict = {
        "last_probe": None,
        "last_signal_collection": None,
        "last_drift_check": None,
        "data_dir": str(DATA_DIR),
    }

    if probe:
        status["last_probe"] = {
            "timestamp": probe.get("timestamp"),
            "model": probe.get("model"),
            "grade": probe.get("summary", {}).get("grade"),
            "score": probe.get("summary", {}).get("score"),
            "avg_latency_ms": probe.get("summary", {}).get("avg_latency_ms"),
        }

    if signal:
        status["last_signal_collection"] = {
            "timestamp": signal.get("timestamp"),
            "signal_count": signal.get("signal_count"),
        }

    if drift:
        status["last_drift_check"] = {
            "timestamp": drift.get("timestamp"),
            "alert_count": drift.get("alert_count"),
            "channels": drift.get("channels"),
        }

    if json_out:
        print(json.dumps(status, indent=2))
        return

    print("=== dum-dum status ===")
    print(f"Data dir: {DATA_DIR}")
    print()

    if status["last_probe"]:
        p = status["last_probe"]
        print(f"Last probe:   {p['timestamp']}")
        print(f"  Model:      {p['model']}")
        print(f"  Grade:      {p['grade']} ({p['score']}/100)")
        if p.get("avg_latency_ms") is not None:
            print(f"  Avg latency: {p['avg_latency_ms']}ms")
    else:
        print("Last probe:   none (run: ./run.sh probe --dry-run)")

    print()

    if status["last_signal_collection"]:
        s = status["last_signal_collection"]
        print(f"Last signals: {s['timestamp']}")
        print(f"  Count:      {s['signal_count']}")
    else:
        print("Last signals: none (run: ./run.sh collect --dry-run)")

    print()

    if status["last_drift_check"]:
        d = status["last_drift_check"]
        print(f"Last drift:   {d['timestamp']}")
        print(f"  Alerts:     {d['alert_count']}")
        if d.get("channels"):
            print(f"  Channels:   {d['channels']}")
    else:
        print("Last drift:   none (run: ./run.sh drift --dry-run)")


if __name__ == "__main__":
    app()
