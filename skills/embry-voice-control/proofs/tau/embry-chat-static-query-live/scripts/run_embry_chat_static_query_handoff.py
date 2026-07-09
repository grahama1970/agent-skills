"""Run the Embry static-query proof and emit a Tau handoff.

The command is meant to be invoked by Tau as a local command_spec node. It
consumes the Tau start handoff on stdin, runs the live Embry voice-control proof,
writes wrapper evidence receipts, and prints exactly one tau.agent_handoff.v1
JSON object to stdout.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any
from uuid import uuid4


SKILL_ROOT = Path("/home/graham/workspace/experiments/agent-skills/skills/embry-voice-control")
OUTPUT_ROOT = Path("/mnt/storage12tb/skills/embry-voice-control/outputs/e2e/embry-chat-static-query-live-tau")
LATEST_EMBRY_PROOF = Path(
    "/mnt/storage12tb/skills/embry-voice-control/outputs/e2e/embry-chat-static-query-live/latest.json"
)


def utc_stamp() -> str:
    """Return an ISO UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from disk."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write a JSON object to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_start_handoff() -> dict[str, Any]:
    """Load Tau start handoff from stdin."""
    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("Tau start handoff stdin was empty")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Tau start handoff stdin did not contain a JSON object")
    return data


def run_embry_proof() -> subprocess.CompletedProcess[str]:
    """Run the existing live Embry Chat static query proof."""
    command = [
        str(SKILL_ROOT / "run.sh"),
        "embry-chat-static-query-live",
        "--play-local",
        "--local-playback-target",
        "64",
    ]
    return subprocess.run(
        command,
        cwd=str(SKILL_ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
        check=False,
    )


def build_persistent_subagent_receipt(
    *,
    run_dir: Path,
    start_handoff: dict[str, Any],
) -> Path:
    """Write a receipt proving Tau propagated the persistent subagent contract."""
    context = start_handoff.get("context") if isinstance(start_handoff.get("context"), dict) else {}
    persistent = context.get("persistent_subagent") if isinstance(context.get("persistent_subagent"), dict) else {}
    path = run_dir / "persistent_subagent_receipt.json"
    receipt = {
        "schema": "tau.persistent_subagent_receipt.v1",
        "mocked": False,
        "live": True,
        "created_at": utc_stamp(),
        "surface_declared": bool(persistent),
        "surface_reachable_checked": False,
        "surface_reachable_required_for_this_rung": False,
        "persistent_subagent": persistent,
        "claims": {
            "proves": [
                "Tau propagated a persistent Embry voice surface declaration into the node handoff context."
            ],
            "does_not_prove": [
                "UX route reachability.",
                "Chat UX rendering.",
                "Orb sync.",
                "Browser audio behavior."
            ],
        },
    }
    write_json(path, receipt)
    return path


def build_wrapper_receipt(
    *,
    run_dir: Path,
    start_handoff: dict[str, Any],
    completed: subprocess.CompletedProcess[str],
    latest: dict[str, Any] | None,
    persistent_receipt_path: Path,
) -> Path:
    """Write a Tau wrapper receipt summarizing the live proof command."""
    path = run_dir / "tau_embry_chat_static_query_wrapper_receipt.json"
    receipt = {
        "schema": "embry.voice.tau_static_query_wrapper_receipt.v1",
        "mocked": False,
        "live": True,
        "created_at": utc_stamp(),
        "start_goal": start_handoff.get("goal"),
        "command": completed.args,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "latest_embry_proof": latest,
        "persistent_subagent_receipt": str(persistent_receipt_path),
        "acceptance": {
            "pass": bool(latest and latest.get("pass") is True and completed.returncode == 0),
            "embry_chat_turn_receipt": latest.get("receipt_path") if latest else None,
            "chatterbox_audio_receipt": latest.get("audio_path") if latest else None,
            "pipewire_playback_receipt": latest.get("local_playback") if latest else None,
        },
    }
    write_json(path, receipt)
    return path


def main() -> int:
    """Entrypoint for Tau command_spec execution."""
    start_handoff = load_start_handoff()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-tau-embry-chat-" + uuid4().hex[:8]
    run_dir = OUTPUT_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    persistent_receipt_path = build_persistent_subagent_receipt(
        run_dir=run_dir,
        start_handoff=start_handoff,
    )
    completed = run_embry_proof()
    latest = read_json(LATEST_EMBRY_PROOF) if LATEST_EMBRY_PROOF.exists() else None
    wrapper_receipt_path = build_wrapper_receipt(
        run_dir=run_dir,
        start_handoff=start_handoff,
        completed=completed,
        latest=latest,
        persistent_receipt_path=persistent_receipt_path,
    )
    ok = bool(latest and latest.get("pass") is True and completed.returncode == 0)
    goal = start_handoff.get("goal") if isinstance(start_handoff.get("goal"), dict) else {}
    github = start_handoff.get("github") if isinstance(start_handoff.get("github"), dict) else {}
    evidence = [
        f"persistent_subagent_receipt:{persistent_receipt_path}",
        f"embry_chat_turn_receipt.v1:{latest.get('receipt_path') if latest else ''}",
        f"chatterbox_audio_receipt:{latest.get('audio_path') if latest else ''}",
        f"pipewire_playback_receipt:{json.dumps(latest.get('local_playback'), sort_keys=True) if latest else ''}",
        f"tau_wrapper_receipt:{wrapper_receipt_path}",
    ]
    status = "COMPLETED" if ok else "BLOCKED"
    summary = (
        "Embry Chat static query proof passed through memory-first Tau route and Chatterbox playback."
        if ok
        else "Embry Chat static query proof did not produce all required evidence."
    )
    handoff = {
        "schema": "tau.agent_handoff.v1",
        "github": github,
        "goal": goal,
        "previous_subagent": "embry-chatterbox",
        "context": {
            "summary": "Embry persistent voice subagent static-query proof result.",
            "artifacts": [
                str(persistent_receipt_path),
                str(wrapper_receipt_path),
                str(latest.get("receipt_path")) if latest and latest.get("receipt_path") else "",
                str(latest.get("audio_path")) if latest and latest.get("audio_path") else "",
            ],
        },
        "result": {
            "status": status,
            "summary": summary,
            "evidence": evidence,
        },
        "rationale": "The first operational Embry DAG wraps the already-passing static query rung only.",
        "next_agent": {
            "name": "human",
            "executor": "human",
            "reason": "Human reviews the Tau DAG receipt before adding Chat UX, orb, replay, or interruption rungs.",
        },
        "required_evidence": [
            "Human accepts the DAG receipt or requests the next bounded Embry voice rung."
        ],
        "stop_condition": "Stop after the static query DAG node emits all required evidence or blocks.",
    }
    print(json.dumps(handoff, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
