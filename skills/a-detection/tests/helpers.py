"""Synthetic test construction only; never label these examples as real human evidence."""
import hashlib
import uuid

from a_detection.contracts import Edit
from a_detection.dataset import Record


def edit(source, inserted, seq=1, start=0, delete_count=0, kind="input"):
    result = source[:start] + inserted + source[start + delete_count:]
    return Edit(event_id=uuid.uuid4().hex, seq=seq, base_revision=seq - 1,
                start=start, delete_count=delete_count, insert_text=inserted,
                after_sha256=hashlib.sha256(result.encode("utf-8")).hexdigest(),
                kind=kind, client_elapsed_ms=float(seq)), result


def corpus():
    """All groups and normalized code structures differ across the four splits."""
    rows = []
    for split_index, split in enumerate(("train", "tune", "calibration", "test")):
        for label in ("human", "machine"):
            for index in range(6):
                count = 2 + split_index * 12 + index
                source = "def solve(value):\n    result = value\n"
                operation = "    result += 1\n" if label == "human" else "    result = abs(result)\n"
                source += operation * count + "    return result\n"
                identity = f"{split}-{label}-{index}"
                rows.append(Record(sample_id=identity, session_id=identity,
                    task_id=identity, author_id=identity, repository_id=identity,
                    split=split, language="python", source=source, label=label,
                    model_family=("synthetic-heldout" if split == "test" else "synthetic-training")
                        if label == "machine" else None,
                    origin="synthetic", provenance_ref="tests/helpers.py; simulated role, not a human",
                    collected_at=f"2026-09-{split_index + 1:02d}T00:00:00+00:00"))
    return rows
