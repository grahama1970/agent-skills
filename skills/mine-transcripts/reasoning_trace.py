"""Deterministic reasoning-trace extraction lane.

Implements best-practices-reasoning-trace: parses CLI agent session
transcripts into reasoning.trace.v1 records with receipt-grounded outcome
event chains, attribution candidates, and mechanical feature observations.
No model calls. All judgment features are deliberately left to the flash
fanout; this lane emits only what code can prove.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA = "reasoning.trace.v1"

FeatureValue = Literal["present", "absent", "unknown", "not_applicable"]
AttributionStrength = Literal["unsupported", "ambiguous", "file_overlap_confirmed"]
OutcomeEventName = Literal["integrated", "evaluation_passed", "rejected", "reverted"]
ResponseClass = Literal["satisfied", "frustrated", "correction", "new_task", "silence", "unknown"]


class ToolCallRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int
    tool: str
    args_digest: str = Field(min_length=8)
    outcome: Literal["ok", "error", "unknown"] = "unknown"


class FeatureObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: FeatureValue
    scored_by: Literal["deterministic"] = "deterministic"
    evidence: str = ""


class OutcomeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: OutcomeEventName
    observed_at: str
    commit_sha: str | None = None
    attribution: AttributionStrength = "unsupported"
    attribution_method: Literal["file_overlap", "explicit_human", "revert_commit", "none"] = "none"
    reason: str = ""
    observed_through: str = ""


class RequestInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text_excerpt: str = Field(max_length=500)
    action: str = "QUERY"
    domain: str | None = None
    classification: Literal["heuristic", "deterministic"] = "heuristic"


class ReasoningTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_name: Literal["reasoning.trace.v1"] = Field(default=SCHEMA, alias="schema")
    key: str = Field(min_length=1, alias="_key")
    source: Literal["pi", "codex", "claude", "cursor", "ask"]
    session_path: str
    repo: str | None = None
    model: str | None = None
    started_at: str | None = None
    last_activity_at: str | None = None
    observed_through: str = ""
    task_kind: Literal["artifact_producing", "analysis_only", "unknown"] = "unknown"
    request: RequestInfo
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    tool_sequence: list[str] = Field(default_factory=list)
    answer_excerpt: str = Field(default="", max_length=500)
    deterministic_features: list[FeatureObservation] = Field(default_factory=list)
    outcome_events: list[OutcomeEvent] = Field(default_factory=list)
    user_response_class: ResponseClass = "unknown"
    user_response_excerpt: str = Field(default="", max_length=300)
    eligible_for: list[str] = Field(default_factory=list)
    artifact_path: str = ""
    tags: list[str] = Field(default_factory=list)
    retrieval_text: str = Field(min_length=1)

    def to_memory_doc(self) -> dict[str, Any]:
        doc = self.model_dump(mode="json", by_alias=True)
        doc.pop("schema_name", None)
        return doc


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(tool: str, args: Any) -> str:
    canonical = json.dumps({"tool": tool, "args": args}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _resolve_repo(cwd: str | None, session_file: Path) -> str | None:
    """Authoritative repo from the session header cwd; token decode as fallback."""
    if cwd and Path(cwd).exists():
        return cwd
    return _repo_from_session_dir(session_file)


def _repo_from_session_dir(session_file: Path) -> str | None:
    # Session tree token encodes cwd with '/' as '--'; real hyphens stay '-'.
    try:
        token = session_file.parts[session_file.parts.index("sessions") + 1]
    except (ValueError, IndexError):
        return None
    if not token.startswith("--"):
        return None
    segments = [s for s in token.split("--") if s]
    if not segments:
        return None
    path = "/" + "/".join(segments)
    return path if Path(path).exists() else None


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _extract_text(content: list[dict[str, Any]]) -> str:
    return "\n".join(c.get("text", "") for c in content if c.get("type") == "text").strip()


def _looks_error(result_text: str) -> bool:
    head = result_text[:300].lower()
    return any(m in head for m in ("traceback", "exit code 1", "exit code 2", "error:", "commandnotfound", "no such file"))


CORRECTION_MARKERS = ("no,", "wrong", "instead", "actually", "not what", "don't", "do not", "you mis")
SATISFACTION_MARKERS = ("perfect", "thanks", "great", "verified", "exactly", "good")


def _classify_response(text: str) -> ResponseClass:
    low = text.lower()
    if any(m in low for m in CORRECTION_MARKERS):
        return "correction"
    if any(m in low for m in SATISFACTION_MARKERS):
        return "satisfied"
    return "unknown"


WRITE_TOOLS = {"edit", "write", "apply_patch", "applypatch"}
READ_TOOLS = {"read", "grep", "find", "ls"}


def _paths_from_args(tool: str, args: dict[str, Any]) -> set[str]:
    keys = ("path", "file", "target")
    out = set()
    for k in keys:
        v = args.get(k)
        if isinstance(v, str):
            out.add(v)
    return out


def parse_pi_session(session_file: Path) -> ReasoningTrace | None:
    """Parse one Pi session.jsonl into a trace with deterministic fields only."""
    events: list[dict[str, Any]] = []
    model_id = None
    started_at = None
    last_at = None
    session_cwd = None
    with session_file.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") == "model_change":
                model_id = d.get("modelId")
            if d.get("type") == "session":
                started_at = d.get("timestamp")
                session_cwd = d.get("cwd")
            if d.get("type") == "message":
                events.append(d)
                last_at = d.get("timestamp", last_at)
    if not events or started_at is None:
        return None

    tool_calls: list[ToolCallRecord] = []
    tool_seq: list[str] = []
    pending: dict[str, ToolCallRecord] = {}
    written_paths: set[str] = set()
    read_paths: set[str] = set()
    first_user_text = ""
    last_answer_text = ""
    last_user_after_answer = ""
    saw_write = False
    read_before_first_write = False

    for ev in events:
        msg = ev.get("message", {})
        role = msg.get("role")
        content = msg.get("content", [])
        if role == "assistant":
            for c in content:
                if c.get("type") == "toolCall":
                    name = c.get("name", "?")
                    args = c.get("arguments", {}) or {}
                    rec = ToolCallRecord(seq=len(tool_calls), tool=name, args_digest=_digest(name, args))
                    tool_calls.append(rec)
                    tool_seq.append(name)
                    pending[c.get("id", rec.args_digest)] = rec
                    if name in WRITE_TOOLS:
                        saw_write = True
                        written_paths |= _paths_from_args(name, args)
                    is_read = name in READ_TOOLS or (
                        name == "bash"
                        and isinstance(args.get("command"), str)
                        and args["command"].lstrip().startswith(("cat ", "head ", "grep ", "rg ", "sed -n", "less ", "tail "))
                    )
                    if is_read:
                        if not saw_write:
                            read_before_first_write = True
                        read_paths |= _paths_from_args(name, args)
            text = _extract_text(content)
            if text:
                last_answer_text = text
        elif role == "toolResult":
            body = _extract_text(content) or json.dumps(content)[:200]
            call_id = msg.get("toolCallId")
            if call_id and call_id in pending:
                pending[call_id].outcome = "error" if _looks_error(body) else "ok"
            elif call_id and "|" in str(call_id):
                base = call_id.split("|")[0]
                if base in pending:
                    pending[base].outcome = "error" if _looks_error(body) else "ok"
        elif role == "user":
            text = _extract_text(content)
            if not text:
                continue
            if not first_user_text:
                first_user_text = text
            elif last_answer_text:
                if not last_user_after_answer:
                    last_user_after_answer = text

    if not first_user_text:
        return None

    sig_counts: dict[str, int] = {}
    for tc in tool_calls:
        sig_counts[tc.args_digest] = sig_counts.get(tc.args_digest, 0) + 1
    repeated = sum(1 for v in sig_counts.values() if v > 1)
    readback = bool(written_paths & read_paths) if written_paths else None

    features = [
        FeatureObservation(name="repeated_call_signature", value="present" if repeated else "absent", evidence=f"{repeated} digests appeared more than once; raw signal, appropriateness unjudged"),
        FeatureObservation(name="read_before_first_write", value=("present" if read_before_first_write else "absent") if tool_calls else "not_applicable"),
        FeatureObservation(
            name="read_after_write",
            value=("present" if readback else "absent") if written_paths else "not_applicable",
            evidence="path-level read/write overlap via file tools; bash reads not tracked in v1",
        ),
        FeatureObservation(name="final_turn_had_tool", value=("present" if tool_seq and events else "unknown")),
    ]
    # final_turn_had_tool: did the last assistant message contain a toolCall?
    last_assistant = next((e for e in reversed(events) if e.get("message", {}).get("role") == "assistant"), None)
    if last_assistant is not None:
        features[-1].value = "present" if any(c.get("type") == "toolCall" for c in last_assistant["message"].get("content", [])) else "absent"

    key = "trace:pi:" + hashlib.sha256(str(session_file).encode()).hexdigest()[:24]
    repo = _resolve_repo(session_cwd, session_file)
    resp_class = _classify_response(last_user_after_answer) if last_user_after_answer else "silence"
    task_kind = "artifact_producing" if written_paths else "analysis_only"
    excerpt = first_user_text[:400]
    summary = (
        f"Pi session in {repo or 'unknown repo'} (model {model_id or 'unknown'}, {len(tool_calls)} tool calls, "
        f"task {task_kind}). Request: {excerpt[:180]}. Outcome events: none extracted by deterministic pass. "
        f"User response class: {resp_class}."
    )
    return ReasoningTrace(
        key=key,
        source="pi",
        session_path=str(session_file),
        repo=repo,
        model=model_id,
        started_at=started_at,
        last_activity_at=last_at,
        observed_through=_now(),
        task_kind=task_kind,
        request=RequestInfo(text_excerpt=excerpt, domain=Path(repo).name if repo else None),
        tool_calls=tool_calls,
        tool_sequence=tool_seq[:120],
        answer_excerpt=last_answer_text[:400],
        deterministic_features=features,
        user_response_class=resp_class,
        user_response_excerpt=last_user_after_answer[:250],
        eligible_for=[],
        artifact_path=str(session_file),
        tags=["reasoning-trace", f"task:{task_kind}", f"response:{resp_class}"],
        retrieval_text=summary,
    )


def git_outcome_events(trace: ReasoningTrace, window_min: int = 15) -> list[OutcomeEvent]:
    """Join last activity to git commits. Timestamp proximity yields CANDIDATES;
    file overlap upgrades to file_overlap_confirmed; never claims more."""
    events: list[OutcomeEvent] = []
    if not trace.repo or not trace.last_activity_at or trace.task_kind != "artifact_producing":
        return events
    repo = Path(trace.repo)
    if not (repo / ".git").exists():
        return events
    try:
        at = _parse_iso(trace.last_activity_at)
        start = _parse_iso(trace.started_at) if trace.started_at else at
    except ValueError:
        return events
    # Window spans the whole session: long sessions land commits mid-session,
    # not near the end. File overlap disambiguates the wider window.
    since = (start - timedelta(minutes=window_min)).isoformat()
    until = (at + timedelta(minutes=window_min)).isoformat()
    try:
        log = subprocess.run(
            ["git", "-C", str(repo), "log", "--all", f"--since={since}", f"--until={until}", "--pretty=%H|%cI|%s"],
            capture_output=True, text=True, timeout=20,
        )
    except subprocess.TimeoutExpired:
        return events
    written = {p for p in _written_paths_from_trace(trace)}
    now = _now()
    for row in log.stdout.strip().splitlines():
        if not row:
            continue
        sha, cts, subject = row.split("|", 2)
        strength: AttributionStrength = "ambiguous"
        method: OutcomeEvent.attribution_method = "none"  # type: ignore[assignment]
        if written:
            names = subprocess.run(["git", "-C", str(repo), "show", "--name-only", "--pretty=format:", sha], capture_output=True, text=True, timeout=20)
            changed = {n.strip() for n in names.stdout.splitlines() if n.strip()}
            overlap = {str(Path(w).relative_to(repo)) if str(w).startswith(str(repo)) else str(w) for w in written} & changed
            if overlap:
                strength = "file_overlap_confirmed"
                method = "file_overlap"
        events.append(OutcomeEvent(event="integrated", observed_at=cts, commit_sha=sha, attribution=strength, attribution_method=method, reason=subject[:200], observed_through=now))
    return events


def _written_paths_from_trace(trace: ReasoningTrace) -> set[str]:
    """Re-derive written paths from tool sequence recorded in the trace file."""
    # tool_calls records digests only; re-read session for paths in v1
    out: set[str] = set()
    try:
        with open(trace.session_path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("type") != "message":
                    continue
                msg = d.get("message", {})
                if msg.get("role") != "assistant":
                    continue
                for c in msg.get("content", []):
                    if c.get("type") == "toolCall" and c.get("name") in WRITE_TOOLS:
                        out |= _paths_from_args(c.get("name", ""), c.get("arguments", {}) or {})
    except OSError:
        pass
    return {str(Path(p).resolve()) for p in out if p}


def store_memory(traces: list[ReasoningTrace], base_url: str) -> dict[str, Any]:
    import httpx

    docs = [t.to_memory_doc() for t in traces]
    resp = httpx.post(f"{base_url.rstrip('/')}/upsert", json={"collection": "reasoning_traces", "documents": docs}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic reasoning-trace extraction")
    ap.add_argument("--sessions-root", default=str(Path.home() / ".pi/agent/sessions"))
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--min-bytes", type=int, default=20_000)
    ap.add_argument("--out", default="data/reasoning_traces.jsonl")
    ap.add_argument("--store-memory", action="store_true")
    ap.add_argument("--memory-url", default="http://127.0.0.1:8601")
    ap.add_argument("--json-summary", action="store_true")
    args = ap.parse_args()

    root = Path(args.sessions_root)
    files = sorted(
        {p for p in root.rglob("session.jsonl") if p.stat().st_size >= args.min_bytes}
        | {p for p in root.glob("*.jsonl") if p.stat().st_size >= args.min_bytes},
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    traces: list[ReasoningTrace] = []
    for f in files[: args.limit]:
        t = parse_pi_session(f)
        if t is None:
            continue
        t.outcome_events = git_outcome_events(t)
        if t.outcome_events:
            t.tags.append("outcome:has_candidates")
        traces.append(t)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for t in traces:
            fh.write(json.dumps(t.to_memory_doc(), ensure_ascii=False) + "\n")

    memory_status = "skipped"
    if args.store_memory and traces:
        try:
            store_memory(traces, args.memory_url)
            memory_status = "stored"
        except Exception as exc:  # noqa: BLE001 - report, never crash the lane
            memory_status = f"failed: {exc}"

    summary = {
        "schema": "mine_reasoning.run_summary.v1",
        "scanned": len(files[: args.limit]),
        "extracted": len(traces),
        "with_outcome_candidates": sum(1 for t in traces if t.outcome_events),
        "memory": memory_status,
        "out": str(out_path),
        "validated_by": "pydantic reasoning.trace.v1",
    }
    print(json.dumps(summary, indent=2) if args.json_summary else json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
