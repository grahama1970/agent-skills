"""Transactional SQLite sessions; consent, time, revision, retention, and exact retry guards."""
import hmac
import secrets
import sqlite3
import time
import uuid
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from loguru import logger

from a_detection.analysis import analyze
from a_detection.contracts import (
    Analysis,
    Deletion,
    Edit,
    EventReceipt,
    EvidenceExport,
    Policy,
    SessionCreated,
    SessionRequest,
    Submit,
)
from a_detection.errors import Code, DetectionError
from a_detection.io import canonical, digest, strict_json, text_digest
from a_detection.model import ModelArtifact

EMPTY_SHA = text_digest("")


def apply_edit(source: str, event: Edit, policy: Policy) -> str:
    if event.start > len(source) or event.start + event.delete_count > len(source):
        raise DetectionError(Code.CONFLICT, "Edit range is outside the acknowledged revision.", 409)
    result = source[:event.start] + event.insert_text + source[event.start + event.delete_count:]
    if len(result) > policy.max_source_chars:
        raise DetectionError(Code.LIMIT, "Source exceeds policy.max_source_chars.", 413)
    if text_digest(result) != event.after_sha256:
        raise DetectionError(Code.INTEGRITY, "Edit result does not match its declared source digest.", 409)
    return result

class Store:
    """Stateful session persistence; each mutation runs in a separate immediate transaction."""
    def __init__(self, path: Path, policy: Policy, clock: Callable[[], float] = time.time):
        self.path, self.policy, self.clock = path, policy, clock
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.policy_sha256 = digest(canonical(policy.model_dump(mode="json")))
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                  id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, language TEXT NOT NULL,
                  created REAL NOT NULL, expires REAL NOT NULL, submitted REAL,
                  policy_hash TEXT NOT NULL, source TEXT NOT NULL DEFAULT '',
                  revision INTEGER NOT NULL DEFAULT 0, head TEXT NOT NULL,
                  analysis TEXT);
                CREATE TABLE IF NOT EXISTS events (
                  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                  event_id TEXT NOT NULL, seq INTEGER NOT NULL, payload_hash TEXT NOT NULL,
                  receipt TEXT NOT NULL, PRIMARY KEY(session_id, event_id),
                  UNIQUE(session_id, seq));
            """)
        path.chmod(0o600)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA secure_delete=ON")
        db.execute("PRAGMA busy_timeout=5000")
        # DELETE journaling avoids long-lived WAL copies, but is not a secure-erasure guarantee.
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                logger.error("classified_failure module=store")
                db.rollback()
                raise

    def _session(self, db: sqlite3.Connection, session_id: str, token: str, now: float | None = None) -> sqlite3.Row:
        row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        supplied = text_digest(token)
        if row is None or not hmac.compare_digest(row["token_hash"], supplied):
            raise DetectionError(Code.UNAUTHORIZED, "Session authorization failed.", 401)
        current = self.clock() if now is None else now
        if current < row["created"]:
            raise DetectionError(Code.CONFLICT, "Server clock moved before session creation.", 409)
        if current > row["created"] + self.policy.retention_seconds:
            raise DetectionError(Code.EXPIRED, "Session retention window expired.", 410)
        if row["policy_hash"] != self.policy_sha256:
            raise DetectionError(Code.CONFLICT, "Policy changed; start a new assessment session.", 409)
        return row

    def create(self, request: SessionRequest) -> dict:
        if request.consent is not True:
            raise DetectionError(Code.CONSENT_REQUIRED, "Consent is required.", 403)
        now = self.clock()
        identifier, token = uuid.uuid4().hex, secrets.token_urlsafe(32)
        with self.transaction() as db:
            db.execute("DELETE FROM sessions WHERE created < ?", (now - self.policy.retention_seconds,))
            if db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] >= self.policy.max_sessions:
                raise DetectionError(Code.LIMIT, "Local session capacity reached; delete old sessions.", 429)
            db.execute("""INSERT INTO sessions
                (id,token_hash,language,created,expires,policy_hash,head) VALUES (?,?,?,?,?,?,?)""",
                (identifier, text_digest(token), request.language, now,
                 now + self.policy.duration_seconds, self.policy_sha256, EMPTY_SHA))
        return SessionCreated.model_validate({"schema_version": "a_detection.session_created.v1", "session_id": identifier,
                "token": token, "created_at": now, "expires_at": now + self.policy.duration_seconds,
                "server_now": now, "revision": 0, "source_sha256": EMPTY_SHA,
                "policy_sha256": self.policy_sha256}).model_dump(mode="json")

    def append(self, session_id: str, token: str, event: Edit) -> EventReceipt:
        payload_hash = digest(canonical(event.model_dump(mode="json")))
        with self.transaction() as db:
            now = self.clock()
            session = self._session(db, session_id, token, now)
            existing = db.execute("SELECT payload_hash,receipt FROM events WHERE session_id=? AND event_id=?",
                                  (session_id, event.event_id)).fetchone()
            if existing:
                if not hmac.compare_digest(existing["payload_hash"], payload_hash):
                    raise DetectionError(Code.CONFLICT, "An event ID was reused with changed contents.", 409)
                return EventReceipt.model_validate(strict_json(existing["receipt"]))
            if session["submitted"] is not None:
                raise DetectionError(Code.CONFLICT, "Submitted sessions cannot be edited.", 409)
            if now >= session["expires"]:
                raise DetectionError(Code.EXPIRED, "The server assessment timer has expired.", 410)
            if event.seq != session["revision"] + 1 or event.base_revision != session["revision"]:
                raise DetectionError(Code.CONFLICT, "Sequence or base revision is stale.", 409)
            if event.seq > self.policy.max_events:
                raise DetectionError(Code.LIMIT, "Session event budget exhausted.", 413)
            last = db.execute("SELECT receipt FROM events WHERE session_id=? ORDER BY seq DESC LIMIT 1",
                              (session_id,)).fetchone()
            if last and now < EventReceipt.model_validate(strict_json(last[0])).received_at:
                raise DetectionError(Code.CONFLICT, "Server clock moved before the last receipt.", 409)
            source = apply_edit(session["source"], event, self.policy)
            payload = {"schema_version": "a_detection.event_receipt.v1", "session_id": session_id,
                       "revision": event.seq, "event": event.model_dump(mode="json"),
                       "received_at": now, "previous_sha256": session["head"]}
            payload["receipt_sha256"] = digest(canonical(payload))
            receipt = EventReceipt.model_validate(payload)
            db.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                       (session_id, event.event_id, event.seq, payload_hash,
                        canonical(receipt.model_dump(mode="json")).decode("utf-8")))
            db.execute("UPDATE sessions SET source=?,revision=?,head=? WHERE id=?",
                       (source, event.seq, receipt.receipt_sha256, session_id))
            return receipt

    def submit(self, session_id: str, token: str, request: Submit,
               model: ModelArtifact | None = None) -> Analysis:
        with self.transaction() as db:
            now = self.clock()
            row = self._session(db, session_id, token, now)
            if request.revision != row["revision"] or request.source_sha256 != text_digest(row["source"]):
                raise DetectionError(Code.CONFLICT, "Submission does not match the durable server revision.", 409)
            if row["submitted"] is not None:
                return Analysis.model_validate(strict_json(row["analysis"]))
            if now >= row["expires"]:
                raise DetectionError(Code.EXPIRED, "The server assessment timer has expired.", 410)
            received = db.execute("SELECT receipt FROM events WHERE session_id=? ORDER BY seq",
                                  (session_id,)).fetchall()
            if received and now < EventReceipt.model_validate(strict_json(received[-1][0])).received_at:
                raise DetectionError(Code.CONFLICT, "Server clock moved before the last receipt.", 409)
            counts = Counter(EventReceipt.model_validate(strict_json(item[0])).event.kind for item in received)
            result = analyze(row["source"], row["language"], self.policy, model,
                             {"event_count": row["revision"], "reported_pastes": counts["paste"],
                              "client_activity": "UNTRUSTED_REPORT_NOT_AUTHORSHIP"})
            db.execute("UPDATE sessions SET submitted=?,analysis=? WHERE id=?",
                       (now, canonical(result.model_dump(mode="json")).decode("utf-8"), session_id))
            return result

    def export(self, session_id: str, token: str) -> EvidenceExport:
        with self.transaction() as db:
            row = self._session(db, session_id, token)
            events = [EventReceipt.model_validate(strict_json(item[0])) for item in
                      db.execute("SELECT receipt FROM events WHERE session_id=? ORDER BY seq", (session_id,))]
            return EvidenceExport(
                session_id=session_id, language=row["language"], created_at=row["created"],
                expires_at=row["expires"], submitted_at=row["submitted"], policy_sha256=row["policy_hash"],
                events=events, source=row["source"], revision=row["revision"],
                source_sha256=text_digest(row["source"]), head_sha256=row["head"],
                analysis=Analysis.model_validate(strict_json(row["analysis"])) if row["analysis"] else None,
            )

    def delete(self, session_id: str, token: str) -> dict:
        # Deletion remains possible after the assessment deadline, before physical retention purge.
        with self.transaction() as db:
            row = db.execute("SELECT token_hash FROM sessions WHERE id=?", (session_id,)).fetchone()
            if row is None or not hmac.compare_digest(row[0], text_digest(token)):
                raise DetectionError(Code.UNAUTHORIZED, "Session authorization failed.", 401)
            db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
            remaining = db.execute("SELECT COUNT(*) FROM events WHERE session_id=?", (session_id,)).fetchone()[0]
            if remaining:
                raise DetectionError(Code.INTEGRITY, "Deletion readback found residual event rows.", 500)
        return Deletion().model_dump(mode="json")

    def purge(self) -> int:
        with self.transaction() as db:
            result = db.execute("DELETE FROM sessions WHERE created < ?",
                                (self.clock() - self.policy.retention_seconds,))
            return result.rowcount
