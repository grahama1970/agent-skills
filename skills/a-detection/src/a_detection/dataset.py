"""Strict JSONL corpus loading and fail-closed group, family, and duplicate split audits."""
from collections import defaultdict
from pathlib import Path
from typing import Literal

from loguru import logger
from pydantic import Field, model_validator

from a_detection.contracts import Strict
from a_detection.errors import Code, DetectionError
from a_detection.features import extract
from a_detection.io import strict_json, text_digest


class Record(Strict):
    sample_id: str = Field(min_length=1, max_length=160)
    session_id: str = Field(min_length=1, max_length=160)
    task_id: str = Field(min_length=1, max_length=160)
    author_id: str = Field(min_length=1, max_length=160)
    repository_id: str = Field(min_length=1, max_length=160)
    split: Literal["train", "tune", "calibration", "test"]
    language: Literal["python"]
    source: str = Field(min_length=1, max_length=64000)
    label: Literal["human", "machine", "hybrid", "unknown"]
    model_family: str | None = Field(default=None, max_length=160)
    origin: Literal["real", "synthetic"]
    provenance_ref: str = Field(min_length=1, max_length=500)
    collected_at: str = Field(min_length=10, max_length=40)

    @model_validator(mode="after")
    def require_provenance(self) -> "Record":
        from datetime import datetime
        try:
            when = datetime.fromisoformat(self.collected_at.replace("Z", "+00:00"))
        except ValueError as exc:
            logger.error("classified_failure module=dataset")
            raise ValueError("collected_at must be an ISO timestamp.") from exc
        if when.tzinfo is None:
            raise ValueError("collected_at must be timezone aware.")
        if self.label in ("machine", "hybrid") and not self.model_family:
            raise ValueError("Machine-assisted examples need a declared generator family.")
        if self.label == "human" and self.model_family is not None:
            raise ValueError("Human examples cannot declare a generating model family.")
        return self


def load_records(path: Path, allow_synthetic: bool = False) -> list[Record]:
    records: list[Record] = []
    total = 0
    with path.open("rb") as stream:
        while raw := stream.readline(400001):
            total += len(raw)
            if len(raw) > 400000 or total > 128_000_000 or len(records) >= 100000:
                raise DetectionError(Code.LIMIT, "Corpus exceeds the bounded JSONL loader limit.")
            if not raw.strip():
                continue
            record = Record.model_validate(strict_json(raw, 400000))
            if record.origin == "synthetic" and not allow_synthetic:
                raise DetectionError(Code.INVALID_INPUT, "Synthetic examples require --allow-synthetic.")
            records.append(record)
    if not records:
        raise DetectionError(Code.INVALID_INPUT, "Corpus is empty.")
    return records


def audit_splits(records: list[Record], require_all_splits: bool = True) -> dict:
    if len({row.sample_id for row in records}) != len(records):
        raise DetectionError(Code.LEAKAGE, "Duplicate sample IDs.")
    if require_all_splits and {row.split for row in records} != {"train", "tune", "calibration", "test"}:
        raise DetectionError(Code.LEAKAGE, "Four independent train/tune/calibration/test splits are required.")
    maps: dict[str, dict[str, set[str]]] = {
        key: defaultdict(set) for key in
        ("session", "task", "author", "repository", "source", "normalized")
    }
    sessions: dict[str, set[tuple[str, str | None]]] = defaultdict(set)
    for row in records:
        normalized = extract(row.source).normalized_sha256
        values = (row.session_id, row.task_id, row.author_id, row.repository_id,
                  text_digest(row.source), normalized)
        for key, value in zip(maps, values, strict=True):
            maps[key][value].add(row.split)
        sessions[row.session_id].add((row.label, row.model_family))
    for name, groups in maps.items():
        if any(len(splits) > 1 for splits in groups.values()):
            raise DetectionError(Code.LEAKAGE, f"Cross-split {name} overlap.")
    if any(len(labels) != 1 for labels in sessions.values()):
        raise DetectionError(Code.INVALID_INPUT, "A session has inconsistent labels or generator families.")
    known = {row.model_family for row in records if row.split != "test" and row.model_family}
    heldout = {row.model_family for row in records if row.split == "test" and row.model_family}
    if known & heldout:
        raise DetectionError(Code.LEAKAGE, "Test generator families were exposed before final testing.")
    for split in ("train", "tune", "calibration", "test"):
        if require_all_splits and not any(row.split == split and row.label == "human" for row in records):
            raise DetectionError(Code.INVALID_INPUT, "Each split needs human controls.")
    if require_all_splits and not heldout:
        raise DetectionError(Code.INVALID_INPUT, "Test split needs an unseen generator family.")
    from datetime import datetime
    times = [(row.split, datetime.fromisoformat(row.collected_at.replace("Z", "+00:00")))
             for row in records]
    pretest = [value for split, value in times if split != "test"]
    test = [value for split, value in times if split == "test"]
    return {
        "status": "PASS", "records": len(records),
        "heldout_families": sorted(heldout),
        "temporal_holdout": bool(test and pretest and min(test) > max(pretest)),
        "provenance": "DECLARED_NOT_INDEPENDENTLY_VERIFIED",
        "synthetic": any(row.origin == "synthetic" for row in records),
        "near_duplicate_scope": "Normalized-token exact duplicates only; semantic clones not exhausted.",
    }
