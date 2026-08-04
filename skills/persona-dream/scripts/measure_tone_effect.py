#!/usr/bin/env python3
"""Does the requested delivery tone change the audio at all? (#1209)

Tone now survives normalization (#1202) and is recorded on every spoken journal
(#1208). Neither fact shows it reaches the waveform. Two things say it might not:
``emotion_knobs`` comes back ``null`` for every tone including accepted ones, and
Chatterbox's own ``stage_preset_affect_status`` reports preset-driven shifts
measured BELOW same-parameter stochastic spread.

So this measures instead of asserting. The same text is rendered under several
requested tones, and separately N times under one unchanged tone. The neutral
repeats give the renderer's own noise floor; a tone only counts as audible when
it moves a metric further than that floor.

Calibrating from the repeats is the whole design. A threshold picked by hand
would be a threshold picked to pass. If tone turns out to be inaudible, that is
a completed result: the project stops claiming emotional delivery and says so.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
CHATTERBOX = os.environ.get("CHATTERBOX_BASE_URL", "http://127.0.0.1:8018")
CHATTERBOX_OUT_HOST_ROOT = Path(
    os.environ.get("CHATTERBOX_OUT_HOST_ROOT",
                   "/home/graham/workspace/experiments/chatterbox/logs")
)

#: Metrics that would carry audible affect. Reused from the listener-study
#: technical screen so one measurement vocabulary covers both lanes.
AFFECT_METRICS = (
    "f0_median_hz", "f0_range_hz", "rms_dbfs", "k_weighted_loudness_lkfs",
    "duration_s", "voiced_ratio", "pause_ratio",
)

#: A tone must move a metric by more than this many neutral standard deviations
#: to count. Frozen before measurement; 3 sd is the same bar the listener-study
#: screen uses, so "audible" here means the same thing it means there.
K_SD = 3.0


def utc_now() -> str:
    return datetime.now().astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rel(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def sha_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_sibling(name: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(f"{name}.py"))
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load sibling script: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def post_json(url: str, payload: dict[str, Any], timeout: int = 900) -> dict[str, Any]:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def resolve_host_audio(container_path: str) -> Path | None:
    if not container_path:
        return None
    p = Path(container_path)
    if p.is_file():
        return p
    if p.is_absolute() and len(p.parts) > 2 and p.parts[1] == "out":
        host = CHATTERBOX_OUT_HOST_ROOT.joinpath(*p.parts[2:])
        if host.is_file():
            return host
    return None


def render(text: str, tone: str, label: str, out_dir: Path, ref_audio: str) -> dict[str, Any]:
    """One live render; returns the local wav path and the normalized tone."""
    response = post_json(f"{CHATTERBOX}/synthesize-batch", {
        "answer_text": text, "label": label,
        "use_blessed_qra_cache": False, "asr_verify": False, "asr_cache": False,
        "voice_delivery": {"tone": tone, "intensity": 0.6, "valence": -0.1},
        "ref_audio": ref_audio,
    })
    source = resolve_host_audio(str(response.get("finished_response_audio") or ""))
    dest = out_dir / f"{label}.wav"
    if source is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    return {
        "label": label, "requested_tone": tone,
        "normalized_tone": response.get("normalized_tone"),
        "emotion_knobs": response.get("emotion_knobs"),
        "wav": dest if dest.is_file() else None,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    screen = _load_sibling("technical_screen_blinded_listener_study")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    text = args.text
    if not text:
        spoken = Path(args.run_dir) / "journal_spoken.txt" if args.run_dir else None
        if spoken and spoken.is_file():
            text = spoken.read_text(encoding="utf-8").strip()
    if not text:
        raise SystemExit("no text: pass --text or --run-dir containing journal_spoken.txt")
    text = text[: args.max_chars]

    failed: list[str] = []

    # Noise floor first, so the bar is set before any tone is seen.
    neutral: list[dict[str, Any]] = []
    for i in range(1, args.neutral_repeats + 1):
        r = render(text, args.neutral_tone, f"tone_neutral_{i:02d}", out_dir, args.ref_audio)
        if r["wav"] is None:
            failed.append(f"neutral_render_missing:{i}")
            continue
        neutral.append(screen.measure_wav(r["wav"]))

    if len(neutral) < 3:
        return {
            "schema": "persona_dream.tone_effect_receipt.v1", "created_at": utc_now(),
            "status": "BLOCKED_INSUFFICIENT_NEUTRAL_REPEATS", "mocked": False, "live": True,
            "neutral_usable": len(neutral), "failed_gates": failed or ["neutral_repeats_too_few"],
        }

    floor: dict[str, dict[str, float]] = {}
    for metric in AFFECT_METRICS:
        values = [float(m[metric]) for m in neutral if metric in m]
        if len(values) < 3:
            continue
        # Round the sd FIRST, then derive the threshold from the rounded value.
        # Publishing a rounded sd next to a threshold computed from the full
        # precision one makes the receipt fail its own arithmetic: a reader who
        # recomputes K_SD * sd gets a different number than the one gating the
        # result.
        sd = round(float(statistics.stdev(values)), 6)
        floor[metric] = {
            "median": round(float(statistics.median(values)), 6),
            "sd": sd,
            "threshold": round(K_SD * sd, 6),
            "n": len(values),
        }

    tone_rows: list[dict[str, Any]] = []
    audible_tones: set[str] = set()
    knobs_seen = False
    for tone in args.tone:
        r = render(text, tone, f"tone_probe_{tone}", out_dir, args.ref_audio)
        if r["emotion_knobs"]:
            knobs_seen = True
        if r["wav"] is None:
            failed.append(f"tone_render_missing:{tone}")
            continue
        if r["normalized_tone"] != tone:
            failed.append(f"tone_did_not_survive:{tone}->{r['normalized_tone']}")
        metrics = screen.measure_wav(r["wav"])
        exceeded: list[dict[str, Any]] = []
        for metric, cal in floor.items():
            if metric not in metrics:
                continue
            delta = float(metrics[metric]) - cal["median"]
            if abs(delta) > cal["threshold"]:
                exceeded.append({"metric": metric, "delta": round(delta, 6),
                                 "threshold": cal["threshold"]})
        # How far past the bar, not just whether it cleared. A metric that
        # exceeds by 3% with n=6 neutrals is noise wearing a PASS.
        for e in exceeded:
            e["margin_ratio"] = round(abs(e["delta"]) / e["threshold"], 3) if e["threshold"] else None
        if exceeded:
            audible_tones.add(tone)
        tone_rows.append({
            "requested_tone": tone,
            "normalized_tone": r["normalized_tone"],
            "emotion_knobs": r["emotion_knobs"],
            "metrics": {k: metrics[k] for k in AFFECT_METRICS if k in metrics},
            "metrics_beyond_neutral_spread": exceeded,
            "audible_by_this_measure": bool(exceeded),
        })

    # Three outcomes, not two. "Cleared the bar on one metric by a hair" is a
    # different finding from "moved several metrics decisively", and collapsing
    # them into one PASS is how a weak result gets cited as a strong one.
    strong = {
        row["requested_tone"] for row in tone_rows
        if len(row["metrics_beyond_neutral_spread"]) >= 2
        or any((e.get("margin_ratio") or 0) >= 1.5 for e in row["metrics_beyond_neutral_spread"])
    }
    audible = bool(audible_tones)
    if strong:
        status = "PASS_TONE_AUDIBLE"
    elif audible:
        status = "MARGINAL_TONE_EFFECT_AT_NOISE_FLOOR"
    else:
        status = "BLOCKED_TONE_BELOW_STOCHASTIC_SPREAD"

    receipt = {
        "schema": "persona_dream.tone_effect_receipt.v1",
        "created_at": utc_now(),
        "status": status,
        "mocked": False,
        "live": True,
        "endpoint": f"POST {CHATTERBOX}/synthesize-batch",
        "text_sha256": "sha256:" + hashlib.sha256(text.encode()).hexdigest(),
        "text_chars": len(text),
        "neutral_tone": args.neutral_tone,
        "neutral_repeats_usable": len(neutral),
        "k_sd": K_SD,
        "threshold_rule": (
            "a tone counts as audible only when a metric moves further from the "
            "neutral median than K_SD neutral standard deviations; thresholds are "
            "derived from the repeats, never chosen"
        ),
        "neutral_floor": floor,
        "tones": tone_rows,
        "audible_tones": sorted(audible_tones),
        "decisively_audible_tones": sorted(strong),
        "emotion_knobs_ever_returned": knobs_seen,
        "failed_gates": failed,
        "claims": {
            "proves": ([
                "at least one requested tone moved an acoustic metric beyond the "
                "renderer's own same-parameter stochastic spread",
            ] if audible else [
                "no requested tone moved any measured metric beyond the renderer's "
                "own same-parameter stochastic spread on this text",
            ]),
            "does_not_prove": [
                "that a listener perceives the requested emotion",
                "anything about tones, texts, or backends outside this run",
            ],
        },
        "disposition": (
            "Requested tone moved at least one metric decisively beyond the noise "
            "floor; emotional-delivery claims may cite this receipt."
            if strong else
            "Requested tone cleared the noise floor on a single metric by a small "
            "margin. This is suggestive, NOT sufficient to claim emotional "
            "delivery. Re-run with more neutral repeats before citing it."
            if audible else
            "Requested tone is NOT audible by this measure. The project must stop "
            "implying emotional delivery and say so in its surfaces."
        ),
    }
    out = Path(args.out) if args.out else out_dir / "TONE_EFFECT_RECEIPT.json"
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path)
    ap.add_argument("--text", default="")
    ap.add_argument("--tone", action="append", default=[])
    ap.add_argument("--neutral-tone", default="neutral_warm")
    ap.add_argument("--neutral-repeats", type=int, default=8)
    ap.add_argument("--ref-audio", default="/data/embry_ref.wav")
    ap.add_argument("--max-chars", type=int, default=400)
    ap.add_argument("--out-dir", type=Path, default=Path("/tmp/pd-tone-effect"))
    ap.add_argument("--out", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not args.tone:
        args.tone = ["firm_boundary", "grief_safe", "memory_uncertain"]
    r = run(args)
    print(json.dumps(r, indent=2, sort_keys=True) if args.json else
          f"{r['status']}  audible={r.get('audible_tones')}  "
          f"neutral_n={r.get('neutral_repeats_usable')}")
    return 0 if r["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
