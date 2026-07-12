"""One-case physical managed-listener execution for the audio E2E ladder."""

from __future__ import annotations

from contextlib import AbstractContextManager
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from .event_waiter import wait_for_managed_turn


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class ManagedListenerProcess(AbstractContextManager["ManagedListenerProcess"]):
    def __init__(self, config: dict[str, Any], turn_count: int) -> None:
        self.config = config
        self.turn_count = turn_count
        self.process: subprocess.Popen[str] | None = None
        self.socket = Path(config["managed_listener_socket"])

    def __enter__(self) -> "ManagedListenerProcess":
        self.socket.parent.mkdir(parents=True, exist_ok=True)
        self.socket.unlink(missing_ok=True)
        repo = Path(self.config["realtimestt_repo"])
        command = [
            self.config["realtimestt_python"],
            str(repo / "proofs/embry_pipewire_ingress/run_physical_hot_mic_listener.py"),
            "--run-dir", str(Path(self.config["campaign_dir"]) / "managed-listener"),
            "--source-node", self.config["listener_source_node"],
            "--event-service-url", self.config["journal_url"].rstrip("/") + "/v1/listener/events",
            "--managed-socket", str(self.socket),
            "--target-cycles", str(self.turn_count),
            "--cycles-this-run", str(self.turn_count),
            "--max-attempts-this-run", str(max(8, self.turn_count * 4)),
            "--restart-capture-after-cycle", "0",
            "--model", "small.en",
            "--realtime-model", "tiny.en",
            "--device", self.config["listener_device"],
            "--compute-type", self.config["listener_compute_type"],
        ]
        log_path = Path(self.config["campaign_dir"]) / "managed-listener.log"
        self._log = log_path.open("w", encoding="utf-8")
        self.process = subprocess.Popen(command, stdout=self._log, stderr=subprocess.STDOUT, text=True)
        deadline = time.monotonic() + self.config["listener_start_timeout_seconds"]
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"managed_listener_exited:{self.process.returncode}:{log_path}")
            if self.socket.exists():
                return self
            time.sleep(0.1)
        raise TimeoutError(f"managed_listener_socket_timeout:{self.socket}")

    def arm(self, command: dict[str, Any]) -> dict[str, Any]:
        protocol_dir = Path(self.config["realtimestt_repo"]) / "proofs/embry_pipewire_ingress"
        sys.path.insert(0, str(protocol_dir))
        try:
            from managed_turn_protocol import send_arm_command
            return send_arm_command(self.socket, command)
        finally:
            sys.path.remove(str(protocol_dir))

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self._log.close()


class CaseExecutor:
    def __init__(self, config: dict[str, Any], listener: ManagedListenerProcess) -> None:
        self.config = config
        self.listener = listener

    def execute_listener_turns(self, campaign_id: str, case: dict[str, Any]) -> list[dict[str, Any]]:
        receipts: list[dict[str, Any]] = []
        source_audio = [Path(path) for path in self.config.get("turn_audio", [])]
        if source_audio and len(source_audio) != len(case["turn_script"]):
            raise ValueError("turn_audio_count_mismatch")
        for turn_offset, turn in enumerate(case["turn_script"]):
            authority_seed = {
                "campaign_id": campaign_id,
                "case_id": case["case_id"],
                "attempt_id": case["attempt_id"],
                "session_id": case["session_id"],
                "turn_id": turn["turn_id"],
            }
            source_authority_id = "physical-horus:" + hashlib.sha256(_canonical(authority_seed)).hexdigest()[:24]
            expected = {**authority_seed, "source_authority_id": source_authority_id}
            ack = self.listener.arm({
                "schema": "embry.listener_turn_command.v1",
                "command": "arm",
                **expected,
                "wake_required": True,
            })
            if not ack.get("armed"):
                raise RuntimeError("managed_listener_arm_rejected")
            print(
                json.dumps({
                    "status": "AWAITING_HUMAN_SPEECH",
                    "case_id": case["case_id"],
                    "turn_id": turn["turn_id"],
                    "say_exactly": turn.get("spoken_text", turn["utterance"]),
                }),
                flush=True,
            )
            source_process = None
            if source_audio:
                audio_path = source_audio[turn_offset]
                if not audio_path.is_file():
                    raise FileNotFoundError(f"turn_audio_missing:{audio_path}")
                time.sleep(self.config["source_playback_delay_seconds"])
                source_process = subprocess.Popen(
                    [
                        self.config["pw_play"],
                        "--target", self.config["source_playback_target"],
                        str(audio_path),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            chain = wait_for_managed_turn(
                Path(self.config["journal_db"]),
                session_id=case["session_id"],
                expected=expected,
                timeout_seconds=self.config["turn_timeout_seconds"],
            )
            if source_process is not None:
                _, source_stderr = source_process.communicate(timeout=15)
                if source_process.returncode != 0:
                    raise RuntimeError(f"source_playback_failed:{source_process.returncode}:{source_stderr}")
            final = chain["listener.final_transcript"]
            receipts.append({
                "turn_id": turn["turn_id"],
                "display_text_sha256": turn.get("display_text_sha256", turn["utterance_sha256"]),
                "expected_spoken_text_sha256": turn.get("spoken_text_sha256", turn["utterance_sha256"]),
                "source_authority_id": source_authority_id,
                "arm_event_id": chain["listener.turn_armed"]["event_id"],
                "final_event_id": final["event_id"],
                "final_sequence": final["sequence"],
                "request_text": final["payload"].get("request_text"),
                "audio_path": final["payload"].get("audio_path"),
                "audio_sha256": final["payload"].get("audio_sha256"),
                "completed_event_id": chain["listener.turn_completed"]["event_id"],
                "live": final["live"],
                "mocked": final["mocked"],
                "source_audio_path": str(source_audio[turn_offset]) if source_audio else None,
            })
        return receipts
