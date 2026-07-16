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

from .asr_comparison import compare_asr_text
from .event_waiter import (
    journal_sequence_boundary,
    wait_for_managed_turn,
    wait_for_managed_wake,
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _request_wer(expected_spoken_text: str, actual_request_text: str) -> float:
    return float(compare_asr_text(
        expected_spoken_text,
        actual_request_text,
    )["comparison_wer"])


class ManagedListenerProcess(AbstractContextManager["ManagedListenerProcess"]):
    def __init__(
        self,
        config: dict[str, Any],
        *,
        target_turn_count: int,
        turns_this_run: int,
    ) -> None:
        self.config = config
        self.target_turn_count = target_turn_count
        self.turns_this_run = turns_this_run
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
            "--target-cycles", str(self.target_turn_count),
            "--cycles-this-run", str(self.turns_this_run),
            "--max-attempts-this-run", str(max(8, self.turns_this_run * 4)),
            "--restart-capture-after-cycle", "0",
            "--model", "small.en",
            "--realtime-model", "tiny.en",
            "--device", self.config["listener_device"],
            "--compute-type", self.config["listener_compute_type"],
            "--post-speech-silence-duration",
            str(self.config["listener_post_speech_silence_seconds"]),
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

    @staticmethod
    def _source_authority(
        campaign_id: str,
        case: dict[str, Any],
        turn: dict[str, Any],
        source_asset: dict[str, Any] | None,
    ) -> tuple[str, dict[str, Any]]:
        source_mode = str(case.get("source_mode") or "")
        fresh_physical = source_mode == "physical_live_horus"
        physical_identity_mode = source_mode in {
            "physical_live_horus",
            "recorded_physical_horus",
        }
        if source_mode == "physical_live_horus":
            prefix = "physical-horus"
            source_contract = "physical_horus_identity"
        elif source_mode == "recorded_physical_horus":
            prefix = "recorded-physical-horus"
            source_contract = "physical_horus_identity"
        elif source_mode in {
            "qualified_horus_clone",
            "qualified_horus_audio",
        }:
            prefix = "qualified-horus-clone"
            source_contract = "qualified_horus_clone"
        else:
            raise ValueError(f"source_mode_not_executable:{source_mode}")
        authority_seed = {
            "campaign_id": campaign_id,
            "case_id": case["case_id"],
            "attempt_id": case["attempt_id"],
            "session_id": case["session_id"],
            "turn_id": turn["turn_id"],
            "source_mode": source_mode,
            "source_contract": source_contract,
            "source_audio_sha256": (
                ((source_asset or {}).get("audio") or {}).get("sha256")
            ),
        }
        source_authority_id = (
            prefix + ":" + hashlib.sha256(_canonical(authority_seed)).hexdigest()[:24]
        )
        return source_authority_id, {
            **authority_seed,
            "source_authority_id": source_authority_id,
            "fresh_physical_human_speech": fresh_physical,
            # Listener/ASR proves audio lineage only.  Physical identity and
            # personal-memory permission are resolved later from the exact
            # turn's speaker.verification.completed event.
            "speaker_identity_proven": False,
            "speaker_identity_verification_required": physical_identity_mode,
            "allow_personal_memory": False,
            "source_contract": source_contract,
        }

    def execute_listener_turn(
        self,
        campaign_id: str,
        case: dict[str, Any],
        turn: dict[str, Any],
        *,
        wake_audio: Path | None,
        source_audio: Path | None,
        wake_asset: dict[str, Any] | None = None,
        source_asset: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source_authority_id, expected = self._source_authority(
            campaign_id,
            case,
            turn,
            source_asset,
        )
        journal_boundary = journal_sequence_boundary(
            Path(self.config["journal_db"]),
            session_id=case["session_id"],
        )
        ack = self.listener.arm({
            "schema": "embry.listener_turn_command.v1",
            "command": "arm",
            **{key: expected[key] for key in (
                "campaign_id",
                "case_id",
                "attempt_id",
                "session_id",
                "turn_id",
                "source_authority_id",
            )},
            "wake_required": True,
        })
        if not ack.get("armed"):
            raise RuntimeError("managed_listener_arm_rejected")

        if source_audio is None:
            print(
                json.dumps({
                    "status": "AWAITING_HUMAN_SPEECH",
                    "case_id": case["case_id"],
                    "turn_id": turn["turn_id"],
                    "say_exactly": turn.get("spoken_text", turn["utterance"]),
                }),
                flush=True,
            )
        else:
            print(
                json.dumps({
                    "status": "PLAYING_QUALIFIED_HORUS_AUDIO",
                    "case_id": case["case_id"],
                    "turn_id": turn["turn_id"],
                    "source_audio": str(source_audio),
                }),
                flush=True,
            )

        wake_event = None
        if wake_audio is not None:
            if not wake_audio.is_file():
                raise FileNotFoundError(f"wake_audio_missing:{wake_audio}")
            time.sleep(self.config["source_playback_delay_seconds"])
            managed_lineage = {key: expected[key] for key in (
                "campaign_id",
                "case_id",
                "attempt_id",
                "session_id",
                "turn_id",
                "source_authority_id",
            )}
            for wake_attempt in range(1, 4):
                print(
                    json.dumps({
                        "status": "PLAYING_WAKE_AUDIO",
                        "case_id": case["case_id"],
                        "turn_id": turn["turn_id"],
                        "wake_attempt": wake_attempt,
                    }),
                    flush=True,
                )
                wake_process = subprocess.run(
                    [
                        self.config["pw_play"],
                        "--target",
                        self.config["source_playback_target"],
                        "--volume",
                        str(self.config["wake_playback_volume"]),
                        str(wake_audio),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=15,
                )
                if wake_process.returncode != 0:
                    raise RuntimeError(
                        f"wake_playback_failed:{wake_process.returncode}:"
                        f"{wake_process.stderr}"
                    )
                try:
                    wake_event = wait_for_managed_wake(
                        Path(self.config["journal_db"]),
                        session_id=case["session_id"],
                        expected=managed_lineage,
                        after_sequence=journal_boundary,
                        timeout_seconds=min(
                            10.0,
                            self.config["turn_timeout_seconds"],
                        ),
                    )
                    break
                except TimeoutError:
                    if wake_attempt == 3:
                        raise

        source_process = None
        if source_audio is not None:
            if not source_audio.is_file():
                raise FileNotFoundError(f"turn_audio_missing:{source_audio}")
            time.sleep(
                self.config["source_playback_delay_seconds"]
                if wake_event is None
                else 0.5
            )
            source_process = subprocess.Popen(
                [
                    self.config["pw_play"],
                    "--target",
                    self.config["source_playback_target"],
                    "--volume",
                    str(self.config["source_playback_volume"]),
                    str(source_audio),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )

        chain = wait_for_managed_turn(
            Path(self.config["journal_db"]),
            session_id=case["session_id"],
            expected={key: expected[key] for key in (
                "campaign_id",
                "case_id",
                "attempt_id",
                "session_id",
                "turn_id",
                "source_authority_id",
            )},
            after_sequence=journal_boundary,
            timeout_seconds=self.config["turn_timeout_seconds"],
        )
        if source_process is not None:
            _, source_stderr = source_process.communicate(timeout=15)
            if source_process.returncode != 0:
                raise RuntimeError(
                    f"source_playback_failed:{source_process.returncode}:"
                    f"{source_stderr}"
                )

        final = chain["listener.final_transcript"]
        request_text = final["payload"].get("request_text") or ""
        expected_spoken = turn.get("spoken_text", turn["utterance"])
        asr_comparison = compare_asr_text(expected_spoken, request_text)
        request_wer = float(asr_comparison["comparison_wer"])
        if request_wer > self.config["max_request_wer"]:
            raise RuntimeError(
                f"managed_listener_request_wer_exceeded:{request_wer:.4f}:"
                f"expected={expected_spoken!r}:actual={request_text!r}"
            )

        return {
            "schema": "embry.audio_e2e.listener_turn_receipt.v1",
            "status": "PASS",
            "case_id": case["case_id"],
            "turn_id": turn["turn_id"],
            "source_mode": case["source_mode"],
            "fresh_physical_human_speech": expected["fresh_physical_human_speech"],
            "speaker_identity_proven": expected["speaker_identity_proven"],
            "speaker_identity_verification_required": expected[
                "speaker_identity_verification_required"
            ],
            "allow_personal_memory": expected["allow_personal_memory"],
            "source_contract": expected["source_contract"],
            "display_text_sha256": turn.get(
                "display_text_sha256", turn["utterance_sha256"]
            ),
            "expected_spoken_text_sha256": turn.get(
                "spoken_text_sha256", turn["utterance_sha256"]
            ),
            "source_authority_id": source_authority_id,
            "journal_sequence_boundary": journal_boundary,
            "arm_event_id": chain["listener.turn_armed"]["event_id"],
            "arm_sequence": chain["listener.turn_armed"]["sequence"],
            "wake_event_id": wake_event["event_id"] if wake_event else None,
            "final_event_id": final["event_id"],
            "final_sequence": final["sequence"],
            "request_text": request_text,
            "request_wer": round(request_wer, 4),
            "request_raw_wer": round(float(asr_comparison["raw_wer"]), 4),
            "request_comparison_wer": round(request_wer, 4),
            "asr_comparison": asr_comparison,
            "audio_path": final["payload"].get("audio_path"),
            "audio_sha256": final["payload"].get("audio_sha256"),
            "completed_event_id": chain["listener.turn_completed"]["event_id"],
            "live": final["live"],
            "mocked": final["mocked"],
            "wake_audio_path": str(wake_audio) if wake_audio else None,
            "source_audio_path": str(source_audio) if source_audio else None,
            "wake_playback_volume": self.config["wake_playback_volume"],
            "source_playback_volume": self.config["source_playback_volume"],
            "wake_asset": wake_asset,
            "source_asset": source_asset,
            "typed_transcript_used": False,
        }

    def execute_listener_turns(
        self,
        campaign_id: str,
        case: dict[str, Any],
    ) -> list[dict[str, Any]]:
        receipts: list[dict[str, Any]] = []
        source_audio = [Path(path) for path in self.config.get("turn_audio", [])]
        wake_audio = (
            Path(self.config["wake_audio"])
            if self.config.get("wake_audio")
            else None
        )
        if source_audio and len(source_audio) != len(case["turn_script"]):
            raise ValueError("turn_audio_count_mismatch")
        for turn_offset, turn in enumerate(case["turn_script"]):
            receipts.append(
                self.execute_listener_turn(
                    campaign_id,
                    case,
                    turn,
                    wake_audio=wake_audio,
                    source_audio=(
                        source_audio[turn_offset] if source_audio else None
                    ),
                )
            )
        return receipts
