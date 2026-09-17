"""Bounded strict JSON, deterministic digests, and atomic private file publication."""
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

from a_detection.errors import Code, DetectionError


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def text_digest(text: str) -> str:
    return digest(text.encode("utf-8"))


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DetectionError(Code.INVALID_INPUT, "Duplicate JSON object member.")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise DetectionError(Code.INVALID_INPUT, "Non-finite JSON number.")


def strict_json(raw: bytes | str, limit: int = 2_000_000) -> Any:
    if len(raw) > limit:
        raise DetectionError(Code.LIMIT, "JSON input exceeds the configured byte limit.", 413)
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        logger.error("classified_failure module=io")
        raise DetectionError(Code.INVALID_INPUT, "Invalid UTF-8 JSON.") from exc


def read_json(path: Path, limit: int = 2_000_000) -> Any:
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    return strict_json(raw, limit)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".publish-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(canonical(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
