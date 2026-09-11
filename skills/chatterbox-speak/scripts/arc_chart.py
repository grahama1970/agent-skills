#!/usr/bin/env python3
"""Deterministic SVG chart of a chatterbox_speak.arc.v2 receipt.

Three lanes over the phases of one answer:
  tone energy (from tone calibration intensity), pace tempo factor,
  and complexity (simple=0.33 / moderate=0.66 / complex=1.0).
Pure string SVG; no dependencies.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TONE_ENERGY = {
    "careful_concerned": 0.55,
    "calm_precise": 0.30,
    "memory_confident": 0.70,
    "memory_uncertain": 0.65,
    "curious_searching": 0.80,
    "neutral_warm": 0.40,
    "relieved": 0.75,
    "playful_light": 0.85,
    "firm_boundary": 0.95,
}
TEMPO = {"slow": 0.85, "neutral": 1.0, "brisk": 1.08, "fast": 1.18}
COMPLEXITY = {"simple": 0.33, "moderate": 0.66, "complex": 1.0}

W, H = 900, 300
ML, MR, MT, MB = 60, 30, 30, 70


def lane_y(value: float) -> float:
    return MT + (H - MT - MB) * (1.0 - value)


def main() -> int:
    receipt_path, out_path = sys.argv[1], sys.argv[2]
    d = json.loads(Path(receipt_path).read_text())
    phases = d["phases"]
    n = len(phases)
    span = (W - ML - MR) / max(1, n)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        '<rect width="100%" height="100%" fill="#0b0f14"/>',
        f'<text x="{ML}" y="18" fill="#7dd3fc" font-family="monospace" font-size="13">conversation arc: {d["arc"]} ({n} phases)</text>',
    ]
    for lane, label, color, get in (
        (0, "tone energy", "#22d3ee",
         lambda p: TONE_ENERGY.get(p["tone"], 0.5)),
        (1, "pace tempo", "#34d399",
         lambda p: (TEMPO.get(p["effective_pace"], 1.0) - 0.8) / 0.4),
        (2, "complexity", "#f59e0b",
         lambda p: COMPLEXITY.get(p["complexity"], 0.33)),
    ):
        pts = []
        for i, p in enumerate(phases):
            x = ML + span * i + span / 2
            y = lane_y(max(0.0, min(1.0, get(p))))
            pts.append((x, y))
        parts.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="2.5" '
            f'points="{" ".join(f"{x},{y}" for x, y in pts)}"/>'
        )
        for (x, y), p in zip(pts, phases):
            parts.append(
                f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"/>'
            )
            parts.append(
                f'<text x="{x}" y="{H - MB + 14 + lane * 14}" '
                f'fill="{color}" font-family="monospace" font-size="9" '
                f'text-anchor="middle">{p["tone"]}/{p["effective_pace"]}</text>'
            )
        parts.append(
            f'<text x="{8}" y="{lane_y(0.92) + lane * 14}" fill="{color}" '
            f'font-family="monospace" font-size="10">{label}</text>'
        )
    for i, p in enumerate(phases):
        x = ML + span * i + span / 2
        parts.append(
            f'<text x="{x}" y="{H - MB + 56}" fill="#94a3b8" '
            f'font-family="monospace" font-size="9" text-anchor="middle">'
            f'{p["complexity"]}</text>'
        )
        parts.append(
            f'<line x1="{ML + span * i}" y1="{MT}" x2="{ML + span * i}" '
            f'y2="{H - MB}" stroke="#1e293b" stroke-width="1"/>'
        )
    parts.append("</svg>")
    Path(out_path).write_text("\n".join(parts), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
