"""Framed PCM transport shared by the Embry host bridge contract."""

from __future__ import annotations

import json
import socket
import struct
import zlib
from typing import Any, BinaryIO


HEADER_LENGTH = struct.Struct("!I")
PCM_FORMAT = "s16le"
SAMPLE_RATE_HZ = 16_000
CHANNELS = 1
SAMPLES_PER_FRAME = 512
BYTES_PER_FRAME = SAMPLES_PER_FRAME * 2
MAX_HEADER_BYTES = 16 * 1024


def canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def frame_header(
    *, session_id: str, stream_id: str, source_node: str, frame_sequence: int, pcm: bytes,
) -> dict[str, Any]:
    if len(pcm) != BYTES_PER_FRAME:
        raise ValueError("pcm_frame_size_invalid")
    if frame_sequence < 1:
        raise ValueError("frame_sequence_invalid")
    return {
        "schema": "embry.pcm_frame.v1",
        "session_id": session_id,
        "stream_id": stream_id,
        "source_node": source_node,
        "frame_sequence": frame_sequence,
        "sample_offset": (frame_sequence - 1) * SAMPLES_PER_FRAME,
        "format": PCM_FORMAT,
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "channels": CHANNELS,
        "samples": SAMPLES_PER_FRAME,
        "payload_bytes": len(pcm),
        "crc32": f"{zlib.crc32(pcm) & 0xFFFFFFFF:08x}",
    }


def encode_frame(header: dict[str, Any], pcm: bytes) -> bytes:
    encoded = canonical_json(header)
    if len(encoded) > MAX_HEADER_BYTES:
        raise ValueError("pcm_header_too_large")
    return HEADER_LENGTH.pack(len(encoded)) + encoded + pcm


def send_frame(sock: socket.socket, header: dict[str, Any], pcm: bytes) -> None:
    sock.sendall(encode_frame(header, pcm))


def read_exact(stream: BinaryIO, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise EOFError("pcm_stream_ended")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_message(stream: BinaryIO) -> dict[str, Any]:
    length = HEADER_LENGTH.unpack(read_exact(stream, HEADER_LENGTH.size))[0]
    if length < 2 or length > MAX_HEADER_BYTES:
        raise ValueError("pcm_header_length_invalid")
    value = json.loads(read_exact(stream, length))
    if not isinstance(value, dict):
        raise ValueError("pcm_message_invalid")
    return value


def validate_frame(header: dict[str, Any], pcm: bytes) -> None:
    expected = {
        "schema": "embry.pcm_frame.v1",
        "format": PCM_FORMAT,
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "channels": CHANNELS,
        "samples": SAMPLES_PER_FRAME,
        "payload_bytes": BYTES_PER_FRAME,
    }
    for key, value in expected.items():
        if header.get(key) != value:
            raise ValueError(f"pcm_{key}_invalid")
    if len(pcm) != BYTES_PER_FRAME:
        raise ValueError("pcm_payload_size_invalid")
    if not isinstance(header.get("source_node"), str) or not header["source_node"]:
        raise ValueError("pcm_source_node_invalid")
    sequence = header.get("frame_sequence")
    if not isinstance(sequence, int) or sequence < 1:
        raise ValueError("pcm_frame_sequence_invalid")
    if header.get("sample_offset") != (sequence - 1) * SAMPLES_PER_FRAME:
        raise ValueError("pcm_sample_offset_invalid")
    if header.get("crc32") != f"{zlib.crc32(pcm) & 0xFFFFFFFF:08x}":
        raise ValueError("pcm_crc32_mismatch")
