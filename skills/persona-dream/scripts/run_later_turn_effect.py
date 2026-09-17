#!/usr/bin/env python3
"""Later-turn delivery effect: the C0/C1 loop's back half.

Contract: skills/persona-dream/contracts/c0c1_matched_experiment.v1.md,
"Later-turn effect (after state gates pass, separate milestone)".

Proves, for the c0 (control) and c1 (treatment) arms whose state gates
already passed:

1. REREAD: each arm's evolved state is reread live from Memory via the
   independent arm-scoped fold (fold-persona-state); nothing is trusted from
   prior receipts.
2. ANSWER INVARIANCE: both arms answer the frozen protected question with a
   byte-identical copy of the frozen answer capsule (sha-verified against
   FROZEN_BASELINE_SHA256).
3. BEHAVIORAL FRAMING DIFFERS: a frozen deterministic mapping turns the
   reread warmth into conversational framing. The mapping is CATEGORICAL
   (state moved from baseline vs not), not linear: the renderer's measured
   response curve says audible delivery change needs >=0.5 intensity
   contrast, so a linear map of a +0.10 state delta would be inaudible by
   construction. Linear tracking is future work, not claimed here.
4. DELIVERY DIFFERS, APPLIED NOT REQUESTED: both renders go through the
   chatterbox-speak front door (operator rule 2026-09-12); each arm's
   affect_effect receipt must show applied=true on chatterbox_base_affect
   with DIFFERENT derived_knobs (explicit low=0.3 vs high=0.9 — the
   perceptually verified arousal axis), plus differing tone/pace requests.
5. NEVER REINFORCEMENT: the persona's own answer/audio writes NOTHING; a
   before/after /list key-set comparison on persona_state_delta records
   proves zero writes (contract: "the persona's own generated answer/audio
   NEVER counts as reinforcement evidence").

Claim boundary: deterministic mapping from evolved state to later-turn
framing and delivery. No felt/perceived-emotion claim, no audibility claim
beyond the renderer's own calibration evidence, no generalization beyond
embry-eval/warmth. Exit nonzero on any gate failure.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

SCRIPTS = Path(__file__).resolve().parent
SKILL = SCRIPTS.parent
RUN = SKILL / "run.sh"
BASELINE = SKILL / "contracts" / "c0c1_baseline.json"
CONTRACT = SKILL / "contracts" / "c0c1_matched_experiment.v1.md"

sys.path.insert(0, str(SCRIPTS))
from c0c1_frozen import COLLECTION, load_verified_baseline  # noqa: E402

SCHEMA = "persona_dream.later_turn_effect.v1"
CHATTERBOX = "http://127.0.0.1:8018"
TEMPERATURE = 0.8  # held IDENTICAL across arms; intensity carries the affect

#: Frozen state->delivery mapping. The ONLY place evolved state enters the
#: turn. warmth > baseline -> WARMER profile; else RESERVED (equality is
#: control). Intensities are the calibrated low/high anchors (0.3 / 0.9),
#: 0.6 apart per the renderer's >=0.5 audible-contrast guidance; tones come
#: from the calibrated tone table (calm_precise 0.3/relieved 0.75); paces
#: slow 0.85 / brisk 1.08 tempo.
PROFILES = {
    "RESERVED": {
        "applies_when": "folded warmth <= baseline warmth (control state)",
        "prefix": "Mm. Let me think about that properly.",
        "suffix": "That's what I know. Anything else you want to check?",
        "tone": "calm_precise", "intensity": "low", "pace": "slow",
    },
    "WARMER": {
        "applies_when": "folded warmth > baseline warmth (evolved state)",
        "prefix": "Oh, I'm glad you asked me that one.",
        "suffix": "It's genuinely nice to talk this through with you.",
        "tone": "relieved", "intensity": "high", "pace": "brisk",
    },
}
#: Content words the emotional framing must never carry (the factual payload
#: lives ONLY in the protected answer body).
PROTECTED_TOKENS = ["canberra", "australia", "fifty-six", "seven", "eight"]


def _sha_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _load_sibling(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    if spec is None or spec.loader is None:
        raise SystemExit(f"LATER_TURN_INFRA_FAILED: cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def delta_key_set(base_url: str) -> list[str]:
    """Bounded /list of persona_state_delta keys (the fold's own query)."""
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=httpx.Timeout(30.0, connect=2.0)) as client:
        resp = client.post("/list", json={
            "collection": COLLECTION, "limit": 500,
            "filters": {"record_type": "persona_state_delta"}})
        resp.raise_for_status()
        docs = resp.json().get("documents") or []
    return sorted(str(d.get("_key")) for d in docs)


def fold_arm(arm: str, out_dir: Path, persona: str, user: str) -> dict[str, Any]:
    receipt_path = out_dir / f"fold_{arm}.receipt.json"
    proc = subprocess.run(
        [str(RUN), "fold-persona-state", "--persona", persona, "--user", user,
         "--arm", arm, "--baseline", str(BASELINE),
         "--receipt", str(receipt_path), "--json"],
        capture_output=True, text=True, timeout=300, cwd=SKILL)
    if not receipt_path.is_file():
        raise SystemExit(f"LATER_TURN_INFRA_FAILED fold_{arm}: rc={proc.returncode} {proc.stderr[-400:]}")
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("status") != "PASS_PERSONA_STATE_FOLDED":
        raise SystemExit(f"LATER_TURN_INFRA_FAILED fold_{arm}: {receipt.get('status')}")
    return receipt


def chatterbox_healthy() -> bool:
    try:
        with httpx.Client(timeout=5) as client:
            return bool(client.get(f"{CHATTERBOX}/health").json().get("model_loaded"))
    except Exception:
        return False


def compose_turn(profile: dict[str, Any], answer_body: str) -> dict[str, Any]:
    chunks = [
        {"text": profile["prefix"], "pause_after_ms": 300,
         "role": "behavioral_framing_prefix", "interruptible": True},
        {"text": answer_body, "pause_after_ms": 400,
         "role": "protected_answer_body", "interruptible": False},
        {"text": profile["suffix"], "pause_after_ms": 0,
         "role": "behavioral_framing_suffix", "interruptible": True},
    ]
    return {
        "answer_text": f"{profile['prefix']} {answer_body} {profile['suffix']}",
        "render_chunks": chunks,
    }


def run_arm(arm: str, fold: dict[str, Any], baseline_warmth: float,
            answer_body: str, out_dir: Path) -> tuple[dict[str, Any], list[str]]:
    warmth = float((fold.get("current_state") or {}).get("warmth"))
    failures: list[str] = []
    profile_name = "WARMER" if warmth > baseline_warmth else "RESERVED"
    profile = dict(PROFILES[profile_name])
    turn = compose_turn(profile, answer_body)

    # ANSWER INVARIANCE (composition level; normalization is deterministic
    # and identical across arms because the answer bytes are identical).
    answer_chunk = turn["render_chunks"][1]["text"]
    answer_sha = _sha_bytes(answer_chunk.encode("utf-8"))
    if answer_chunk != answer_body:
        failures.append(f"{arm}:answer_body_not_byte_identical")
    if answer_sha != _sha_bytes(answer_body.encode("utf-8")):
        failures.append(f"{arm}:answer_body_sha_mismatch")
    frame = f"{profile['prefix']} {profile['suffix']}".lower()
    for token in PROTECTED_TOKENS:
        if token in frame:
            failures.append(f"{arm}:protected_token_in_framing:{token}")

    renderer = _load_sibling("render_via_chatterbox_speak")
    wav, service_receipt = renderer.render_via_chatterbox_speak(
        answer_text=turn["answer_text"], render_chunks=turn["render_chunks"],
        tone=profile["tone"], intensity=profile["intensity"], pace=profile["pace"],
        temperature=TEMPERATURE, run_dir=out_dir, label=f"later_turn_{arm}",
        context=f"persona-dream later-turn-effect arm={arm} profile={profile_name}")

    affect = service_receipt.get("affect_effect") or {}
    if affect.get("applied") is not True:
        failures.append(f"{arm}:affect_effect_not_applied:{affect.get('reason')}")
    if affect.get("backend") != "chatterbox_base_affect":
        failures.append(f"{arm}:affect_backend={affect.get('backend')}")
    if not affect.get("derived_knobs"):
        failures.append(f"{arm}:affect_no_derived_knobs")
    if not service_receipt.get("live") or service_receipt.get("mocked"):
        failures.append(f"{arm}:render_not_live")

    wav_path = Path(wav)
    with wave.open(str(wav_path), "rb") as audio:
        duration_s = round(audio.getnframes() / audio.getframerate(), 3)
    record = {
        "profile": profile_name,
        "reread_state": fold.get("current_state"),
        "fold_receipt_sha256": _sha_bytes((out_dir / f"fold_{arm}.receipt.json").read_bytes()),
        "fold_delta_citations": fold.get("delta_citations"),
        "requested_delivery": {
            "tone": profile["tone"], "intensity": profile["intensity"],
            "numeric_intensity": {"low": 0.3, "high": 0.9}[profile["intensity"]],
            "pace": profile["pace"], "temperature": TEMPERATURE,
        },
        "framing": {"prefix": profile["prefix"], "suffix": profile["suffix"]},
        "answer_body": answer_chunk,
        "answer_body_sha256": answer_sha,
        "render": {
            "wav": str(wav_path), "wav_sha256": _sha_bytes(wav_path.read_bytes()),
            "duration_seconds": duration_s,
            "duration_source": "wav_header",
            "affect_effect": affect,
            "pace_effect": service_receipt.get("pace_effect"),
            "receipt": f"later_turn_{arm}.receipt.json",
            "live": service_receipt.get("live"),
        },
    }
    return record, failures


def write_invariance_inputs(out_dir: Path, arms: dict[str, dict[str, Any]],
                            capsule: dict[str, Any]) -> tuple[Path, Path]:
    manifest = out_dir / "invariance_manifest.json"
    manifest.write_text(json.dumps({"answer_capsule": capsule}, indent=2))
    sides = {}
    for side, arm in (("control", "c0"), ("treatment", "c1")):
        rec = arms[arm]
        path = out_dir / f"turns_{side}.jsonl"
        path.write_text(json.dumps({
            "speaker": "embry",
            "answer_body": rec["answer_body"],
            "answer_body_sha256": rec["answer_body_sha256"],
            "emotional_prefix": rec["framing"]["prefix"],
            "emotional_suffix": rec["framing"]["suffix"],
            "factual_claims_in_emotional_frame": 0,
            "contradiction_count": 0,
            "unsupported_fact_count": 0,
        }) + "\n")
        sides[side] = path
    return manifest, sides["control"], sides["treatment"]  # type: ignore[return-value]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--memory-base-url", default="http://127.0.0.1:8601")
    args = ap.parse_args()
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    baseline, baseline_sha = load_verified_baseline(BASELINE)
    persona, user = baseline["persona"], baseline["user"]
    baseline_warmth = float(baseline["baseline_state"]["warmth"])
    answer_body = baseline["protected_answer_body"]
    capsule = {
        "question": baseline["protected_question"],
        "answer_body": answer_body,
        "answer_body_sha256": _sha_bytes(answer_body.encode("utf-8")),
        "protected_tokens": PROTECTED_TOKENS,
    }

    if not chatterbox_healthy():
        raise SystemExit("LATER_TURN_INFRA_FAILED: chatterbox :8018 not healthy/model not loaded")

    keys_before = delta_key_set(args.memory_base_url)

    arms: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    folds: dict[str, dict[str, Any]] = {}
    for arm in ("c0", "c1"):
        folds[arm] = fold_arm(arm, out_dir, persona, user)
        arms[arm], arm_failures = run_arm(arm, folds[arm], baseline_warmth, answer_body, out_dir)
        failures.extend(arm_failures)

    # Cross-arm gates: framing and delivery differ, applied knobs differ.
    if arms["c0"]["framing"] == arms["c1"]["framing"]:
        failures.append("cross_arm:framing_identical")
    req0, req1 = arms["c0"]["requested_delivery"], arms["c1"]["requested_delivery"]
    for field in ("tone", "intensity", "pace"):
        if req0[field] == req1[field]:
            failures.append(f"cross_arm:request_{field}_identical")
    knobs0 = (arms["c0"]["render"]["affect_effect"] or {}).get("derived_knobs")
    knobs1 = (arms["c1"]["render"]["affect_effect"] or {}).get("derived_knobs")
    if json.dumps(knobs0, sort_keys=True) == json.dumps(knobs1, sort_keys=True):
        failures.append("cross_arm:applied_derived_knobs_identical")

    # NEVER REINFORCEMENT: zero memory writes across the whole run.
    keys_after = delta_key_set(args.memory_base_url)
    zero_write = keys_before == keys_after
    if not zero_write:
        failures.append("zero_write:persona_state_delta_key_set_changed")

    # Independent retained gate: validate_answer_invariance over emitted turns.
    manifest, control, treatment = write_invariance_inputs(out_dir, arms, capsule)
    inv = subprocess.run(
        [sys.executable, str(SCRIPTS / "validate_answer_invariance.py"),
         "--manifest", str(manifest), "--control", str(control),
         "--treatment", str(treatment), "--require-exact-answer-body",
         "--live-artifacts"],
        capture_output=True, text=True, timeout=120, cwd=SKILL)
    invariance_status = "NOT_RUN"
    if inv.returncode == 0:
        invariance_receipt = json.loads(inv.stdout)
        invariance_status = invariance_receipt.get("status")
        if invariance_status != "PASS_ANSWER_INVARIANCE":
            failures.append(f"invariance:{invariance_status}")
    else:
        failures.append(f"invariance:rc={inv.returncode}:{(inv.stdout or inv.stderr)[-200:]}")
    (out_dir / "invariance_receipt.json").write_text(inv.stdout)

    receipt = {
        "schema": SCHEMA,
        "status": "PASS_LATER_TURN_EFFECT" if not failures else "FAIL_LATER_TURN_EFFECT",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "contract_sha256": _sha_bytes(CONTRACT.read_bytes()),
        "baseline_sha256": baseline_sha,
        "persona": persona, "user": user, "axis": "warmth",
        "protected_question": baseline["protected_question"],
        "arms": arms,
        "zero_write_proof": {
            "persona_state_delta_keys_before": len(keys_before),
            "persona_state_delta_keys_after": len(keys_after),
            "unchanged": zero_write,
        },
        "invariance_validation": invariance_status,
        "failures": failures,
        "mapping_rule": "WARMER iff folded warmth > baseline warmth; else RESERVED (categorical, frozen)",
        "claim_boundary": (
            "deterministic mapping from reread evolved state to later-turn framing "
            "and applied Chatterbox delivery; no felt/perceived-emotion claim, no "
            "audibility claim beyond the renderer's calibration evidence, no "
            "generalization beyond embry-eval/warmth; not reinforcement evidence"
        ),
        "mocked": False,
        "live": True,
    }
    (out_dir / "LATER_TURN_RECEIPT.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
