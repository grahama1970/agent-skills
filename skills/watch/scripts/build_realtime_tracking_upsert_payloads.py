"""Build dry-run memory /upsert payloads for Watch real-time tracking.

This is intentionally offline. It validates a deterministic tracker event log
against the Watch observation event schema, checks that the event stream matches
the accepted memory manifest, and emits concrete memory daemon /upsert request
bodies without posting them.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


DEFAULT_ARCH_DIR = Path(__file__).resolve().parents[1] / "docs" / "architecture"
DEFAULT_MANIFEST = DEFAULT_ARCH_DIR / "watch_realtime_tracking_memory_upsert_manifest.bad_santa_marcus.json"
DEFAULT_EVENTS = DEFAULT_ARCH_DIR / "watch_tracker_event_log.bad_santa_marcus.fixture.jsonl"
DEFAULT_SCHEMA = DEFAULT_ARCH_DIR / "watch_track_observations.schema.json"
DEFAULT_OUT_DIR = DEFAULT_ARCH_DIR / "generated" / "bad_santa_marcus_0248_upsert_payloads"

FORBIDDEN_VECTOR_KEYS = {"embedding", "embeddings", "vector", "vectors", "dense_vector"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    manifest = _read_json(args.manifest)
    events = _read_events(args.events, args.schema)
    _assert_manifest_is_dry_run(manifest)
    _assert_events_match_manifest(events, manifest)
    _assert_no_raw_vectors(manifest)

    payloads = _build_payloads(manifest)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for collection, payload in payloads.items():
        path = args.out_dir / f"upsert_{collection}.json"
        _write_json(path, payload)
        written.append(_display_path(path))

    summary = {
        "schema_version": "watch.realtime_tracking_upsert_payload_summary.v1",
        "status": "DRY_RUN_ONLY",
        "posted": False,
        "manifest_id": manifest.get("manifest_id"),
        "source_manifest": _display_path(args.manifest),
        "source_events": _display_path(args.events),
        "event_count": len(events),
        "track_ids": sorted({event["track_id"] for event in events}),
        "segment_ids": sorted({event["segment_id"] for event in events}),
        "time_bounds_seconds": {
            "start": min(event["media_time_seconds"] for event in events),
            "end": max(event["media_time_seconds"] for event in events),
        },
        "payload_files": written,
        "payload_counts": {
            collection: len(payload["documents"])
            for collection, payload in payloads.items()
        },
        "claim_boundary": (
            "Payloads are request-shape proof only. This does not prove live "
            "memory writes, Qdrant vector writes, live tracker inference, or recall."
        ),
    }
    summary_path = args.out_dir / "summary.json"
    _write_json(summary_path, summary)

    print("dry_run_payloads_ok", len(payloads))
    print("event_count", len(events))
    print("track_ids", summary["track_ids"])
    print("payload_counts", summary["payload_counts"])
    print("out_dir", args.out_dir)
    return 0


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"expected JSON object: {path}")
    return data


def _read_events(events_path: Path, schema_path: Path) -> list[dict[str, Any]]:
    schema = _read_json(schema_path)
    event_schema = dict(schema["$defs"]["live_track_update_event"])
    event_schema["$defs"] = schema["$defs"]
    validator = Draft202012Validator(event_schema)
    events: list[dict[str, Any]] = []
    for index, line in enumerate(events_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        event = json.loads(line)
        errors = sorted(validator.iter_errors(event), key=lambda error: error.path)
        if errors:
            details = "; ".join(
                f"{list(error.path)}: {error.message}" for error in errors
            )
            raise ValueError(f"event {index} failed schema validation: {details}")
        events.append(event)
    if not events:
        raise ValueError(f"no events found: {events_path}")
    return events


def _assert_manifest_is_dry_run(manifest: dict[str, Any]) -> None:
    if manifest.get("status") != "DRY_RUN_ONLY":
        raise ValueError("manifest status must be DRY_RUN_ONLY")
    write_mode = manifest.get("write_mode", {})
    if write_mode.get("execute") is not False:
        raise ValueError("manifest write_mode.execute must be false")


def _assert_events_match_manifest(events: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    observations = manifest.get("collections", {}).get("watch_track_observations", [])
    if not observations:
        raise ValueError("manifest has no watch_track_observations")
    observation_keys = {
        (
            obs.get("stream_id"),
            obs.get("asset_uid"),
            obs.get("segment_id"),
            obs.get("track_id"),
        )
        for obs in observations
    }
    for index, event in enumerate(events, start=1):
        key = (
            event.get("stream_id"),
            event.get("asset_uid"),
            event.get("segment_id"),
            event.get("track_id"),
        )
        if key not in observation_keys:
            raise ValueError(f"event {index} does not match a manifest observation: {key}")
    final_events = [event for event in events if event.get("status") == "BOUNDARY_CANDIDATE"]
    if not final_events:
        raise ValueError("event log must include at least one BOUNDARY_CANDIDATE event")


def _assert_no_raw_vectors(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_VECTOR_KEYS:
                raise ValueError(f"raw vector-like field is forbidden at {child_path}")
            _assert_no_raw_vectors(child, child_path)
    elif isinstance(value, list):
        if len(value) > 8 and all(isinstance(item, (int, float)) for item in value):
            raise ValueError(f"raw numeric vector array is forbidden at {path}")
        for index, child in enumerate(value):
            _assert_no_raw_vectors(child, f"{path}[{index}]")


def _build_payloads(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    collections = manifest["collections"]
    payloads: dict[str, dict[str, Any]] = {}
    for request in manifest["memory_upsert_request_plan"]:
        collection = request["collection"]
        documents = collections.get(collection)
        if not isinstance(documents, list) or not documents:
            raise ValueError(f"request collection has no documents: {collection}")
        payloads[collection] = {
            "collection": collection,
            "documents": documents,
        }
    return payloads


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
