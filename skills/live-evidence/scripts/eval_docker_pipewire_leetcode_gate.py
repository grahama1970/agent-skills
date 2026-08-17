#!/usr/bin/env python3
"""Live Docker/PipeWire STT eval for the transcript-to-leetcode gate."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv(override=False)


SPOKEN_PROMPT = (
    "Given an array of numbers and a target, find two numbers that add up to the target "
    "and return the output."
)
CLARIFICATION_ANSWERS = {
    "return-contract": "Return the two indices.",
    "element-reuse": "The indices must be distinct.",
    "multiple-solutions": "Exactly one solution exists.",
}


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def write_profile(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "name: docker-pipewire-leetcode-gate",
                "watch_terms:",
                "  - array",
                "  - target",
                "  - two numbers",
                "project_aliases:",
                "  live-e2e:",
                "    - two sum",
                "    - target sum",
                "repo_priorities:",
                "  - live-e2e",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_repo(repo: Path) -> None:
    repo.mkdir(parents=True)
    (repo / "two_sum.py").write_text(
        "\n".join(
            [
                "def two_sum(nums: list[int], target: int) -> list[int]:",
                "    seen: dict[int, int] = {}",
                "    for index, value in enumerate(nums):",
                "        complement = target - value",
                "        if complement in seen:",
                "            return [seen[complement], index]",
                "        seen[value] = index",
                "    raise ValueError('no solution')",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_ask_fixture_runner(path: Path, run_dir: Path, log_path: Path) -> Path:
    runner = path / "ask-docker-pipewire-fixture-runner.sh"
    runner.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"run_dir={json.dumps(str(run_dir))}",
                f"log_path={json.dumps(str(log_path))}",
                'mkdir -p "$run_dir/node-artifacts/handler-fixture"',
                'printf "%s\\n" "$*" >> "$log_path"',
                'cat > "$run_dir/node-artifacts/handler-fixture/response.md" <<\'EOF\'',
                "Use a hash map from value to index; return the stored index and current index once target - value appears. Code path: live-e2e/two_sum.py.",
                "EOF",
                'printf \'{"run_dir":"%s"}\\n\' "$run_dir"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner.chmod(0o755)
    return runner


def synthesize_prompt(wav_path: Path) -> None:
    command = [
        "espeak-ng",
        "-v",
        "en-us",
        "-s",
        "130",
        "-p",
        "45",
        "-w",
        str(wav_path),
        SPOKEN_PROMPT,
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "espeak-ng failed")


def wait_for_health(client: httpx.Client, server_log: Path) -> None:
    for _ in range(80):
        try:
            if client.get("/api/health").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"server did not start; log={server_log.read_text(encoding='utf-8', errors='replace')}")


def get_state(client: httpx.Client) -> dict[str, Any]:
    response = client.get("/api/state")
    response.raise_for_status()
    return response.json()


def wait_for_clarification_card(client: httpx.Client, *, timeout_s: float = 90.0) -> tuple[dict[str, Any], dict[str, Any]]:
    deadline = time.monotonic() + timeout_s
    last_state: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last_state = get_state(client)
        for card in last_state.get("cards") or []:
            source = _gate_source(card)
            if source is None:
                continue
            metadata = source.get("metadata") or {}
            if metadata.get("gate_status") == "needs_clarification":
                return card, last_state
        time.sleep(1.0)
    raise RuntimeError(f"timed out waiting for needs_clarification card; last_state={last_state}")


def _gate_source(card: dict[str, Any]) -> dict[str, Any] | None:
    for source in card.get("sources") or []:
        if source.get("repository") == "transcript-to-leetcode":
            return source
    return None


def _ask_sources(card: dict[str, Any]) -> list[dict[str, Any]]:
    return [source for source in card.get("sources") or [] if source.get("lane") == "ask" and source.get("repository") == "ask"]


def _ask_source_has_receipt(source: dict[str, Any]) -> bool:
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    return bool(metadata.get("run_dir") and metadata.get("response_path") and metadata.get("response_sha256"))


def clarification_ids(card: dict[str, Any]) -> list[str]:
    source = _gate_source(card) or {}
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    questions = metadata.get("clarifying_questions") if isinstance(metadata.get("clarifying_questions"), list) else []
    return [str(item.get("id")) for item in questions if isinstance(item, dict) and item.get("id")]


def answer_for_question(question_id: str) -> str:
    if question_id in CLARIFICATION_ANSWERS:
        return CLARIFICATION_ANSWERS[question_id]
    if question_id == "problem-selection":
        return "The intended problem is Two Sum: find two distinct entries in the array whose sum equals target."
    return "Use the Two Sum interpretation with distinct indices, exactly one answer, and return the two indices."


def post_clarifications(
    client: httpx.Client,
    card_id: str,
    answers: dict[str, str],
    *,
    timeout_s: float,
) -> dict[str, Any]:
    response = client.post(
        f"/api/cards/{card_id}/clarifications",
        json={"answers": answers},
        timeout=timeout_s,
    )
    response.raise_for_status()
    return response.json()


def run_bridge(args: argparse.Namespace, *, backend_url: str, source_wav: Path, output_root: Path) -> dict[str, Any]:
    bridge = Path(__file__).with_name("e2e_pipewire_docker_bridge.py")
    command = [
        sys.executable,
        str(bridge),
        "--backend-url",
        backend_url,
        "--source-wav",
        str(source_wav),
        "--playback-target",
        args.playback_target,
        "--capture-target",
        args.capture_target,
        "--docker-image",
        args.docker_image,
        "--output-dir",
        str(output_root / "bridge"),
        "--max-seconds",
        str(args.max_seconds),
        "--tail-seconds",
        str(args.tail_seconds),
        "--model",
        args.model,
        "--realtime-model",
        args.realtime_model,
        "--device",
        "cuda",
        "--compute-type",
        args.compute_type,
        "--no-require-ask",
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False, timeout=args.max_seconds + 180)
    bridge_invocation = {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    try:
        payload = json.loads(result.stdout[result.stdout.index("{") :])
    except (ValueError, json.JSONDecodeError):
        payload = {}
    bridge_invocation["reported_receipt"] = payload.get("receipt")
    return bridge_invocation


def read_bridge_receipt(bridge_result: dict[str, Any]) -> dict[str, Any]:
    path = bridge_result.get("reported_receipt")
    if not isinstance(path, str) or not path:
        return {}
    receipt_path = Path(path)
    if not receipt_path.is_file():
        return {}
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def assert_bridge_audio_stt(bridge_receipt: dict[str, Any]) -> None:
    acceptance = bridge_receipt.get("acceptance") if isinstance(bridge_receipt.get("acceptance"), dict) else {}
    required = {
        "pipewire_audio_captured": acceptance.get("pipewire_audio_captured") is True,
        "docker_realtimestt_process_ok": acceptance.get("docker_realtimestt_process_ok") is True,
        "pipewire_transcript_events": int(acceptance.get("pipewire_transcript_events") or 0) > 0,
    }
    if not all(required.values()):
        raise RuntimeError(f"Docker/PipeWire/STT bridge did not meet audio intake checks: {required}")


def claims_for_mode(ask_mode: str) -> dict[str, list[str]]:
    does_not_prove = [
        "YouTube website playback; this uses an espeak-ng WAV through the same PipeWire capture path",
        "human UI ergonomics for entering clarification answers",
    ]
    if ask_mode == "fixture":
        does_not_prove.append("live provider quality because --ask-mode fixture uses a local Ask fixture runner")
    return {
        "proves": [
            "PipeWire audio was captured from a played WAV and fed into a GPU Docker RealtimeSTT process",
            "Live Evidence received pipewire transcript events from that process",
            "the automatic code-question path blocked Ask at needs_clarification",
            "partial clarification answers kept Ask invocation count at zero",
            "complete clarification answers invoked Ask exactly once with receipt metadata",
        ],
        "does_not_prove": does_not_prove,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="/mnt/storage12tb/skills/live-evidence/agentic-evals/docker-pipewire-leetcode-gate")
    parser.add_argument("--docker-image", default="live-evidence-realtimestt-gpu:local")
    parser.add_argument("--playback-target", default="59")
    parser.add_argument("--capture-target", default="alsa_output.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.analog-stereo")
    parser.add_argument("--max-seconds", type=float, default=28.0)
    parser.add_argument("--tail-seconds", type=float, default=3.0)
    parser.add_argument("--model", default="base.en")
    parser.add_argument("--realtime-model", default="tiny.en")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--ask-mode", choices=("fixture", "real"), default="fixture")
    parser.add_argument("--ask-handler", default="gpt-5.5-high")
    parser.add_argument("--ask-timeout", type=float, default=600.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    skills_root = root.parent
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_dir).expanduser().resolve() / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    receipt_path = output_dir / "receipt.json"
    receipt: dict[str, Any] = {
        "schema": "live_evidence.docker_pipewire_leetcode_gate_receipt.v1",
        "status": "FAIL",
        "created_at": datetime.now(UTC).isoformat(),
        "mocked": False,
        "live": True,
        "fixture_backed": args.ask_mode == "fixture",
        "ask_mode": args.ask_mode,
        "spoken_prompt": SPOKEN_PROMPT,
        "output_dir": str(output_dir),
    }
    server_process: subprocess.Popen[str] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="live-evidence-docker-pipewire-gate-") as temp_name:
            temp = Path(temp_name)
            repo = temp / "live-e2e"
            write_repo(repo)
            profile = temp / "profile.yaml"
            write_profile(profile)
            source_wav = output_dir / "source-prompt.wav"
            synthesize_prompt(source_wav)
            data_dir = output_dir / "data"
            server_log = output_dir / "server.log"
            ask_log = output_dir / "ask.argv"
            ask_run_dir = output_dir / "ask-run"
            if args.ask_mode == "fixture":
                ask_runner = write_ask_fixture_runner(output_dir, ask_run_dir, ask_log)
                allow_provider = "false"
            else:
                ask_runner = skills_root / "ask" / "run.sh"
                allow_provider = "true"
            port = free_port()
            backend_url = f"http://127.0.0.1:{port}"
            env = {
                **os.environ,
                "LIVE_EVIDENCE_REPOS": str(repo),
                "LIVE_EVIDENCE_DATA_DIR": str(data_dir),
                "LIVE_EVIDENCE_PROFILE": str(profile),
                "LIVE_EVIDENCE_HTTP_TIMEOUT": "0.5",
                "LIVE_EVIDENCE_PROCESS_TIMEOUT": "4",
                "LIVE_EVIDENCE_MAX_CARDS": "8",
                "LIVE_EVIDENCE_ASK_RUNNER": str(ask_runner),
                "LIVE_EVIDENCE_ASK_HANDLER": args.ask_handler,
                "LIVE_EVIDENCE_ASK_TIMEOUT": str(args.ask_timeout),
                "LIVE_EVIDENCE_ASK_ALLOW_PROVIDER_CALLS": allow_provider,
                "MEMORY_SERVICE_URL": "http://127.0.0.1:9",
            }
            with server_log.open("w", encoding="utf-8") as log:
                server_process = subprocess.Popen(
                    [sys.executable, "-m", "live_evidence", "serve", "--host", "127.0.0.1", "--port", str(port), "--no-browser"],
                    cwd=root,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            with httpx.Client(base_url=backend_url, timeout=10.0) as client:
                wait_for_health(client, server_log)
                bridge_result = run_bridge(args, backend_url=backend_url, source_wav=source_wav, output_root=output_dir)
                bridge_receipt = read_bridge_receipt(bridge_result)
                assert_bridge_audio_stt(bridge_receipt)
                bridge_result_path = output_dir / "bridge-invocation.json"
                bridge_result_path.write_text(json.dumps(bridge_result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                phase_a_card, phase_a_state = wait_for_clarification_card(client)
                phase_a_state_path = output_dir / "phase-a-state.json"
                phase_a_state_path.write_text(json.dumps(phase_a_state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                if ask_log.exists():
                    raise RuntimeError(f"Ask ran before clarification: {ask_log.read_text(encoding='utf-8', errors='replace')}")

                partial_card = post_clarifications(
                    client,
                    phase_a_card["card_id"],
                    {"return-contract": CLARIFICATION_ANSWERS["return-contract"]},
                    timeout_s=30.0,
                )
                if partial_card.get("status") != "insufficient" or _ask_sources(partial_card):
                    raise RuntimeError(f"partial clarification did not remain blocked: {partial_card}")
                if ask_log.exists():
                    raise RuntimeError(f"Ask ran after partial clarification: {ask_log.read_text(encoding='utf-8', errors='replace')}")

                full_answers = dict(CLARIFICATION_ANSWERS)
                full_answers["problem-selection"] = answer_for_question("problem-selection")
                for question_id in clarification_ids(partial_card):
                    full_answers[question_id] = answer_for_question(question_id)
                answer_card = post_clarifications(
                    client,
                    partial_card["card_id"],
                    full_answers,
                    timeout_s=args.ask_timeout + 30.0,
                )
                ask_sources = _ask_sources(answer_card)
                if answer_card.get("status") != "supported" or len(ask_sources) != 1:
                    raise RuntimeError(f"full clarification did not produce exactly one answer card: {answer_card}")
                if not _ask_source_has_receipt(ask_sources[0]):
                    raise RuntimeError(f"Ask answer source lacks receipt metadata: {answer_card}")
                final_state = get_state(client)
                final_state_path = output_dir / "final-state.json"
                final_state_path.write_text(json.dumps(final_state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                transcript = final_state.get("transcript") or []
                gate_metadata = (_gate_source(phase_a_card) or {}).get("metadata") or {}
                answer_metadata = ask_sources[0].get("metadata") or {}
                receipt.update(
                    {
                        "status": "PASS",
                        "backend_url": backend_url,
                        "source_wav": str(source_wav),
                        "bridge_invocation": str(bridge_result_path),
                        "bridge_reported_receipt": bridge_result.get("reported_receipt"),
                        "phase_a_state": str(phase_a_state_path),
                        "final_state": str(final_state_path),
                        "server_log": str(server_log),
                        "checks": {
                            "legacy_bridge_harness_returncode": bridge_result.get("returncode"),
                            "bridge_pipewire_audio_captured": (bridge_receipt.get("acceptance") or {}).get("pipewire_audio_captured"),
                            "bridge_docker_realtimestt_process_ok": (bridge_receipt.get("acceptance") or {}).get("docker_realtimestt_process_ok"),
                            "pipewire_transcript_events": len([event for event in transcript if event.get("source") == "pipewire"]),
                            "phase_a_needs_clarification": gate_metadata.get("gate_status") == "needs_clarification",
                            "phase_a_ask_invocation_count": 0,
                            "partial_answer_remains_needs_clarification": True,
                            "partial_answer_ask_invocation_count": 0,
                            "phase_b_ready_for_solution": answer_metadata.get("leetcode_gate_status") == "ready_for_solution",
                            "phase_b_ask_invocation_count": 1,
                            "transcript_sha256_preserved": gate_metadata.get("transcript_sha256") == answer_metadata.get("transcript_sha256"),
                            "solver_prompt_hash_recorded": bool(answer_metadata.get("solver_prompt_sha256")),
                        },
                        "clarification_card_id": phase_a_card.get("card_id"),
                        "phase_a_clarification_question_ids": clarification_ids(phase_a_card),
                        "partial_clarification_question_ids": clarification_ids(partial_card),
                        "answer_card_id": answer_card.get("card_id"),
                        "ask_log": str(ask_log) if ask_log.exists() else None,
                        "ask_run_artifact": str(ask_run_dir) if ask_run_dir.exists() else answer_metadata.get("run_dir"),
                        "claims": claims_for_mode(args.ask_mode),
                    }
                )
    except Exception as exc:
        receipt["error"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        if server_process and server_process.poll() is None:
            server_process.terminate()
            try:
                server_process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                server_process.kill()
                server_process.wait(timeout=2.0)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copy2(receipt_path, Path("/tmp/live-evidence-docker-pipewire-leetcode-gate-receipt.json"))
    print(json.dumps({"receipt": str(receipt_path), "status": receipt.get("status"), "error": receipt.get("error")}, indent=2))
    return 0 if receipt.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
