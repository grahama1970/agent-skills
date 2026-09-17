"""Real SQLite evidence transactions and independent adversarial readback; no mock database."""
import json
import secrets
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pytest

from a_detection.contracts import EvidenceExport, Policy, SessionRequest, Submit
from a_detection.errors import Code, DetectionError
from a_detection.store import Store
from a_detection.verify import verify_export
from tests.helpers import edit


@dataclass
class Clock:
    value: float = 1700000000.0
    def __call__(self):
        return self.value


def session(tmp_path, policy=None, clock=None):
    store = Store(tmp_path / "sessions.sqlite3", policy or Policy(), **({"clock": clock} if clock else {}))
    details = store.create(SessionRequest(consent=True))
    return store, details["session_id"], details["token"]


def test_unicode_roundtrip_and_final_submission(tmp_path):
    store, sid, token = session(tmp_path)
    first, source = edit("", "# 🧪 café é\nvalue = '𐐀'\n")
    receipt = store.append(sid, token, first)
    assert store.append(sid, token, first) == receipt
    second, source = edit(source, "雪", 2, source.index("𐐀"), 1)
    store.append(sid, token, second)
    result = store.submit(sid, token, Submit(revision=2, source_sha256=second.after_sha256))
    exported = store.export(sid, token)
    assert exported.source == source
    assert verify_export(exported)["event_count"] == 2
    assert result.disposition == "INSUFFICIENT_EVIDENCE"
    assert store.submit(sid, token, Submit(revision=2, source_sha256=second.after_sha256)) == result
    with pytest.raises(DetectionError):
        store.append(sid, token, edit(source, "# extra", 3)[0])


@pytest.mark.parametrize("change", ["stale", "wrong_hash", "changed_retry", "wrong_token", "range"])
def test_mutation_guards_preserve_durable_state(tmp_path, change):
    store, sid, token = session(tmp_path)
    event, source = edit("", "x = 1\n")
    store.append(sid, token, event)
    if change == "changed_retry":
        broken = event.model_copy(update={"kind": "paste"})
    else:
        broken = edit(source, "# next", 2)[0]
        if change == "stale":
            broken = broken.model_copy(update={"base_revision": 0})
        if change == "wrong_hash":
            broken = broken.model_copy(update={"after_sha256": "f" * 64})
        if change == "range":
            broken = broken.model_copy(update={"start": 1000})
    with pytest.raises(DetectionError):
        store.append(sid, "wrong-token" if change == "wrong_token" else token, broken)
    assert store.export(sid, token).source == source
    assert store.export(sid, token).revision == 1


def test_server_clock_not_client_clock_controls_deadline(tmp_path):
    clock = Clock()
    store, sid, token = session(tmp_path, Policy(duration_seconds=2), clock)
    clock.value += 3
    with pytest.raises(DetectionError) as failure:
        store.append(sid, token, edit("", "x = 1")[0])
    assert failure.value.code == Code.EXPIRED
    with pytest.raises(DetectionError):
        store.submit(sid, token, Submit(revision=0, source_sha256=store.export(sid, token).source_sha256))
    assert store.delete(sid, token)["deleted"] is True


def test_policy_dependency_mutation_changes_acceptance(tmp_path):
    root = Path(__file__).resolve().parents[1]
    spec = json.loads((root / "specs/policy.json").read_text())
    observed = []
    for limit in (100, 200):
        declared = dict(spec, max_source_chars=limit)
        policy = Policy.model_validate(declared)
        store, sid, token = session(tmp_path / str(limit), policy)
        event, _ = edit("", "x" * 150)
        try:
            store.append(sid, token, event)
            observed.append("ACCEPT")
        except DetectionError as error:
            observed.append(error.code.value)
    assert observed == ["resource_limit", "ACCEPT"]


def test_retention_and_deletion_readback(tmp_path):
    clock = Clock()
    store, sid, token = session(tmp_path, Policy(retention_seconds=60), clock)
    store.append(sid, token, edit("", "private = 'retention-test'")[0])
    clock.value += 61
    assert store.purge() == 1
    with sqlite3.connect(store.path) as independent:
        assert independent.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
        assert independent.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    with pytest.raises(DetectionError):
        store.export(sid, token)


def test_concurrent_retry_has_one_event(tmp_path):
    store, sid, token = session(tmp_path)
    event, _ = edit("", "value = 1")
    with ThreadPoolExecutor(max_workers=8) as executor:
        receipts = list(executor.map(lambda _: store.append(sid, token, event), range(16)))
    assert len({row.receipt_sha256 for row in receipts}) == 1
    assert store.export(sid, token).revision == 1


@pytest.mark.parametrize("field", ["source", "head_sha256", "revision", "session_id", "event_digest", "event_time"])
def test_independent_checker_rejects_changed_evidence(tmp_path, field):
    store, sid, token = session(tmp_path)
    store.append(sid, token, edit("", "x = '🧪'")[0])
    payload = store.export(sid, token).model_dump(mode="json")
    if field == "source":
        payload["source"] = "x = 'changed'"
    elif field == "head_sha256":
        payload[field] = "f" * 64
    elif field == "revision":
        payload[field] = 2
    elif field == "session_id":
        payload[field] = "f" * 32
    elif field == "event_digest":
        payload["events"][0]["receipt_sha256"] = "f" * 64
    elif field == "event_time":
        payload["events"][0]["received_at"] = payload["expires_at"] + 1
    with pytest.raises(DetectionError):
        verify_export(EvidenceExport.model_validate(payload))


def test_fresh_unicode_edit_sequences(tmp_path, samples):
    store, sid, token = session(tmp_path, Policy(max_events=samples + 1))
    source = ""
    alphabet = ["a", "雪", "🧪", "é", "\n", "'", "\t", "𐐀", " "]
    for index in range(1, samples + 1):
        start = secrets.randbelow(len(source) + 1)
        delete = secrets.randbelow(len(source) - start + 1)
        inserted = "".join(secrets.choice(alphabet) for _ in range(secrets.randbelow(8)))
        event, expected = edit(source, inserted, index, start, delete)
        store.append(sid, token, event)
        exported = store.export(sid, token)
        assert exported.source == expected
        assert verify_export(exported)["event_count"] == index
        source = expected


def test_backwards_server_clock_rejected(tmp_path):
    clock = Clock()
    store, sid, token = session(tmp_path, clock=clock)
    clock.value += 5
    first, source = edit("", "x = 1")
    store.append(sid, token, first)
    clock.value -= 1
    with pytest.raises(DetectionError):
        store.append(sid, token, edit(source, "# next", 2)[0])
    with pytest.raises(DetectionError):
        store.submit(sid, token, Submit(revision=1, source_sha256=first.after_sha256))
    assert verify_export(store.export(sid, token))["status"] == "PASS"
