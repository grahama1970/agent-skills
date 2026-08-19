"""Read-only debugger proof lane (#1450).

Composes the sibling debugger skill (capture_breakpoints.py +
validate_debugger_proof.py) instead of copying its implementation. Fail-closed
by construction:

- the frozen session policy gates invocation BEFORE any subprocess exists;
- the repository identity in the request is compared against the working tree
  before capture, and again against the request digest bound into the outcome;
- a proof becomes evidence only after the debugger skill's own independent
  validator passes AND this adapter's readback confirms an actually-verified
  stop at the requested location -- producer-authored ``proofValid`` alone is
  never trusted;
- outcomes are revision-fenced by the caller through the same
  compare-and-swap card publication used by every other lane.

No mutation path exists here: the request type pins allowed_effects to
read_only at the schema level.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .models import DebugRequest


def default_debugger_root() -> Path | None:
    candidate = Path(__file__).resolve().parents[3] / "debugger"
    return candidate if (candidate / "scripts" / "capture_breakpoints.py").exists() else None


def repository_digest(root: Path) -> str:
    """Current repository identity: commit sha, else deterministic tree digest."""

    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    import hashlib

    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*.py") if p.is_file()):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def verified_stop_matches(canonical: dict[str, Any], request: DebugRequest) -> list[dict[str, Any]]:
    """Stops that are independently verified AND at a requested location.

    Producer-authored assessment fields are ignored here on purpose: only the
    validator-emitted per-breakpoint hit/verified flags plus exact file:line
    equality with the request count.
    """

    verified_stops = [
        bp for bp in canonical.get("breakpoints") or []
        if bp.get("hit") is True and bp.get("verified") is True
    ]
    requested = {
        (str(Path(bp.file).resolve()), bp.line)
        for bp in request.requested_breakpoints
    }
    return [
        bp for bp in verified_stops
        if (str(Path(str(bp.get("file"))).resolve()), int(bp.get("line") or 0)) in requested
    ]


class DebuggerLane:
    """One bounded read-only escalation lane over the debugger skill."""

    def __init__(self, debugger_root: Path | None = None, work_dir: Path | None = None) -> None:
        self._debugger_root = debugger_root or default_debugger_root()
        self._work_dir = work_dir or Path("/tmp/live-evidence-debugger")
        self._seen_digests: dict[str, dict[str, Any]] = {}

    def run(self, request: DebugRequest, *, debugger_invocation_allowed: bool) -> dict[str, Any]:
        """Execute one request. Returns a typed outcome; never raises for
        policy/validation failures -- those are journaled outcomes, not crashes.

        outcome["result"] is one of:
        blocked_by_policy | duplicate_request | blocked_missing_capability |
        rejected_repository_mismatch | capture_failed | no_breakpoint_hit |
        proof_invalid | stop_mismatch | supported
        Only "supported" may back a supported card.
        """

        digest = request.request_digest()
        base: dict[str, Any] = {
            "schema": "live_evidence.debug_outcome.v1",
            "request_digest": digest,
            "question_id": request.question_id,
            "question_revision": request.question_revision,
            "session_policy_digest": request.session_policy_digest,
            "subprocess_calls": 0,
            "mocked": False,
        }

        # 1. Frozen policy is the authority (#1449): zero subprocess on deny.
        if not debugger_invocation_allowed:
            return {**base, "result": "blocked_by_policy"}

        # 2. Exactly-once per request digest: a duplicate returns the recorded
        # outcome instead of re-running effects.
        if digest in self._seen_digests:
            return {**self._seen_digests[digest], "duplicate": True}

        if request.debugger_mode == "vscode_bridge":
            # Capability-gated GUI lane: absence is a truthful BLOCKED state,
            # never a faked visible stop. (Bridge composition is a later slice.)
            outcome = {**base, "result": "blocked_missing_capability",
                       "detail": "vscode_bridge not provisioned in this environment"}
            self._seen_digests[digest] = outcome
            return outcome

        if self._debugger_root is None:
            outcome = {**base, "result": "blocked_missing_capability",
                       "detail": "sibling debugger skill not found"}
            self._seen_digests[digest] = outcome
            return outcome

        # 3. Repository identity binding, checked BEFORE any capture runs.
        root = Path(request.repository_root)
        current = repository_digest(root) if root.exists() else "missing-root"
        if current != request.repository_commit_or_tree_digest:
            outcome = {**base, "result": "rejected_repository_mismatch",
                       "expected": request.repository_commit_or_tree_digest,
                       "observed": current}
            self._seen_digests[digest] = outcome
            return outcome

        # 4. Real capture through the debugger skill, read-only.
        self._work_dir.mkdir(parents=True, exist_ok=True)
        proof_path = self._work_dir / f"proof-{digest[:16]}.json"
        canonical_path = self._work_dir / f"canonical-{digest[:16]}.json"
        capture_cmd = [
            sys.executable,
            str(self._debugger_root / "scripts" / "capture_breakpoints.py"),
            "--out", str(proof_path),
        ]
        for breakpoint_spec in request.requested_breakpoints:
            if breakpoint_spec.line is None:
                outcome = {**base, "result": "capture_failed",
                           "detail": "python_bdb lane requires file:line breakpoints"}
                self._seen_digests[digest] = outcome
                return outcome
            capture_cmd += ["--break", f"{breakpoint_spec.file}:{breakpoint_spec.line}"]
        for name in request.requested_locals:
            capture_cmd += ["--local", name]
        capture_cmd += ["--", *request.reproduction_command]
        capture = subprocess.run(
            capture_cmd, capture_output=True, text=True, timeout=180, cwd=str(root)
        )
        base["subprocess_calls"] = 1
        if not proof_path.exists():
            outcome = {**base, "result": "capture_failed",
                       "detail": (capture.stderr or capture.stdout)[-500:]}
            self._seen_digests[digest] = outcome
            return outcome
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
        if int(proof.get("hit_count") or 0) < 1 or not proof.get("hits"):
            outcome = {**base, "result": "no_breakpoint_hit",
                       "proof_path": str(proof_path)}
            self._seen_digests[digest] = outcome
            return outcome

        # 5. Independent validation -- the debugger skill's validator, then our
        # own readback of the canonical artifact. Neither alone suffices.
        validation = subprocess.run(
            [sys.executable,
             str(self._debugger_root / "scripts" / "validate_debugger_proof.py"),
             str(proof_path), "--canonical-out", str(canonical_path), "--expect-valid"],
            capture_output=True, text=True, timeout=60,
        )
        base["subprocess_calls"] = 2
        if validation.returncode != 0 or not canonical_path.exists():
            outcome = {**base, "result": "proof_invalid",
                       "detail": (validation.stderr or validation.stdout)[-500:],
                       "proof_path": str(proof_path)}
            self._seen_digests[digest] = outcome
            return outcome
        canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
        matched = verified_stop_matches(canonical, request)
        if not matched:
            outcome = {**base, "result": "stop_mismatch",
                       "detail": "no independently verified stop at a requested location",
                       "proof_path": str(proof_path),
                       "canonical_path": str(canonical_path)}
            self._seen_digests[digest] = outcome
            return outcome

        # Canonical captures collapse to one frame; the raw proof keeps locals
        # per hit (already secret-redacted by the debugger skill). Merge the
        # matched stops' locals so a module-frame capture is not lost.
        matched_locations = {
            (str(Path(str(bp.get("file"))).resolve()), int(bp.get("line") or 0))
            for bp in matched
        }
        captured_locals: dict[str, Any] = dict(
            (canonical.get("captures") or {}).get("locals") or {}
        )
        for hit in proof.get("hits") or []:
            location = (str(Path(str(hit.get("file"))).resolve()), int(hit.get("line") or 0))
            if location in matched_locations:
                captured_locals.update(hit.get("locals") or {})
        outcome = {
            **base,
            "result": "supported",
            "proof_path": str(proof_path),
            "canonical_path": str(canonical_path),
            "stopped_file": matched[0].get("file"),
            "stopped_line": matched[0].get("line"),
            "captured_variable_names": sorted(captured_locals),
            "captured_locals": captured_locals,
            "limitations": (canonical.get("assessment") or {}).get("limitations") or [],
            "repository_digest": current,
        }
        self._seen_digests[digest] = outcome
        return outcome
