#!/usr/bin/env python3
"""Build and validate the active-revision Phase 11 zero-call payload binding."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence
from urllib.parse import quote, urlparse

from jsonschema import Draft202012Validator

from prepare_revision_qualification import GateBlocked, read_object, safe_indexed_file, sha256_file

ROOT = Path(__file__).resolve().parents[1]
STANDARD_ENDPOINT = "fal-ai/kling-video/v3/standard/image-to-video"
DEFAULT_REPOSITORY = "grahama1970/agent-skills"
PAYLOAD_BINDING_SCHEMA = "persona_dream.phase11_payload_binding.v1"
PAYLOAD_BINDING_STATUS = "BLOCKED_PUBLIC_MEDIA_PROBE_REQUIRED"
EXPECTED_DURATIONS = (2, 3, 2, 3)
MAX_MULTI_PROMPT_CHARS = 512
FRAME_IDS = tuple(
    f"sb_{panel:03d}.{role}_frame"
    for panel in range(1, 5)
    for role in ("start", "end")
)
FRAME_ROLES = {
    "sb_001.start_frame": "global_start_anchor",
    "sb_004.end_frame": "global_end_anchor",
    **{
        artifact_id: "continuity_only"
        for artifact_id in FRAME_IDS
        if artifact_id not in {"sb_001.start_frame", "sb_004.end_frame"}
    },
}
CHARACTER_REFERENCE_SUFFIXES = {
    "embry": "phase_07_storyboard_live_tau/references/01-embry_character_sheet.jpg",
    "kai": "phase_07_storyboard_live_tau/references/02-kai_character_sheet.png",
}
ELEMENT_REFERENCE_IDS = {
    "embry": ("sb_002.start_frame", "sb_004.start_frame"),
    "kai": ("sb_001.start_frame", "sb_003.start_frame"),
}
SHA256_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
COMMIT_RE = re.compile(r"^[a-f0-9]{40}$")
TIME_RANGE_RE = re.compile(r"time\s+range\s+([0-9]+(?:\.[0-9]+)?)s\s*[-–]\s*([0-9]+(?:\.[0-9]+)?)s", re.I)
TIER_RE = re.compile(r"Kling(?:\s+Video)?\s+v?3\s+(Pro|Standard)(?:\s+I2V)?", re.I)
SPOKEN_PATTERNS = (
    re.compile(r"\b(?:quietly\s+)?(?:says?|speaks?|whispers?)\b", re.I),
    re.compile(r"\bdialogue\s+cue\s*:", re.I),
    re.compile(r"if we paddle now", re.I),
)
SPEECH_NEGATIVE = (
    "no audible speech, no lip-sync, no mouth articulating words, no subtitles, "
    "no captions, no dialogue text, no speech bubbles"
)

# The live fal queue accepted the request but result validation rejected each
# KlingV3MultiPromptElement.prompt above this Unicode character boundary.
# Keep this constraint shared by binding generation and canonical validation.
PANEL_SOURCE_REQUIREMENTS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "sb_001": (
        ("location", ("kahalu", "kona")),
        ("lineup", ("lineup",)),
        ("reef", ("reef",)),
        ("restraint", ("wait", "hold", "outside")),
    ),
    "sb_002": (
        ("wax", ("wax",)),
        ("grip", ("grip", "palm")),
        ("reef", ("reef",)),
        ("fatigue", ("fatigue", "sweat", "heat")),
    ),
    "sb_003": (
        ("lineup", ("lineup",)),
        ("safe_channel", ("safe channel",)),
        ("reef", ("reef",)),
        ("etiquette", ("etiquette",)),
    ),
    "sb_004": (
        ("safe_channel", ("safe channel",)),
        ("reef", ("reef",)),
        ("commit", ("commit", "chooses")),
        ("agency", ("decision", "agency")),
    ),
}

PANEL_CONCISE_ACTIONS = {
    "sb_001": (
        "Waterline wide at Kahaluʻu Bay: @Element1 Embry and @Element2 Kai hold "
        "outside the lineup over visible lava reef, respecting surf etiquette."
    ),
    "sb_002": (
        "Medium waterline action: @Element1 Embry resets her grip as sun-softened "
        "wax slips before the lava reef; heat and fatigue show while @Element2 Kai stays outside."
    ),
    "sb_003": (
        "Medium-wide lineup: @Element2 Kai reads the safe channel, reef, and surf "
        "etiquette, then signals @Element1 Embry to wait; Embry remains the decision-maker."
    ),
    "sb_004": (
        "Waterline finish: @Element1 Embry commits through the safe channel above "
        "visible lava reef; @Element2 Kai stays outside the main action, preserving Embry's agency."
    ),
}

COMMON_CONTINUITY = "Preserve Embry and Kai identity and rashguard continuity."
SB003_SILENCE = (
    "Silent shot: No spoken dialogue. No lip movement; use gaze, posture, and one "
    "nonverbal hand signal."
)


class PayloadBindingBlocked(RuntimeError):
    def __init__(self, code: str, *, details: Mapping[str, Any] | None = None, exit_code: int = 2) -> None:
        super().__init__(code)
        self.code = code
        self.details = dict(details or {})
        self.exit_code = exit_code


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def pretty_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def schema_errors(value: Mapping[str, Any]) -> list[str]:
    schema_path = ROOT / "contracts" / "phase11_payload_binding.v1.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PayloadBindingBlocked(
            "BLOCKED_PHASE11_PAYLOAD_BINDING_SCHEMA_UNAVAILABLE",
            details={"path": str(schema_path), "error": str(exc)},
        ) from exc
    return [
        f"{'.'.join(str(part) for part in error.path) or '$'}: {error.message}"
        for error in sorted(Draft202012Validator(schema).iter_errors(dict(value)), key=lambda item: list(item.path))
    ]


def _read_object(path: Path, *, missing_code: str, invalid_code: str) -> dict[str, Any]:
    if not path.is_file():
        raise PayloadBindingBlocked(
            missing_code,
            details={"path": str(path), "next_command": "bootstrap-phase11-payload-binding"},
        )
    try:
        value = read_object(path)
    except (GateBlocked, OSError, ValueError, json.JSONDecodeError) as exc:
        raise PayloadBindingBlocked(invalid_code, details={"path": str(path), "error": str(exc)}) from exc
    if not isinstance(value, dict):
        raise PayloadBindingBlocked(invalid_code, details={"path": str(path)})
    return value


def discover_git_commit(run_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(run_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PayloadBindingBlocked(
            "BLOCKED_PHASE11_PUBLICATION_COMMIT_REQUIRED",
            details={
                "error": str(exc),
                "next_command": "skills/persona-dream/run.sh bootstrap-phase11-payload-binding --publication-commit <40-hex-commit>",
            },
        ) from exc
    commit = completed.stdout.strip().lower()
    if not COMMIT_RE.fullmatch(commit):
        raise PayloadBindingBlocked(
            "BLOCKED_PHASE11_PUBLICATION_COMMIT_INVALID",
            details={"observed": commit},
        )
    return commit


def _artifact_index(context: Any) -> dict[str, dict[str, Any]]:
    raw = getattr(context, "artifact_index", {}).get("artifacts")
    if not isinstance(raw, Mapping):
        raise PayloadBindingBlocked("BLOCKED_REVISION_ARTIFACT_INDEX_INVALID")
    return {str(key): dict(value) for key, value in raw.items() if isinstance(value, Mapping)}


def _verified_entry(context: Any, artifact_id: str) -> dict[str, Any]:
    entry = _artifact_index(context).get(artifact_id)
    if not isinstance(entry, Mapping):
        raise PayloadBindingBlocked(
            "BLOCKED_PHASE11_PAYLOAD_BINDING_ARTIFACT_MISSING",
            details={"artifact_id": artifact_id},
        )
    relative_path = str(entry.get("relative_path") or "")
    expected_sha = str(entry.get("sha256") or "")
    pure = PurePosixPath(relative_path)
    if not relative_path or pure.is_absolute() or ".." in pure.parts or not SHA256_RE.fullmatch(expected_sha):
        raise PayloadBindingBlocked(
            "BLOCKED_PHASE11_PAYLOAD_BINDING_ARTIFACT_INVALID",
            details={"artifact_id": artifact_id, "relative_path": relative_path, "sha256": expected_sha},
        )
    try:
        local = safe_indexed_file(context.revision_root, relative_path)
        observed_sha = sha256_file(local)
    except (GateBlocked, OSError, ValueError) as exc:
        raise PayloadBindingBlocked(
            "BLOCKED_PHASE11_PAYLOAD_BINDING_ARTIFACT_INVALID",
            details={"artifact_id": artifact_id, "relative_path": relative_path, "error": str(exc)},
        ) from exc
    if observed_sha != expected_sha:
        raise PayloadBindingBlocked(
            "BLOCKED_PHASE11_PAYLOAD_BINDING_ARTIFACT_HASH",
            details={"artifact_id": artifact_id, "expected": expected_sha, "observed": observed_sha},
        )
    return dict(entry)


def _unique_artifact_by_suffix(context: Any, suffix: str) -> tuple[str, dict[str, Any]]:
    suffix = PurePosixPath(suffix).as_posix()
    matches = [
        (artifact_id, dict(entry))
        for artifact_id, entry in _artifact_index(context).items()
        if str(entry.get("relative_path") or "") == suffix
        or str(entry.get("relative_path") or "").endswith("/" + suffix)
    ]
    if len(matches) != 1:
        raise PayloadBindingBlocked(
            "BLOCKED_PHASE11_CHARACTER_REFERENCE_ARTIFACT",
            details={"suffix": suffix, "matches": [item[0] for item in matches]},
        )
    artifact_id, _entry = matches[0]
    return artifact_id, _verified_entry(context, artifact_id)


def _raw_url(repository: str, commit: str, context: Any, relative_path: str) -> str:
    if repository.count("/") != 1:
        raise PayloadBindingBlocked("BLOCKED_PHASE11_PUBLICATION_REPOSITORY_INVALID", details={"repository": repository})
    if not COMMIT_RE.fullmatch(commit):
        raise PayloadBindingBlocked("BLOCKED_PHASE11_PUBLICATION_COMMIT_INVALID", details={"commit": commit})
    path = PurePosixPath(
        "skills",
        "persona-dream",
        "reports",
        context.run_id,
        ".persona-dream",
        "revisions",
        context.revision_id,
        relative_path,
    ).as_posix()
    encoded = "/".join(quote(part, safe="._-") for part in path.split("/"))
    return f"https://raw.githubusercontent.com/{repository}/{commit}/{encoded}"


def _record(context: Any, artifact_id: str, *, role: str, repository: str, commit: str) -> dict[str, Any]:
    entry = _verified_entry(context, artifact_id)
    relative_path = str(entry["relative_path"])
    return {
        "artifact_id": artifact_id,
        "role": role,
        "sha256": str(entry["sha256"]),
        "revision_relative_path": relative_path,
        "public_url": _raw_url(repository, commit, context, relative_path),
    }


def _media_lock_assets(context: Any, media_lock_path: Path) -> dict[str, dict[str, Any]]:
    value = _read_object(
        media_lock_path,
        missing_code="BLOCKED_PHASE11_MEDIA_LOCK_MISSING",
        invalid_code="BLOCKED_PHASE11_MEDIA_LOCK_INVALID",
    )
    raw = value.get("assets")
    if not isinstance(raw, list) or not all(isinstance(item, Mapping) for item in raw):
        raise PayloadBindingBlocked("BLOCKED_PHASE11_MEDIA_LOCK_INVALID")
    by_id = {str(item.get("asset_id") or ""): dict(item) for item in raw}
    if len(raw) != 8 or set(by_id) != set(FRAME_IDS):
        raise PayloadBindingBlocked(
            "BLOCKED_PHASE11_MEDIA_LOCK_FRAME_SET",
            details={"observed": sorted(by_id), "expected": sorted(FRAME_IDS)},
        )
    for artifact_id in FRAME_IDS:
        entry = _verified_entry(context, artifact_id)
        locked_sha = str(by_id[artifact_id].get("sha256") or by_id[artifact_id].get("observed_sha256") or "")
        if locked_sha != entry.get("sha256"):
            raise PayloadBindingBlocked(
                "BLOCKED_PHASE11_MEDIA_LOCK_HASH",
                details={"artifact_id": artifact_id, "locked": locked_sha, "indexed": entry.get("sha256")},
            )
    return by_id


def _phase10_prompts(phase10: Mapping[str, Any]) -> list[dict[str, Any]]:
    preview = phase10.get("assembled_request_preview")
    request_input = preview.get("input") if isinstance(preview, Mapping) else None
    raw = request_input.get("multi_prompt") if isinstance(request_input, Mapping) else None
    if not isinstance(raw, list) or len(raw) != 4 or not all(isinstance(item, Mapping) for item in raw):
        raise PayloadBindingBlocked(
            "BLOCKED_PHASE11_PHASE10_MULTI_PROMPT",
            details={"observed_count": len(raw) if isinstance(raw, list) else None},
        )
    return [dict(item) for item in raw]


def _source_semantic_blockers(prompt: str, panel_id: str) -> list[str]:
    lowered = prompt.casefold()
    blockers: list[str] = []
    for label, alternatives in PANEL_SOURCE_REQUIREMENTS[panel_id]:
        if not any(token.casefold() in lowered for token in alternatives):
            blockers.append(
                f"BLOCKED_PROVIDER_PROMPT_SEMANTIC_SOURCE_MISSING:{panel_id}:{label}"
            )
    return blockers


def compiled_prompt_blockers(
    prompt: str,
    *,
    panel_id: str,
    start: int,
    end: int,
) -> list[str]:
    blockers: list[str] = []
    character_count = len(prompt)
    if character_count > MAX_MULTI_PROMPT_CHARS:
        blockers.append(
            f"BLOCKED_PROVIDER_MULTI_PROMPT_MAX_512:{panel_id}:{character_count}"
        )
    lowered = prompt.casefold()
    required_literals = (
        panel_id,
        "kling v3 standard i2v",
        f"time range {start}s-{end}s",
        "@element1",
        "@element2",
        "embry",
        "kai",
    )
    for token in required_literals:
        if token.casefold() not in lowered:
            blockers.append(
                f"BLOCKED_PROVIDER_PROMPT_REQUIRED_TOKEN:{panel_id}:{token}"
            )
    for label, alternatives in PANEL_SOURCE_REQUIREMENTS[panel_id]:
        if not any(token.casefold() in lowered for token in alternatives):
            blockers.append(
                f"BLOCKED_PROVIDER_PROMPT_SEMANTIC_TOKEN:{panel_id}:{label}"
            )
    if panel_id == "sb_003":
        for token in ("no spoken dialogue", "no lip movement", "nonverbal hand signal"):
            if token not in lowered:
                blockers.append(
                    f"BLOCKED_PROVIDER_PROMPT_SILENCE_TOKEN:{panel_id}:{token}"
                )
        if any(pattern.search(prompt) for pattern in SPOKEN_PATTERNS):
            blockers.append("BLOCKED_PROVIDER_AUDIO_OFF_SPOKEN_DIALOGUE:sb_003")
    if re.search(r"\bPro\b", prompt, re.I):
        blockers.append(f"BLOCKED_PROVIDER_STANDARD_PRO_NAMING_CONFLICT:{panel_id}")
    match = TIME_RANGE_RE.search(prompt)
    if match is None or float(match.group(1)) != start or float(match.group(2)) != end:
        blockers.append(f"BLOCKED_PROVIDER_TIME_RANGE_CONTRADICTION:{panel_id}")
    return sorted(set(blockers))


def compile_concise_prompt(
    source_prompt: str,
    *,
    panel_id: str,
    start: int,
    end: int,
) -> str:
    source = re.sub(r"\s+", " ", source_prompt).strip()
    source_blockers = _source_semantic_blockers(source, panel_id)
    if source_blockers:
        raise PayloadBindingBlocked(
            source_blockers[0],
            details={"panel_id": panel_id, "blockers": source_blockers},
        )
    parts = [
        f"{panel_id.upper()}. Kling v3 Standard I2V. time range {start}s-{end}s.",
        PANEL_CONCISE_ACTIONS[panel_id],
        COMMON_CONTINUITY,
    ]
    if panel_id == "sb_003":
        parts.append(SB003_SILENCE)
    prompt = " ".join(parts)
    blockers = compiled_prompt_blockers(
        prompt, panel_id=panel_id, start=start, end=end
    )
    if blockers:
        raise PayloadBindingBlocked(
            blockers[0],
            details={
                "panel_id": panel_id,
                "character_count": len(prompt),
                "blockers": blockers,
            },
        )
    return prompt


def _normalized_prompts(phase10: Mapping[str, Any]) -> list[dict[str, str]]:
    raw = _phase10_prompts(phase10)
    result: list[dict[str, str]] = []
    elapsed = 0
    for index, expected_duration in enumerate(EXPECTED_DURATIONS):
        item = raw[index]
        try:
            duration = int(item.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0
        panel_id = f"sb_{index + 1:03d}"
        if duration != expected_duration:
            raise PayloadBindingBlocked(
                "BLOCKED_PROVIDER_SHOT_DURATION",
                details={"panel_id": panel_id, "observed": duration, "expected": expected_duration},
            )
        prompt = compile_concise_prompt(
            str(item.get("prompt") or ""),
            panel_id=panel_id,
            start=elapsed,
            end=elapsed + expected_duration,
        )
        result.append({"duration": str(expected_duration), "prompt": prompt})
        elapsed += expected_duration
    return result


def _contains_null(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, Mapping):
        return any(_contains_null(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_null(item) for item in value)
    return False


def build_payload_binding(
    *,
    context: Any,
    phase10_payload_path: Path,
    media_lock_path: Path,
    publication_commit: str,
    repository: str = DEFAULT_REPOSITORY,
) -> dict[str, Any]:
    publication_commit = publication_commit.lower()
    if not COMMIT_RE.fullmatch(publication_commit):
        raise PayloadBindingBlocked("BLOCKED_PHASE11_PUBLICATION_COMMIT_INVALID", details={"commit": publication_commit})
    _media_lock_assets(context, media_lock_path)
    phase10 = _read_object(
        phase10_payload_path,
        missing_code="BLOCKED_PHASE11_PHASE10_PAYLOAD_MISSING",
        invalid_code="BLOCKED_PHASE11_PHASE10_PAYLOAD_INVALID",
    )
    prompts = _normalized_prompts(phase10)

    frame_records = {
        artifact_id: _record(
            context,
            artifact_id,
            role=FRAME_ROLES[artifact_id],
            repository=repository,
            commit=publication_commit,
        )
        for artifact_id in FRAME_IDS
    }
    character_records: dict[str, dict[str, Any]] = {}
    for identity, suffix in CHARACTER_REFERENCE_SUFFIXES.items():
        artifact_id, _entry = _unique_artifact_by_suffix(context, suffix)
        character_records[identity] = _record(
            context,
            artifact_id,
            role="character_frontal",
            repository=repository,
            commit=publication_commit,
        )

    element_packs: list[dict[str, Any]] = []
    for index, identity in enumerate(("embry", "kai")):
        references = [frame_records[artifact_id] for artifact_id in ELEMENT_REFERENCE_IDS[identity]]
        element_packs.append(
            {
                "identity": identity,
                "prompt_token": f"@Element{index + 1}",
                "element_index": index,
                "frontal": character_records[identity],
                "references": references,
            }
        )

    preview = phase10.get("assembled_request_preview")
    phase10_input = preview.get("input") if isinstance(preview, Mapping) else {}
    negative_prompt = str(phase10_input.get("negative_prompt") or "blur, distort, and low quality").strip()
    if SPEECH_NEGATIVE.lower() not in negative_prompt.lower():
        negative_prompt = f"{negative_prompt.rstrip('; ')}; {SPEECH_NEGATIVE}"
    request_input = {
        "multi_prompt": prompts,
        "start_image_url": frame_records["sb_001.start_frame"]["public_url"],
        "duration": "10",
        "generate_audio": False,
        "end_image_url": frame_records["sb_004.end_frame"]["public_url"],
        "elements": [
            {
                "frontal_image_url": pack["frontal"]["public_url"],
                "reference_image_urls": [item["public_url"] for item in pack["references"]],
            }
            for pack in element_packs
        ],
        "shot_type": "customize",
        "negative_prompt": negative_prompt,
        "cfg_scale": phase10_input.get("cfg_scale", 0.5) if isinstance(phase10_input, Mapping) else 0.5,
    }
    if _contains_null(request_input):
        raise PayloadBindingBlocked("BLOCKED_PROVIDER_REQUEST_NULL_FIELD")

    next_command = [
        "skills/persona-dream/run.sh",
        "capture-phase11-public-media-evidence",
        "--run-root",
        "<RUN_ROOT>",
        "--revision-id",
        context.revision_id,
        "--json",
    ]
    binding = {
        "schema": PAYLOAD_BINDING_SCHEMA,
        "status": PAYLOAD_BINDING_STATUS,
        "gate_status": "BLOCKED_PROVIDER_GATE",
        "run_id": context.run_id,
        "revision_id": context.revision_id,
        "activation_transaction_id": context.activation_transaction_id,
        "source_commit": context.source_commit,
        "artifact_index_sha256": context.artifact_index_sha256,
        "phase10_payload_sha256": sha256_file(phase10_payload_path),
        "media_lock_sha256": sha256_file(media_lock_path),
        "provider": "fal.ai",
        "model": STANDARD_ENDPOINT,
        "mode": "standard",
        "publication": {
            "state": "UNPROBED_COMMIT_PINNED_URLS",
            "repository": repository,
            "commit": publication_commit,
            "provider_accessible_urls_proven": False,
            "publication_performed_by_this_command": False,
            "next_command": next_command,
        },
        "input": request_input,
        "media_roles": {
            "role_counts": {
                "global_start_anchor": 1,
                "global_end_anchor": 1,
                "continuity_only": 6,
                "element_packs": 2,
            },
            "global_start_anchor": frame_records["sb_001.start_frame"],
            "global_end_anchor": frame_records["sb_004.end_frame"],
            "continuity_only": [
                frame_records[artifact_id]
                for artifact_id in FRAME_IDS
                if FRAME_ROLES[artifact_id] == "continuity_only"
            ],
            "character_element_packs": element_packs,
        },
        "technical_gate": {
            "binding_built_from_active_revision": True,
            "request_asset_count": 7,
            "generate_audio": False,
            "provider_media_probes_passed": 0,
            "provider_media_probes_required": 7,
        },
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "paid_call_authorized": False,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "claims": {
            "proves": [
                "the request binding was derived from the active revision artifact index, Phase 10 payload, and media lock",
                "the request contains one start anchor, one end anchor, six continuity-only frames, and two character element packs",
            ],
            "does_not_prove": [
                "the URLs were fetched by fal or any provider",
                "public URL probes passed",
                "human approval or paid-call authorization",
                "provider submission or generation",
            ],
        },
    }
    validate_payload_binding(
        binding,
        context=context,
        phase10_payload_path=phase10_payload_path,
        media_lock_path=media_lock_path,
    )
    return binding


def _expected_url(context: Any, repository: str, commit: str, record: Mapping[str, Any]) -> str:
    return _raw_url(repository, commit, context, str(record.get("revision_relative_path") or ""))


def validate_payload_binding(
    binding: Mapping[str, Any],
    *,
    context: Any,
    phase10_payload_path: Path,
    media_lock_path: Path,
) -> dict[str, Any]:
    errors = schema_errors(binding)
    if errors:
        raise PayloadBindingBlocked("BLOCKED_PHASE11_PAYLOAD_BINDING_SCHEMA", details={"errors": errors})
    identity = {
        "run_id": context.run_id,
        "revision_id": context.revision_id,
        "activation_transaction_id": context.activation_transaction_id,
        "artifact_index_sha256": context.artifact_index_sha256,
        "phase10_payload_sha256": sha256_file(phase10_payload_path),
        "media_lock_sha256": sha256_file(media_lock_path),
    }
    mismatches = {
        field: {"expected": expected, "observed": binding.get(field)}
        for field, expected in identity.items()
        if binding.get(field) != expected
    }
    if mismatches:
        raise PayloadBindingBlocked("BLOCKED_PHASE11_PAYLOAD_BINDING_IDENTITY", details={"mismatches": mismatches})
    if binding.get("model") != STANDARD_ENDPOINT or binding.get("mode") != "standard":
        raise PayloadBindingBlocked(
            "BLOCKED_PROVIDER_STANDARD_PRO_MODE_MISMATCH",
            details={"model": binding.get("model"), "mode": binding.get("mode")},
        )
    publication = binding.get("publication")
    if not isinstance(publication, Mapping):
        raise PayloadBindingBlocked("BLOCKED_PHASE11_PAYLOAD_BINDING_PUBLICATION")
    repository = str(publication.get("repository") or "")
    commit = str(publication.get("commit") or "")
    if publication.get("state") != "UNPROBED_COMMIT_PINNED_URLS" or publication.get("provider_accessible_urls_proven") is not False:
        raise PayloadBindingBlocked("BLOCKED_PHASE11_PAYLOAD_BINDING_PUBLICATION_STATE")
    if not COMMIT_RE.fullmatch(commit):
        raise PayloadBindingBlocked("BLOCKED_PHASE11_PUBLICATION_COMMIT_INVALID")

    media_roles = binding.get("media_roles")
    if not isinstance(media_roles, Mapping):
        raise PayloadBindingBlocked("BLOCKED_MEDIA_ROLE_COUNTS")
    expected_counts = {
        "global_start_anchor": 1,
        "global_end_anchor": 1,
        "continuity_only": 6,
        "element_packs": 2,
    }
    if media_roles.get("role_counts") != expected_counts:
        raise PayloadBindingBlocked("BLOCKED_MEDIA_ROLE_COUNTS", details={"observed": media_roles.get("role_counts")})
    start = media_roles.get("global_start_anchor")
    end = media_roles.get("global_end_anchor")
    continuity = media_roles.get("continuity_only")
    packs = media_roles.get("character_element_packs")
    if not isinstance(start, Mapping) or start.get("artifact_id") != "sb_001.start_frame":
        raise PayloadBindingBlocked("BLOCKED_PHASE11_GLOBAL_START_ANCHOR")
    if not isinstance(end, Mapping) or end.get("artifact_id") != "sb_004.end_frame":
        raise PayloadBindingBlocked("BLOCKED_PHASE11_GLOBAL_END_ANCHOR")
    expected_continuity = [artifact_id for artifact_id in FRAME_IDS if FRAME_ROLES[artifact_id] == "continuity_only"]
    if not isinstance(continuity, list) or [item.get("artifact_id") for item in continuity if isinstance(item, Mapping)] != expected_continuity:
        raise PayloadBindingBlocked("BLOCKED_PHASE11_CONTINUITY_FRAME_SET")
    if not isinstance(packs, list) or len(packs) != 2 or [item.get("identity") for item in packs if isinstance(item, Mapping)] != ["embry", "kai"]:
        raise PayloadBindingBlocked("BLOCKED_CHARACTER_ELEMENT_PACK_COUNT")

    records: list[Mapping[str, Any]] = [start, end, *continuity]
    for pack in packs:
        if not isinstance(pack, Mapping):
            raise PayloadBindingBlocked("BLOCKED_CHARACTER_ELEMENT_PACK_COUNT")
        frontal = pack.get("frontal")
        references = pack.get("references")
        if not isinstance(frontal, Mapping) or not isinstance(references, list) or len(references) != 2:
            raise PayloadBindingBlocked("BLOCKED_CHARACTER_ELEMENT_PACK_IMAGE_COUNT", details={"identity": pack.get("identity")})
        records.extend([frontal, *[item for item in references if isinstance(item, Mapping)]])
    for record in records:
        artifact_id = str(record.get("artifact_id") or "")
        entry = _verified_entry(context, artifact_id)
        if record.get("sha256") != entry.get("sha256") or record.get("revision_relative_path") != entry.get("relative_path"):
            raise PayloadBindingBlocked("BLOCKED_PHASE11_PAYLOAD_BINDING_ARTIFACT_HASH", details={"artifact_id": artifact_id})
        parsed = urlparse(str(record.get("public_url") or ""))
        if f"/.persona-dream/revisions/{context.revision_id}/" not in parsed.path:
            raise PayloadBindingBlocked(
                "BLOCKED_PHASE11_PAYLOAD_BINDING_OLD_REVISION_URL",
                details={"artifact_id": artifact_id, "url": record.get("public_url")},
            )
        expected_url = _expected_url(context, repository, commit, record)
        if record.get("public_url") != expected_url:
            raise PayloadBindingBlocked(
                "BLOCKED_PHASE11_PAYLOAD_BINDING_URL_IDENTITY",
                details={"artifact_id": artifact_id, "expected": expected_url, "observed": record.get("public_url")},
            )

    request_input = binding.get("input")
    if not isinstance(request_input, Mapping) or _contains_null(request_input):
        raise PayloadBindingBlocked("BLOCKED_PROVIDER_REQUEST_NULL_FIELD")
    if request_input.get("start_image_url") != start.get("public_url") or request_input.get("end_image_url") != end.get("public_url"):
        raise PayloadBindingBlocked("BLOCKED_PROVIDER_ANCHOR_MAPPING")
    if request_input.get("generate_audio") is not False or request_input.get("duration") != "10":
        raise PayloadBindingBlocked("BLOCKED_PROVIDER_AUDIO_STRATEGY")
    prompts = request_input.get("multi_prompt")
    if not isinstance(prompts, list) or len(prompts) != 4:
        raise PayloadBindingBlocked("BLOCKED_PROVIDER_MULTI_PROMPT_CARDINALITY")
    elapsed = 0
    for index, expected_duration in enumerate(EXPECTED_DURATIONS):
        item = prompts[index]
        panel_id = f"sb_{index + 1:03d}"
        if not isinstance(item, Mapping) or str(item.get("duration")) != str(expected_duration):
            raise PayloadBindingBlocked("BLOCKED_PROVIDER_SHOT_DURATION", details={"panel_id": panel_id})
        prompt = str(item.get("prompt") or "")
        if re.search(r"\bPro\b", prompt, re.I) or "Kling v3 Standard I2V" not in prompt:
            raise PayloadBindingBlocked(
                "BLOCKED_PROVIDER_STANDARD_PRO_NAMING_CONFLICT",
                details={"panel_id": panel_id},
            )
        if panel_id == "sb_003" and any(pattern.search(prompt) for pattern in SPOKEN_PATTERNS):
            raise PayloadBindingBlocked(
                "BLOCKED_PROVIDER_AUDIO_OFF_SPOKEN_DIALOGUE",
                details={"panel_id": panel_id},
            )
        # The binding may be a historical source projection.  Provider validity
        # is established by the deterministic concise projection, not by reusing
        # its raw prompt bytes.
        compile_concise_prompt(
            prompt,
            panel_id=panel_id,
            start=elapsed,
            end=elapsed + expected_duration,
        )
        elapsed += expected_duration
    if elapsed != 10:
        raise PayloadBindingBlocked("BLOCKED_PROVIDER_TOTAL_DURATION", details={"observed": elapsed})
    elements = request_input.get("elements")
    if not isinstance(elements, list) or len(elements) != 2:
        raise PayloadBindingBlocked("BLOCKED_CHARACTER_ELEMENT_PACK_COUNT")
    for index, pack in enumerate(packs):
        element = elements[index]
        if not isinstance(element, Mapping):
            raise PayloadBindingBlocked("BLOCKED_CHARACTER_ELEMENT_PACK_COUNT")
        expected_frontal = pack["frontal"]["public_url"]
        expected_refs = [item["public_url"] for item in pack["references"]]
        if element.get("frontal_image_url") != expected_frontal or element.get("reference_image_urls") != expected_refs:
            raise PayloadBindingBlocked("BLOCKED_CHARACTER_ELEMENT_PACK_MAPPING", details={"identity": pack.get("identity")})
    for field, expected in {
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "paid_call_authorized": False,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
    }.items():
        if binding.get(field) != expected:
            raise PayloadBindingBlocked("BLOCKED_PROVIDER_ZERO_CALL_INVARIANT", details={"field": field})
    return dict(binding)


def load_and_validate_payload_binding(
    path: Path,
    *,
    context: Any,
    phase10_payload_path: Path,
    media_lock_path: Path,
) -> dict[str, Any]:
    value = _read_object(
        path,
        missing_code="BLOCKED_PHASE11_PAYLOAD_BINDING_MISSING",
        invalid_code="BLOCKED_PHASE11_PAYLOAD_BINDING_INVALID",
    )
    return validate_payload_binding(
        value,
        context=context,
        phase10_payload_path=phase10_payload_path,
        media_lock_path=media_lock_path,
    )


def payload_binding_blockers(
    path: Path,
    *,
    context: Any,
    phase10_payload_path: Path,
    media_lock_path: Path,
) -> list[str]:
    try:
        load_and_validate_payload_binding(
            path,
            context=context,
            phase10_payload_path=phase10_payload_path,
            media_lock_path=media_lock_path,
        )
    except PayloadBindingBlocked as exc:
        return [exc.code]
    return []


def write_payload_binding(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = pretty_bytes(value)
    if path.exists():
        existing = path.read_bytes()
        if existing != payload:
            raise PayloadBindingBlocked(
                "BLOCKED_PHASE11_PAYLOAD_BINDING_ALREADY_EXISTS_DIFFERENT",
                details={"path": str(path), "existing_sha256": "sha256:" + hashlib.sha256(existing).hexdigest(), "new_sha256": "sha256:" + hashlib.sha256(payload).hexdigest()},
            )
        return
    path.write_bytes(payload)
