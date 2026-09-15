from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_PACKET = "project_dream_evidence_packet.v1"
SCHEMA_CANDIDATE = "project_dream_candidate.v1"
SCHEMA_VALIDATION = "project_dream_validation_receipt.v1"

ACTIONS = {
    "CREATE_CANDIDATE",
    "REVISE_CANDIDATE",
    "SUPERSEDE_WITH_REPLACEMENT",
    "DEPRECATE_WITH_REPLACEMENT",
    "MARK_FRESHNESS_STALE",
    "NO_CHANGE",
    "NEEDS_HUMAN_REVIEW",
}

AUTHORITY_RANK = {
    "explicit_user_decision": 1,
    "current_code": 2,
    "machine_receipt": 2,
    "accepted_commit_receipt": 3,
    "resolved_session_compaction": 4,
    "repeated_session_observation": 5,
    "assistant_statement": 6,
    "external_research_unverified": 7,
}

SECRET_RE = re.compile(
    r"(-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:api[_-]?key|token|password|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{12,})",
    re.IGNORECASE,
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest_object(data: Any, omit_keys: set[str] | None = None) -> str:
    omit = omit_keys or set()

    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: scrub(v) for k, v in value.items() if k not in omit}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        return value

    return sha256_text(canonical_json(scrub(data)))


def verify_declared_digest(data: dict[str, Any], field: str = "input_digest") -> tuple[bool, str]:
    actual = digest_object(data, {field})
    return data.get(field) == actual, actual


def json_sidecar(path: Path, suffix: str) -> Path:
    return path.with_name(path.name + suffix)


def contains_secret(value: Any) -> bool:
    if isinstance(value, str):
        return bool(SECRET_RE.search(value))
    if isinstance(value, dict):
        return any(contains_secret(v) for v in value.values())
    if isinstance(value, list):
        return any(contains_secret(v) for v in value)
    return False


def provider_from_model(model: str) -> str:
    return model.split("/", 1)[0] if "/" in model else "opencode"
