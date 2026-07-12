from __future__ import annotations

from io import BytesIO
import json
import struct

import pytest

from embry_voice_control.pcm_protocol import (
    BYTES_PER_FRAME, encode_frame, frame_header, read_exact, validate_frame,
)


def test_pcm_frame_round_trip_contract() -> None:
    pcm = bytes((index % 251 for index in range(BYTES_PER_FRAME)))
    header = frame_header(session_id="session-1", stream_id="stream-1", source_node="jabra.source", frame_sequence=1, pcm=pcm)
    encoded = encode_frame(header, pcm)
    header_size = struct.unpack("!I", encoded[:4])[0]
    decoded = json.loads(encoded[4:4 + header_size])
    payload = encoded[4 + header_size:]
    validate_frame(decoded, payload)
    assert decoded["frame_sequence"] == 1
    assert payload == pcm


def test_pcm_frame_rejects_corruption_and_partial_reads() -> None:
    pcm = bytes(BYTES_PER_FRAME)
    header = frame_header(session_id="session-1", stream_id="stream-1", source_node="jabra.source", frame_sequence=1, pcm=pcm)
    with pytest.raises(ValueError, match="pcm_crc32_mismatch"):
        validate_frame(header, b"x" + pcm[1:])
    with pytest.raises(EOFError, match="pcm_stream_ended"):
        read_exact(BytesIO(b"short"), 6)
