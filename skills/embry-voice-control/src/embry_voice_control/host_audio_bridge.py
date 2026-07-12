"""Host-only PipeWire capture bridge for the containerized Embry listener."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import time
from typing import Any

from embry_voice_control.pcm_protocol import BYTES_PER_FRAME, frame_header, read_message, send_frame


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_bridge(args: argparse.Namespace) -> dict[str, Any]:
    if not args.source_node or args.source_node.isdigit():
        raise ValueError("explicit_pipewire_source_node_name_required")
    socket_path = Path(args.socket_path)
    deadline = time.monotonic() + args.connect_timeout
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    while True:
        try:
            sock.connect(str(socket_path))
            break
        except (FileNotFoundError, ConnectionRefusedError):
            if time.monotonic() >= deadline:
                raise TimeoutError("realtimestt_pcm_socket_unavailable")
            time.sleep(0.1)

    command = [
        args.pw_record, "--target", args.source_node, "--rate", "16000",
        "--channels", "1", "--format", "s16", "-",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdout is not None
    stream = sock.makefile("rb")
    sequence = 0
    ack_sequence = 0
    total_bytes = 0
    started = time.monotonic()
    try:
        while args.max_frames == 0 or sequence < args.max_frames:
            pcm = process.stdout.read(BYTES_PER_FRAME)
            if not pcm:
                break
            if len(pcm) != BYTES_PER_FRAME:
                raise RuntimeError("partial_pcm_frame")
            sequence += 1
            total_bytes += len(pcm)
            send_frame(sock, frame_header(
                session_id=args.session_id,
                stream_id=args.stream_id,
                source_node=args.source_node,
                frame_sequence=sequence,
                pcm=pcm,
            ), pcm)
            if sequence % args.ack_interval == 0:
                ack = read_message(stream)
                if ack.get("schema") != "embry.pcm_ack.v1":
                    raise RuntimeError("pcm_ack_schema_invalid")
                ack_sequence = int(ack.get("frame_sequence", 0))
                if ack_sequence != sequence:
                    raise RuntimeError("pcm_ack_sequence_mismatch")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        stream.close()
        sock.close()

    receipt = {
        "schema": "embry.host_pcm_bridge_receipt.v1",
        "live": True,
        "mocked": False,
        "created_at": utc_now(),
        "session_id": args.session_id,
        "stream_id": args.stream_id,
        "source_node": args.source_node,
        "socket_path": str(socket_path),
        "capture_command": command,
        "frame_count": sequence,
        "pcm_bytes": total_bytes,
        "last_ack_sequence": ack_sequence,
        "frame_gaps": 0,
        "duration_ms": round((time.monotonic() - started) * 1000),
        "pcm_contract_sha256": hashlib.sha256(b"s16le:16000:mono:512").hexdigest(),
        "ok": sequence > 0 and (sequence < args.ack_interval or ack_sequence == sequence),
    }
    output = Path(args.receipt)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-node", required=True)
    parser.add_argument("--socket-path", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--stream-id", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--pw-record", default="/usr/bin/pw-record")
    parser.add_argument("--ack-interval", type=int, default=32)
    parser.add_argument("--connect-timeout", type=float, default=15.0)
    parser.add_argument("--max-frames", type=int, default=0)
    args = parser.parse_args()
    result = run_bridge(args)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
