"""Per-channel drift detection on model quality time series.

Reads probes.jsonl and signals.jsonl, builds SEPARATE time series per channel
(probe, signals), then runs CUSUM and Page-Hinkley with a rolling baseline.

Inputs: --dry-run for fixture data, --json for machine-readable output.
Outputs: drift.jsonl with per-channel detections.
Failure modes: empty data files (exits 0 with message), corrupt JSONL (skipped lines).
"""

import json
import math
import sys
import typing as t
from datetime import datetime, timezone
from pathlib import Path

import typer
from loguru import logger

DATA_DIR = Path.home() / ".embry" / "dum-dum"

# Algorithm parameters
CUSUM_H = 5.0
CUSUM_K = 0.5
PH_THRESHOLD = 10.0
PH_DELTA = 0.01
WARMUP = 3
ROLLING_WINDOW = 20
# EWMA parameters per arXiv:2601.00554
EWMA_LAMBDA = 0.2      # smoothing factor (higher = more reactive to recent)
EWMA_L = 3.0           # control limit multiplier (L * sigma)

app = typer.Typer(add_completion=False)


def load_channel_series() -> dict[str, list[dict]]:
    """Build per-channel time series from probes.jsonl and signals.jsonl."""
    channels: dict[str, list[dict]] = {"probe": [], "signals": []}

    probes_path = DATA_DIR / "probes.jsonl"
    if probes_path.exists():
        with open(probes_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    channels["probe"].append({
                        "timestamp": record["timestamp"],
                        "value": record["summary"]["score"],
                        "model": record.get("model", "unknown"),
                    })
                except (json.JSONDecodeError, KeyError):
                    continue

    signals_path = DATA_DIR / "signals.jsonl"
    if signals_path.exists():
        with open(signals_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    count = record["signal_count"]
                    quality = max(0, 100 - count * 10)
                    channels["signals"].append({
                        "timestamp": record["timestamp"],
                        "value": quality,
                    })
                except (json.JSONDecodeError, KeyError):
                    continue

    for ch in channels.values():
        ch.sort(key=lambda x: x["timestamp"])

    return channels


def rolling_stats(values: list[float], window: int) -> tuple[float, float]:
    """Return (mean, stddev) over the last `window` values."""
    subset = values[-window:] if len(values) > window else values
    n = len(subset)
    if n == 0:
        return 0.0, 1.0
    mean = sum(subset) / n
    if n < 2:
        return mean, 1.0
    var = sum((v - mean) ** 2 for v in subset) / (n - 1)
    return mean, max(math.sqrt(var), 1e-9)


def detect_drift_channel(series: list[dict], channel: str) -> list[dict]:
    """Run CUSUM, Page-Hinkley, and EWMA on a single channel with rolling baseline.

    EWMA (per arXiv:2601.00554) complements CUSUM/PH: it's more sensitive to
    gradual shifts while CUSUM catches abrupt drops and PH catches persistent drift.
    """
    detections = []
    values: list[float] = []

    cusum_pos = 0.0
    cusum_neg = 0.0
    ph_sum = 0.0
    ph_min = float("inf")
    ewma_z: float | None = None  # EWMA statistic

    for i, point in enumerate(series):
        val = float(point["value"])
        values.append(val)

        if i < WARMUP:
            continue

        mean, std = rolling_stats(values[:i], ROLLING_WINDOW)
        z = (val - mean) / std

        # --- CUSUM ---
        cusum_neg = max(0.0, cusum_neg - z - CUSUM_K)
        cusum_pos = max(0.0, cusum_pos + z - CUSUM_K)

        if cusum_neg > CUSUM_H:
            severity = "HIGH" if cusum_neg > CUSUM_H * 2 else "MEDIUM"
            detections.append({
                "channel": channel,
                "sample_idx": i,
                "timestamp": point["timestamp"],
                "cusum_value": round(cusum_neg, 2),
                "method": "CUSUM",
                "severity": severity,
                "quality_score": val,
                "baseline_mean": round(mean, 2),
            })

        # --- Page-Hinkley ---
        ph_sum += mean - val - PH_DELTA
        ph_min = min(ph_min, ph_sum)

        if ph_sum - ph_min > PH_THRESHOLD:
            severity = "HIGH" if (ph_sum - ph_min) > PH_THRESHOLD * 2 else "MEDIUM"
            detections.append({
                "channel": channel,
                "sample_idx": i,
                "timestamp": point["timestamp"],
                "cusum_value": round(ph_sum - ph_min, 2),
                "method": "PAGE_HINKLEY",
                "severity": severity,
                "quality_score": val,
                "baseline_mean": round(mean, 2),
            })

        # --- EWMA (arXiv:2601.00554) ---
        # Exponentially weighted moving average of z-scores
        if ewma_z is None:
            ewma_z = z
        else:
            ewma_z = EWMA_LAMBDA * z + (1 - EWMA_LAMBDA) * ewma_z

        # EWMA control limit: L * sigma_ewma where sigma_ewma accounts for smoothing
        # sigma_ewma = sqrt(lambda / (2 - lambda)) * sigma_z (sigma_z ~ 1 for z-scores)
        ewma_sigma = math.sqrt(EWMA_LAMBDA / (2 - EWMA_LAMBDA))
        ewma_limit = EWMA_L * ewma_sigma

        if ewma_z < -ewma_limit:  # negative = quality dropping
            severity = "HIGH" if ewma_z < -ewma_limit * 1.5 else "MEDIUM"
            detections.append({
                "channel": channel,
                "sample_idx": i,
                "timestamp": point["timestamp"],
                "cusum_value": round(abs(ewma_z), 2),
                "method": "EWMA",
                "severity": severity,
                "quality_score": val,
                "baseline_mean": round(mean, 2),
            })

    return detections


# --- Fixture data for --dry-run ---

DRY_RUN_CHANNELS = {
    "probe": [
        {"timestamp": "2026-04-01T10:00:00Z", "value": 95},
        {"timestamp": "2026-04-02T10:00:00Z", "value": 93},
        {"timestamp": "2026-04-03T10:00:00Z", "value": 90},
        {"timestamp": "2026-04-04T10:00:00Z", "value": 92},
        {"timestamp": "2026-04-05T10:00:00Z", "value": 88},
        {"timestamp": "2026-04-06T10:00:00Z", "value": 75},
        {"timestamp": "2026-04-07T10:00:00Z", "value": 60},
        {"timestamp": "2026-04-08T10:00:00Z", "value": 55},
        {"timestamp": "2026-04-09T10:00:00Z", "value": 45},
    ],
    "signals": [
        {"timestamp": "2026-04-01T10:00:00Z", "value": 100},
        {"timestamp": "2026-04-02T10:00:00Z", "value": 90},
        {"timestamp": "2026-04-03T10:00:00Z", "value": 80},
        {"timestamp": "2026-04-04T10:00:00Z", "value": 90},
        {"timestamp": "2026-04-05T10:00:00Z", "value": 70},
        {"timestamp": "2026-04-06T10:00:00Z", "value": 50},
    ],
}


def format_report(all_detections: list[dict], channels: dict[str, list[dict]]) -> str:
    """Format drift results as a human-readable report."""
    total_points = sum(len(s) for s in channels.values())
    lines = [
        "=== dum-dum drift detection ===",
        f"Time:        {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Channels:    {', '.join(f'{k}({len(v)})' for k, v in channels.items())}",
        f"Data points: {total_points}",
        f"Drift alerts: {len(all_detections)}",
        "",
    ]

    if not all_detections:
        lines.append("  No quality drift detected.")
    else:
        header = f"{'CHAN':<10}| {'IDX':<6}| {'TIMESTAMP':<24}| {'VALUE':<8}| {'METHOD':<14}| {'SEVERITY'}"
        lines.append(header)
        lines.append("-" * len(header))
        for d in all_detections:
            lines.append(
                f"{d['channel']:<10}| {d['sample_idx']:<6}| {d['timestamp']:<24}| "
                f"{d['cusum_value']:<8}| {d['method']:<14}| {d['severity']}"
            )

    return "\n".join(lines)


def save_drift(detections: list[dict], channels: dict[str, list[dict]]) -> None:
    """Append drift results to drift.jsonl."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "alert_count": len(detections),
        "channels": {k: len(v) for k, v in channels.items()},
        "detections": detections,
    }
    outpath = DATA_DIR / "drift.jsonl"
    with open(outpath, "a") as f:
        f.write(json.dumps(record) + "\n")
    logger.info("Saved {} drift alerts to {}", len(detections), outpath)


@app.command()
def main(
    dry_run: t.Annotated[bool, typer.Option("--dry-run", help="Use fixture data")] = False,
    json_out: t.Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Run per-channel CUSUM and Page-Hinkley drift detection."""
    if dry_run:
        channels = DRY_RUN_CHANNELS
    else:
        channels = load_channel_series()
        total = sum(len(s) for s in channels.values())
        if total == 0:
            logger.warning("No quality data found")
            print("No quality data found. Run 'probe' and 'collect' first.", file=sys.stderr)
            raise typer.Exit(code=0)

    all_detections: list[dict] = []
    for channel_name, series in channels.items():
        dets = detect_drift_channel(series, channel_name)
        all_detections.extend(dets)
        if dets:
            logger.info("Channel '{}': {} drift alerts", channel_name, len(dets))

    save_drift(all_detections, channels)

    if json_out:
        print(json.dumps({
            "channels": {k: len(v) for k, v in channels.items()},
            "alert_count": len(all_detections),
            "detections": all_detections,
        }, indent=2))
    else:
        print(format_report(all_detections, channels))


if __name__ == "__main__":
    app()
