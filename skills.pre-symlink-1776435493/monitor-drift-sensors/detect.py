"""CUSUM and Page-Hinkley drift detection on sensor JSONL streams.

Pure Python — no external dependencies.
"""

import json
import math
import sys


# --- Algorithm parameters ---
CUSUM_H = 5.0        # CUSUM decision threshold
CUSUM_K = 0.5        # CUSUM drift allowance (slack)
PH_THRESHOLD = 10.0  # Page-Hinkley detection threshold
PH_DELTA = 0.01      # Page-Hinkley forgetting factor
WARMUP = 5           # Samples before detection begins


def running_stats(values: list[float]) -> tuple[float, float]:
    """Return (mean, stddev) of values."""
    n = len(values)
    if n == 0:
        return 0.0, 1.0
    mean = sum(values) / n
    if n < 2:
        return mean, 1.0
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, max(math.sqrt(var), 1e-9)


def detect_drift(records: list[dict]) -> list[dict]:
    """Run CUSUM and Page-Hinkley on a list of sensor records.

    Each record: {"timestamp": str, "sensor": str, "value": float}
    Returns list of drift detections.
    """
    detections: list[dict] = []
    values: list[float] = []

    # CUSUM state
    cusum_pos = 0.0
    cusum_neg = 0.0

    # Page-Hinkley state
    ph_sum = 0.0
    ph_min = float("inf")

    for i, rec in enumerate(records):
        val = float(rec["value"])
        values.append(val)

        if i < WARMUP:
            continue

        mean, std = running_stats(values[:WARMUP])

        # --- CUSUM ---
        z = (val - mean) / std
        cusum_pos = max(0.0, cusum_pos + z - CUSUM_K)
        cusum_neg = max(0.0, cusum_neg - z - CUSUM_K)

        if cusum_pos > CUSUM_H or cusum_neg > CUSUM_H:
            severity = "HIGH" if max(cusum_pos, cusum_neg) > CUSUM_H * 2 else "MEDIUM"
            detections.append({
                "sample_idx": i,
                "timestamp": rec["timestamp"],
                "cusum_value": round(max(cusum_pos, cusum_neg), 2),
                "method": "CUSUM",
                "severity": severity,
            })

        # --- Page-Hinkley ---
        ph_sum += val - mean - PH_DELTA
        ph_min = min(ph_min, ph_sum)

        if ph_sum - ph_min > PH_THRESHOLD:
            severity = "HIGH" if (ph_sum - ph_min) > PH_THRESHOLD * 2 else "MEDIUM"
            detections.append({
                "sample_idx": i,
                "timestamp": rec["timestamp"],
                "cusum_value": round(ph_sum - ph_min, 2),
                "method": "PAGE_HINKLEY",
                "severity": severity,
            })

    return detections


def format_table(detections: list[dict]) -> str:
    """Format detections as aligned table."""
    header = f"{'SAMPLE_IDX':<12}| {'TIMESTAMP':<24}| {'CUSUM_VALUE':<13}| {'METHOD':<14}| {'SEVERITY'}"
    sep = "-" * len(header)
    lines = [header, sep]
    for d in detections:
        lines.append(
            f"{d['sample_idx']:<12}| {d['timestamp']:<24}| {d['cusum_value']:<13}| {d['method']:<14}| {d['severity']}"
        )
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: detect.py <input.jsonl>", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]

    if input_path == "-":
        lines = sys.stdin.readlines()
    else:
        with open(input_path) as f:
            lines = f.readlines()

    records = [json.loads(line) for line in lines if line.strip()]

    detections = detect_drift(records)

    if not detections:
        print("No drift detected.")
    else:
        # Deduplicate: keep first detection per sample index
        seen: set[int] = set()
        unique: list[dict] = []
        for d in detections:
            if d["sample_idx"] not in seen:
                seen.add(d["sample_idx"])
                unique.append(d)
        print(format_table(unique))
        print(f"\n{len(unique)} drift point(s) detected.")


if __name__ == "__main__":
    main()
