#!/usr/bin/env python3
"""Run a live PipeWire/GPU-STT YouTube-audio oracle eval for Live Evidence."""

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


DEFAULT_WAV_CANDIDATES = [
    Path("/mnt/storage12tb/skills/live-evidence/live-youtube-proof/20260816T181309Z/youtube.wav"),
    Path("/mnt/storage12tb/skills/live-evidence/live-youtube-proof/20260816T180912Z/youtube.wav"),
    Path("/mnt/storage12tb/skills/live-evidence/live-youtube-proof/20260816T180437Z/youtube.wav"),
]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def create_virtual_sink(name: str) -> None:
    """Create a null audio sink for a fully digital play/record loop.

    Real-device transport is not evaluable deterministically here: recording the
    Jabra's sink monitor wedged the device mid-meeting on 2026-08-17 (see the
    bridge's --capture-kind warning), and mic capture depends on physical
    speaker state plus the speakerphone's echo canceller, which silently eats
    its own playback. A null sink has no hardware to wedge and no acoustics to
    vary: what is played is exactly what the monitor yields (verified RMS
    0.0504 vs source 0.058, with the Jabra left suspended throughout).
    """

    subprocess.run(
        ["pw-cli", "create-node", "adapter",
         "{ factory.name=support.null-audio-sink node.name=%s media.class=Audio/Sink "
         "audio.position=[FL,FR] object.linger=true }" % name],
        check=True, capture_output=True, text=True, timeout=15,
    )


def destroy_virtual_sink(name: str) -> None:
    subprocess.run(["pw-cli", "destroy", name], check=False, capture_output=True, text=True, timeout=15)


def default_source_wav() -> Path:
    for candidate in DEFAULT_WAV_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise RuntimeError("no stored YouTube WAV found; pass --source-wav")


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return payload


def write_profile(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "name: youtube-pipewire-oracle",
                "watch_terms:",
                "  - opening parentheses",
                "  - closing parentheses",
                "  - minimum parentheses",
                "  - valid string",
                "project_aliases:",
                "  live-evidence-proof:",
                "    - valid parentheses",
                "    - opening closing parentheses",
                "    - minimum invalid parentheses",
                "repo_priorities:",
                "  - live-evidence-proof",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_repo(repo: Path) -> None:
    repo.mkdir(parents=True)
    (repo / "valid_parentheses.py").write_text(
        "\n".join(
            [
                "def is_valid_parentheses(text: str) -> bool:",
                "    balance = 0",
                "    for char in text:",
                "        if char == '(':",
                "            balance += 1",
                "        elif char == ')':",
                "            if balance == 0:",
                "                return False",
                "            balance -= 1",
                "    return balance == 0",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo / "remove_invalid_parentheses.py").write_text(
        "\n".join(
            [
                "def remove_invalid_parentheses(text: str) -> str:",
                "    chars = list(text)",
                "    stack: list[int] = []",
                "    for index, char in enumerate(chars):",
                "        if char == '(':",
                "            stack.append(index)",
                "        elif char == ')' and stack:",
                "            stack.pop()",
                "        elif char == ')':",
                "            chars[index] = ''",
                "    while stack:",
                "        chars[stack.pop()] = ''",
                "    return ''.join(chars)",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_ask_fixture_runner(path: Path, run_dir: Path, log_path: Path) -> Path:
    runner = path / "ask-youtube-oracle-fixture-runner.sh"
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
                "Use a stack of opening-parenthesis indices. Remove closing parentheses that have no earlier opening match, then remove leftover opening indices. Preserve non-parenthesis characters. Code path: live-evidence-proof/remove_invalid_parentheses.py.",
                "EOF",
                'printf \'{"run_dir":"%s"}\\n\' "$run_dir"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner.chmod(0o755)
    return runner


def wait_for_health(client: httpx.Client, server_log: Path) -> None:
    for _ in range(100):
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


def run_bridge(args: argparse.Namespace, *, backend_url: str, source_wav: Path, output_dir: Path) -> dict[str, Any]:
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
        "--capture-kind",
        getattr(args, "capture_kind", "source"),
        "--docker-image",
        args.docker_image,
        "--output-dir",
        str(output_dir / "bridge"),
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
    result = subprocess.run(command, text=True, capture_output=True, check=False, timeout=args.max_seconds + 210)
    invocation = {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    try:
        payload = json.loads(result.stdout[result.stdout.index("{") :])
    except (ValueError, json.JSONDecodeError):
        payload = {}
    invocation["reported_receipt"] = payload.get("receipt")
    return invocation


def read_bridge_receipt(invocation: dict[str, Any]) -> dict[str, Any]:
    path = invocation.get("reported_receipt")
    if not isinstance(path, str) or not path:
        return {}
    receipt_path = Path(path)
    if not receipt_path.is_file():
        return {}
    return load_json(receipt_path)


def run_ui_cdp(
    repo_root: Path,
    backend_url: str,
    output_dir: Path,
    name: str,
    required_terms: list[str],
) -> tuple[str, dict[str, Any]] | tuple[None, dict[str, Any]]:
    hook = Path.home() / ".codex" / "hooks" / "verify-ui-cdp.sh"
    if not hook.is_file():
        return None, {"status": "SKIPPED", "reason": "verify-ui-cdp hook missing"}
    env = os.environ.copy()
    for key in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE"):
        env.pop(key, None)
    python_wrapper_dir = output_dir / "cdp-python-bin"
    python_wrapper_dir.mkdir(exist_ok=True)
    python3_link = python_wrapper_dir / "python3"
    if not python3_link.exists():
        python3_link.symlink_to("/usr/bin/python3")
    env["PATH"] = os.pathsep.join([str(python_wrapper_dir), env.get("PATH", "")])
    result = subprocess.run(
        [str(hook), "--url", backend_url, "--name", name],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    (output_dir / "ui-cdp.stdout.json").write_text(result.stdout, encoding="utf-8")
    (output_dir / "ui-cdp.stderr.log").write_text(result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "UI CDP verification failed")
    marker = repo_root / ".codex" / "ui-verification" / "latest.json"
    if not marker.is_file():
        raise RuntimeError("UI CDP verification did not write .codex/ui-verification/latest.json")
    marker_copy = output_dir / "ui-cdp-latest.json"
    shutil.copy2(marker, marker_copy)
    ui_result = validate_ui_marker(marker_copy, required_terms)
    return str(marker_copy), ui_result


def validate_ui_marker(marker_path: Path, required_terms: list[str]) -> dict[str, Any]:
    marker = load_json(marker_path)
    screenshot = Path(str(marker.get("screenshot") or ""))
    read_json = Path(str(marker.get("read_json") or ""))
    read_payload = load_json(read_json) if read_json.is_file() else {}
    visible_text = normalize(read_payload.get("text") or read_payload.get("visible_text") or "")
    missing_terms = [term for term in required_terms if normalize(term) not in visible_text]
    result = {
        "status": "PASS",
        "marker": str(marker_path),
        "transport": marker.get("transport"),
        "screenshot": str(screenshot) if screenshot else None,
        "read_json": str(read_json) if read_json else None,
        "screenshot_exists": screenshot.is_file(),
        "read_json_exists": read_json.is_file(),
        "visible_text_chars": len(visible_text),
        "required_terms": required_terms,
        "missing_terms": missing_terms,
    }
    if not result["screenshot_exists"] or not result["read_json_exists"] or missing_terms:
        result["status"] = "FAIL"
    return result


def normalize(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def text_blob(items: list[object]) -> str:
    return normalize(" ".join(str(item or "") for item in items))


def term_group_present(blob: str, group: list[str]) -> bool:
    return all(normalize(term) in blob for term in group)


def card_blob(card: dict[str, Any]) -> str:
    fields = [card.get("query"), card.get("talking_point"), card.get("proof"), card.get("qualifier")]
    for source in card.get("sources") or []:
        fields.extend([source.get("path"), source.get("excerpt"), source.get("repository")])
    return text_blob(fields)


def card_sources(card: dict[str, Any]) -> list[dict[str, Any]]:
    return [source for source in card.get("sources") or [] if isinstance(source, dict)]


CAPTURE_FIDELITY_THRESHOLD = 0.30


def capture_fidelity(captured_blob: str, reference_text: str) -> float:
    """Fraction of reference content words present in the captured transcript.

    The content checks below are meaningless when the capture itself was
    degraded: on 2026-08-17 sink contention turned a WAV that transcribes
    cleanly when read directly (all required terms present) into 641 incoherent
    50-char fragments, and the eval failed on transcript terms as if question
    detection had broken. A fidelity gate distinguishes "the pipeline judged
    badly" from "the pipeline never received the audio", which need different
    responses. Content words only (4+ chars), so fillers cannot fake overlap.
    """

    reference_tokens = {
        token for token in normalize(reference_text).split() if len(token) >= 4
    }
    if not reference_tokens:
        return 1.0
    captured = normalize(captured_blob)
    present = sum(1 for token in reference_tokens if token in captured)
    return present / len(reference_tokens)


def evaluate_oracle(state: dict[str, Any], bridge_receipt: dict[str, Any], oracle: dict[str, Any], reference_text: str = "") -> dict[str, Any]:
    transcript = state.get("transcript") if isinstance(state.get("transcript"), list) else []
    cards = state.get("cards") if isinstance(state.get("cards"), list) else []
    transcript_blob = text_blob([event.get("text") for event in transcript if isinstance(event, dict)])
    card_blobs = [card_blob(card) for card in cards if isinstance(card, dict)]
    all_card_text = "\n".join(card_blobs)
    acceptance = bridge_receipt.get("acceptance") if isinstance(bridge_receipt.get("acceptance"), dict) else {}

    transcript_groups = oracle.get("transcript_required_term_groups") or []
    selected_query = oracle.get("selected_query") if isinstance(oracle.get("selected_query"), dict) else {}
    card_contract = oracle.get("card") if isinstance(oracle.get("card"), dict) else {}
    gate_contract = oracle.get("gate") if isinstance(oracle.get("gate"), dict) else {}

    candidate_cards = [
        card for card in cards
        if isinstance(card, dict) and term_group_present(card_blob(card), card_contract.get("required_text_terms") or [])
    ]
    path_fragments = [str(item) for item in card_contract.get("required_source_path_fragments") or []]
    excerpt_terms = [str(item) for item in card_contract.get("required_source_excerpt_terms") or []]
    matching_source_cards = []
    for card in candidate_cards:
        for source in card_sources(card):
            source_path = normalize(source.get("path"))
            source_excerpt = normalize(source.get("excerpt"))
            if all(normalize(fragment) in source_path for fragment in path_fragments) and all(
                normalize(term) in source_excerpt for term in excerpt_terms
            ):
                matching_source_cards.append(card)
                break

    query_cards = []
    query_required = [str(item) for item in selected_query.get("required_terms") or []]
    query_forbidden = [str(item) for item in selected_query.get("forbidden_terms") or []]
    query_max = int(selected_query.get("max_chars") or 0)
    for card in cards:
        if not isinstance(card, dict):
            continue
        query = normalize(card.get("query"))
        if not query:
            continue
        if query_required and not term_group_present(query, query_required):
            continue
        if query_max and len(str(card.get("query") or "")) > query_max:
            continue
        if any(term in query for term in map(normalize, query_forbidden)):
            continue
        query_cards.append(card)

    ask_sources = [
        source
        for card in cards
        if isinstance(card, dict)
        for source in card_sources(card)
        if source.get("lane") == "ask" and source.get("repository") == "ask"
    ]
    gate_sources = [
        source
        for card in cards
        if isinstance(card, dict)
        for source in card_sources(card)
        if source.get("repository") == "transcript-to-leetcode"
    ]
    raw_ask_without_gate = bool(ask_sources and not gate_sources)

    forbidden_card_terms = [normalize(term) for term in card_contract.get("forbidden_text_terms") or []]
    fidelity = capture_fidelity(transcript_blob, reference_text) if reference_text else None
    checks = {
        "capture_fidelity": fidelity,
        "capture_fidelity_ok": fidelity is None or fidelity >= CAPTURE_FIDELITY_THRESHOLD,
        "bridge_pipewire_audio_captured": acceptance.get("pipewire_audio_captured") is True,
        "bridge_docker_realtimestt_process_ok": acceptance.get("docker_realtimestt_process_ok") is True,
        "bridge_pipewire_transcript_events": int(acceptance.get("pipewire_transcript_events") or 0),
        "transcript_required_terms": [
            {"terms": group, "present": term_group_present(transcript_blob, [str(term) for term in group])}
            for group in transcript_groups
        ],
        "selected_query_bounded": bool(query_cards),
        "source_backed_expected_card": bool(matching_source_cards),
        "forbidden_card_terms_absent": not any(term and term in all_card_text for term in forbidden_card_terms),
        "raw_ask_without_gate_absent": not raw_ask_without_gate or gate_contract.get("raw_ask_without_gate_allowed") is True,
        "blocked_gate_shows_seed_source": True,
    }
    if gate_contract.get("blocked_gate_must_show_seed_source") is True and gate_sources:
        checks["blocked_gate_shows_seed_source"] = bool(matching_source_cards)
    pass_checks = (
        checks["bridge_pipewire_audio_captured"]
        and checks["bridge_docker_realtimestt_process_ok"]
        and checks["bridge_pipewire_transcript_events"] > 0
        and all(item["present"] for item in checks["transcript_required_terms"])
        and checks["selected_query_bounded"]
        and checks["source_backed_expected_card"]
        and checks["forbidden_card_terms_absent"]
        and checks["raw_ask_without_gate_absent"]
        and checks["blocked_gate_shows_seed_source"]
    )
    if not checks["capture_fidelity_ok"]:
        # The audio never arrived intact; content verdicts below would blame
        # the wrong layer. Fail with the true reason instead.
        return {
            "status": "FAIL",
            "failure_reason": "capture_fidelity_degraded",
            "checks": checks,
            "matching_card_ids": [],
            "selected_query_card_ids": [],
            "gate_source_count": len(gate_sources),
            "ask_source_count": len(ask_sources),
        }
    return {
        "status": "PASS" if pass_checks else "FAIL",
        "failure_reason": None if pass_checks else "content_checks_failed",
        "checks": checks,
        "matching_card_ids": [card.get("card_id") for card in matching_source_cards],
        "selected_query_card_ids": [card.get("card_id") for card in query_cards],
        "gate_source_count": len(gate_sources),
        "ask_source_count": len(ask_sources),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--oracle", default=Path(__file__).resolve().parents[1] / "fixtures" / "youtube_pipewire_oracle.json")
    parser.add_argument("--source-wav", default=None)
    parser.add_argument("--output-dir", default="/mnt/storage12tb/skills/live-evidence/agentic-evals/live-youtube-pipewire-oracle")
    parser.add_argument("--docker-image", default="live-evidence-realtimestt-gpu:local")
    # Sink NAME, not a numeric node id: PipeWire node ids are not stable
    # across boots. The previous default "59" pointed at a node that no
    # longer existed, so playback fell back elsewhere while capture
    # listened to this sink's monitor and recorded 107s of silence
    # (RMS 0.0003 vs 0.058 healthy). Names route deterministically.
    parser.add_argument("--playback-target", default="alsa_output.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.analog-stereo")
    parser.add_argument("--capture-target", default="alsa_output.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.analog-stereo")
    parser.add_argument(
        "--real-device", action="store_true",
        help="Route through the physical targets instead of a per-run null sink. "
             "Opt-in: physical routing depends on speaker state and echo cancellation, "
             "and monitor-capture on the Jabra has wedged the device mid-call.",
    )
    parser.add_argument("--max-seconds", type=float, default=108.0)
    parser.add_argument("--tail-seconds", type=float, default=2.5)
    parser.add_argument("--model", default="base.en")
    parser.add_argument("--realtime-model", default="tiny.en")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--ui-cdp", action="store_true")
    parser.add_argument("--ui-name", default="live-evidence-youtube-pipewire-oracle")
    parser.add_argument("--attempts", type=int, default=1, help="Retry full live attempts until backend and UI oracle pass.")
    return parser.parse_args()


def run_attempt_loop(args: argparse.Namespace) -> int:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    aggregate_dir = Path(args.output_dir).expanduser().resolve() / run_id
    attempts_dir = aggregate_dir / "attempts"
    aggregate_dir.mkdir(parents=True, exist_ok=False)
    receipt_path = aggregate_dir / "receipt.json"
    attempts: list[dict[str, Any]] = []
    final_status = "FAIL"
    passing_receipt: str | None = None
    for attempt in range(1, args.attempts + 1):
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            str(Path(args.root).expanduser().resolve()),
            "--oracle",
            str(Path(args.oracle).expanduser().resolve()),
            "--output-dir",
            str(attempts_dir),
            "--docker-image",
            args.docker_image,
            "--playback-target",
            args.playback_target,
            "--capture-target",
            args.capture_target,
            "--max-seconds",
            str(args.max_seconds),
            "--tail-seconds",
            str(args.tail_seconds),
            "--model",
            args.model,
            "--realtime-model",
            args.realtime_model,
            "--compute-type",
            args.compute_type,
            "--ui-name",
            args.ui_name,
        ]
        if args.source_wav:
            command.extend(["--source-wav", str(Path(args.source_wav).expanduser().resolve())])
        if args.ui_cdp:
            command.append("--ui-cdp")
        result = subprocess.run(command, text=True, capture_output=True, check=False, timeout=args.max_seconds + 300)
        attempt_summary: dict[str, Any] = {
            "attempt": attempt,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        try:
            payload = json.loads(result.stdout[result.stdout.index("{") :])
        except (ValueError, json.JSONDecodeError):
            payload = {}
        attempt_summary["receipt"] = payload.get("receipt")
        attempt_summary["status"] = payload.get("status")
        attempts.append(attempt_summary)
        if result.returncode == 0 and payload.get("status") == "PASS":
            final_status = "PASS"
            passing_receipt = payload.get("receipt")
            break
    receipt = {
        "schema": "live_evidence.live_youtube_pipewire_oracle_loop_receipt.v1",
        "status": final_status,
        "created_at": datetime.now(UTC).isoformat(),
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "attempt_budget": args.attempts,
        "attempts_run": len(attempts),
        "passing_receipt": passing_receipt,
        "attempts": attempts,
        "output_dir": str(aggregate_dir),
        "stop_condition": "first backend+Surf/CDP oracle PASS" if final_status == "PASS" else "attempt budget exhausted",
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    shutil.copy2(receipt_path, Path("/tmp/live-evidence-live-youtube-pipewire-oracle-receipt.json"))
    print(json.dumps({"receipt": str(receipt_path), "status": final_status, "passing_receipt": passing_receipt}, indent=2))
    return 0 if final_status == "PASS" else 1


def main() -> int:
    args = parse_args()
    if args.attempts < 1:
        raise SystemExit("--attempts must be >= 1")
    if args.attempts > 1:
        return run_attempt_loop(args)
    root = Path(args.root).expanduser().resolve()
    repo_root = root.parents[1]
    skills_root = root.parent
    virtual_sink: str | None = None
    if not getattr(args, "real_device", False):
        virtual_sink = f"le-eval-sink-{os.getpid()}"
        create_virtual_sink(virtual_sink)
        args.playback_target = virtual_sink
        args.capture_target = virtual_sink
        args.capture_kind = "sink-monitor"
    else:
        args.capture_kind = "source"
    source_wav = Path(args.source_wav).expanduser().resolve() if args.source_wav else default_source_wav()
    oracle_path = Path(args.oracle).expanduser().resolve()
    oracle = load_json(oracle_path)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_dir).expanduser().resolve() / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    receipt_path = output_dir / "receipt.json"
    receipt: dict[str, Any] = {
        "schema": "live_evidence.live_youtube_pipewire_oracle_receipt.v1",
        "status": "FAIL",
        "created_at": datetime.now(UTC).isoformat(),
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "oracle": str(oracle_path),
        "source_wav": str(source_wav),
        "youtube_source": oracle.get("source"),
        "output_dir": str(output_dir),
    }
    server_process: subprocess.Popen[str] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="live-evidence-youtube-pipewire-oracle-") as temp_name:
            temp = Path(temp_name)
            repo = temp / "live-evidence-proof"
            write_repo(repo)
            profile = temp / "profile.yaml"
            write_profile(profile)
            data_dir = output_dir / "data"
            server_log = output_dir / "server.log"
            ask_log = output_dir / "ask.argv"
            ask_run_dir = output_dir / "ask-run"
            ask_runner = write_ask_fixture_runner(output_dir, ask_run_dir, ask_log)
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
                "LIVE_EVIDENCE_ASK_HANDLER": "fixture-handler",
                "LIVE_EVIDENCE_ASK_TIMEOUT": "5",
                "LIVE_EVIDENCE_ASK_ALLOW_PROVIDER_CALLS": "false",
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
                bridge_invocation = run_bridge(args, backend_url=backend_url, source_wav=source_wav, output_dir=output_dir)
                bridge_receipt = read_bridge_receipt(bridge_invocation)
                final_state = get_state(client)
                final_state_path = output_dir / "final-state.json"
                final_state_path.write_text(json.dumps(final_state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                bridge_invocation_path = output_dir / "bridge-invocation.json"
                bridge_invocation_path.write_text(json.dumps(bridge_invocation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                reference_path = root / "fixtures" / "live_youtube_reference_transcript.txt"
                reference_text = reference_path.read_text(encoding="utf-8") if reference_path.is_file() else ""
                oracle_result = evaluate_oracle(final_state, bridge_receipt, oracle, reference_text)
                oracle_result_path = output_dir / "oracle-result.json"
                oracle_result_path.write_text(json.dumps(oracle_result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                ui_required_terms = [
                    "Live Evidence",
                    "QUESTION",
                    "Contract not established",
                    *[str(term) for term in (oracle.get("selected_query") or {}).get("required_terms", [])],
                    *[str(term) for term in (oracle.get("card") or {}).get("required_source_path_fragments", [])],
                    *[str(term) for term in (oracle.get("card") or {}).get("required_source_excerpt_terms", [])],
                ]
                if args.ui_cdp:
                    ui_cdp_marker, ui_cdp_result = run_ui_cdp(
                        repo_root,
                        backend_url,
                        output_dir,
                        args.ui_name,
                        ui_required_terms,
                    )
                else:
                    ui_cdp_marker, ui_cdp_result = None, {"status": "SKIPPED", "reason": "--ui-cdp not requested"}
                ui_cdp_result_path = output_dir / "ui-cdp-result.json"
                ui_cdp_result_path.write_text(json.dumps(ui_cdp_result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                pass_status = oracle_result["status"] == "PASS" and (not args.ui_cdp or ui_cdp_result.get("status") == "PASS")
                receipt.update(
                    {
                        "status": "PASS" if pass_status else "FAIL",
                        "backend_url": backend_url,
                        "server_log": str(server_log),
                        "bridge_invocation": str(bridge_invocation_path),
                        "bridge_reported_receipt": bridge_invocation.get("reported_receipt"),
                        "final_state": str(final_state_path),
                        "oracle_result": str(oracle_result_path),
                        "ui_cdp_marker": ui_cdp_marker,
                        "ui_cdp_result": str(ui_cdp_result_path),
                        "checks": {
                            **oracle_result["checks"],
                            "ui_cdp_marker": bool(ui_cdp_marker),
                            "ui_cdp_screenshot_exists": ui_cdp_result.get("screenshot_exists") is True,
                            "ui_cdp_read_json_exists": ui_cdp_result.get("read_json_exists") is True,
                            "ui_cdp_visible_terms_present": ui_cdp_result.get("status") == "PASS",
                        },
                        "matching_card_ids": oracle_result["matching_card_ids"],
                        "selected_query_card_ids": oracle_result["selected_query_card_ids"],
                        "gate_source_count": oracle_result["gate_source_count"],
                        "ask_source_count": oracle_result["ask_source_count"],
                        "claims": {
                            "proves": [
                                "a stored YouTube interview WAV was played through PipeWire into a GPU Docker RealtimeSTT container",
                                "Live Evidence received pipewire transcript events containing the expected parenthesis-problem terms",
                                "the selected live card stayed bounded to the parenthesis question",
                                "the displayed card exposed current-source evidence for valid_parentheses.py",
                                "known off-target maintenance/WebGPT evidence was absent",
                            ],
                            "does_not_prove": [
                                "browser playback from youtube.com because the eval reuses a stored WAV from the supplied video",
                                "live Ask provider quality because this oracle permits the deterministic gate to block Ask",
                                "real Memory relevance because Memory is intentionally degraded to localhost:9",
                            ],
                        },
                    }
                )
    except Exception as exc:
        receipt["error"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        if virtual_sink:
            destroy_virtual_sink(virtual_sink)
        if server_process and server_process.poll() is None:
            server_process.terminate()
            try:
                server_process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                server_process.kill()
                server_process.wait(timeout=2.0)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copy2(receipt_path, Path("/tmp/live-evidence-live-youtube-pipewire-oracle-receipt.json"))
    print(json.dumps({"receipt": str(receipt_path), "status": receipt.get("status"), "error": receipt.get("error")}, indent=2))
    return 0 if receipt.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
