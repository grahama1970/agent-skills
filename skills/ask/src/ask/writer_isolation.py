"""Writer isolation and patch handoff as a plan-level contract (#1404).

Purpose
    Deciding isolation at execution time is too late: by then two writers are
    already in the same tree. This compiles a plan's writing workstreams into
    explicit isolation requirements and fails closed BEFORE Tau schedules
    anything.

    The rules that carry it:

    - **A reader never gets a worktree.** A scout, researcher, browser reviewer
      or judge does not become write-capable because a sibling node writes.
      Ambient capability is how a reviewer quietly acquires the power to edit
      the thing it is judging.
    - **One writer is the safe default.** Two writers in a shared tree is not a
      configuration, it is a race; it must fail closed unless each is given a
      managed worktree with its own lease and immutable base.
    - **Overlapping path claims are visible before execution**, and block
      unless a declared integrator owns the conflict. Discovering the overlap
      from a merge conflict means both writers already did the work.
    - **Prose is not completion.** A writer receipt without a patch digest and
      changed-file validation is rejected, because "I made the change" is
      exactly what an unverified writer would also say.

    Ask proposes; Tau creates, leases, validates, captures and cleans. Nothing
    here touches git.

Inputs
    A plan dict with ``workstreams``.

Outputs
    ``compile_isolation(plan)`` returns the isolation contract, or raises
    ``IsolationError``.

Failure modes
    Every unsafe shape raises at compile time with the reason named, which is
    the only point where refusing costs nothing.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
from typing import Any

SCHEMA = "ask.writer_isolation.v1"

MUTATION_INTENTS = ("none", "workspace_write")
ISOLATION_POLICIES = ("shared_single_writer", "managed_worktree")
INTEGRATION_POLICIES = ("review_only", "human_apply", "downstream_integrator")
CONFLICT_POLICIES = ("block", "explicit_integrator")

# Roles that must never receive write capability, whatever the ambient host
# offers. A reviewer that can edit what it reviews is not a reviewer.
READ_ONLY_ROLES = ("scout", "researcher", "reviewer", "judge", "browser_reviewer")


class IsolationError(ValueError):
    """A plan whose writer isolation is unsafe. Raised before scheduling."""


def _normalize_paths(paths: Any) -> tuple[str, ...]:
    if not paths:
        return ()
    return tuple(sorted({str(PurePosixPath(str(p))).rstrip("/") for p in paths}))


def _paths_overlap(a: str, b: str) -> bool:
    """True when two claims cover any common file.

    Prefix comparison is done per path segment: ``src/app`` must not be read as
    covering ``src/application``, which shares a string prefix but no files.
    """
    pa, pb = PurePosixPath(a).parts, PurePosixPath(b).parts
    shortest = min(len(pa), len(pb))
    return pa[:shortest] == pb[:shortest]


def overlapping_claims(workstreams: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    """Every (workstream_a, workstream_b, path) collision, before execution."""
    collisions: list[tuple[str, str, str]] = []
    writers = [w for w in workstreams if w.get("mutation_intent") == "workspace_write"]
    for index, first in enumerate(writers):
        for second in writers[index + 1 :]:
            for path_a in _normalize_paths(first.get("allowed_paths")):
                for path_b in _normalize_paths(second.get("allowed_paths")):
                    if _paths_overlap(path_a, path_b):
                        collisions.append(
                            (str(first.get("id")), str(second.get("id")), f"{path_a} ~ {path_b}")
                        )
    return collisions


def compile_isolation(plan: dict[str, Any]) -> dict[str, Any]:
    """Compile a plan's writing workstreams into an isolation contract."""
    workstreams = plan.get("workstreams")
    if not isinstance(workstreams, list) or not workstreams:
        raise IsolationError("plan has no workstreams")

    compiled: list[dict[str, Any]] = []
    for stream in workstreams:
        if not isinstance(stream, dict):
            raise IsolationError("each workstream must be an object")
        stream_id = str(stream.get("id") or "").strip()
        if not stream_id:
            raise IsolationError("every workstream needs an id")

        role = str(stream.get("role") or "").strip()
        intent = str(stream.get("mutation_intent") or "none")
        if intent not in MUTATION_INTENTS:
            raise IsolationError(f"{stream_id}: unknown mutation_intent {intent!r}")

        if role in READ_ONLY_ROLES and intent != "none":
            raise IsolationError(
                f"{stream_id}: role {role!r} is read-only and must not declare {intent!r}; "
                "a reviewer that can edit what it reviews is not a reviewer"
            )

        policy = str(stream.get("isolation_policy") or "shared_single_writer")
        if policy not in ISOLATION_POLICIES:
            raise IsolationError(f"{stream_id}: unknown isolation_policy {policy!r}")

        allowed = _normalize_paths(stream.get("allowed_paths"))
        denied = _normalize_paths(stream.get("denied_paths"))
        if intent == "workspace_write" and not allowed:
            raise IsolationError(f"{stream_id}: a writer must declare allowed_paths")
        if intent == "none" and allowed:
            raise IsolationError(
                f"{stream_id}: a non-writing workstream must not claim writable paths"
            )

        base_commit = str(stream.get("base_commit") or "")
        if policy == "managed_worktree" and not base_commit:
            raise IsolationError(
                f"{stream_id}: managed_worktree requires an immutable base_commit binding"
            )

        compiled.append(
            {
                "id": stream_id,
                "role": role,
                "mutation_intent": intent,
                "isolation_policy": policy if intent == "workspace_write" else "shared_single_writer",
                "allowed_paths": list(allowed),
                "denied_paths": list(denied),
                "base_commit": base_commit,
                "setup_hook": str(stream.get("setup_hook") or ""),
                # A writer must return artifacts, not prose.
                "required_artifacts": ["patch", "changed_files", "test_evidence"]
                if intent == "workspace_write"
                else [],
                "worktree_required": intent == "workspace_write" and policy == "managed_worktree",
            }
        )

    writers = [w for w in compiled if w["mutation_intent"] == "workspace_write"]
    integrators = [
        str(s.get("id"))
        for s in workstreams
        if str(s.get("integration_policy") or "") == "downstream_integrator"
    ]
    conflict_policy = str(plan.get("conflict_policy") or "block")
    if conflict_policy not in CONFLICT_POLICIES:
        raise IsolationError(f"unknown conflict_policy {conflict_policy!r}")

    # Two writers sharing a tree is a race, not a configuration.
    if len(writers) > 1:
        unmanaged = [w["id"] for w in writers if not w["worktree_required"]]
        if unmanaged:
            raise IsolationError(
                f"{len(writers)} writing workstreams but {unmanaged} lack managed_worktree isolation; "
                "parallel writers in one tree cannot be scheduled"
            )
        bases = {w["base_commit"] for w in writers}
        if len(bases) > 1:
            raise IsolationError(
                f"parallel writers must share one immutable base commit; got {sorted(bases)}"
            )

    collisions = overlapping_claims(workstreams)
    if collisions and not (conflict_policy == "explicit_integrator" and integrators):
        rendered = "; ".join(f"{a} vs {b} on {p}" for a, b, p in collisions)
        raise IsolationError(
            f"overlapping path claims block execution: {rendered}. "
            "Declare a downstream_integrator workstream and conflict_policy explicit_integrator to allow it"
        )

    contract = {
        "schema": SCHEMA,
        "workstreams": compiled,
        "writer_count": len(writers),
        "worktrees_required": [w["id"] for w in writers if w["worktree_required"]],
        "conflict_policy": conflict_policy,
        "integrators": integrators,
        "overlaps": [{"a": a, "b": b, "paths": p} for a, b, p in collisions],
    }
    contract["digest"] = "sha256:" + hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return contract


def verify_writer_receipt(receipt: dict[str, Any], contract_entry: dict[str, Any]) -> dict[str, Any]:
    """Accept a writer's output only on artifacts, never on prose.

    "I made the change" is exactly what an unverified writer would also say,
    so a receipt without a patch digest, a changed-file list and test evidence
    is rejected, and any changed file outside the declared scope rejects the
    whole receipt.
    """
    problems: list[str] = []

    patch_digest = str(receipt.get("patch_digest") or "")
    if not patch_digest:
        problems.append("no patch_digest; prose-only completion is not evidence")

    changed = receipt.get("changed_files")
    if not isinstance(changed, list) or not changed:
        problems.append("no changed_files list")
        changed = []

    if not receipt.get("test_evidence"):
        problems.append("no test/build evidence")

    allowed = _normalize_paths(contract_entry.get("allowed_paths"))
    denied = _normalize_paths(contract_entry.get("denied_paths"))
    for path in changed:
        normalized = str(PurePosixPath(str(path)))
        if denied and any(_paths_overlap(normalized, d) for d in denied):
            problems.append(f"{normalized} is in a denied path")
        if allowed and not any(_paths_overlap(normalized, a) for a in allowed):
            problems.append(f"{normalized} is outside the declared scope")

    return {
        "schema": "ask.writer_receipt_verdict.v1",
        "workstream": contract_entry.get("id"),
        "accepted": not problems,
        "problems": problems,
        "patch_digest": patch_digest,
        "changed_file_count": len(changed),
    }


def reviewer_inputs(contract: dict[str, Any], receipts: list[dict[str, Any]]) -> dict[str, Any]:
    """What an independent reviewer may see: accepted manifests only.

    A reviewer that can read a rejected writer's raw tree is reviewing work
    nobody admitted. It receives digests it can verify, not filesystem access.
    """
    entries = {w["id"]: w for w in contract["workstreams"]}
    accepted: list[dict[str, Any]] = []
    withheld: list[dict[str, Any]] = []
    for receipt in receipts:
        entry = entries.get(str(receipt.get("workstream") or ""))
        if entry is None:
            withheld.append({"workstream": receipt.get("workstream"), "reason": "unknown workstream"})
            continue
        verdict = verify_writer_receipt(receipt, entry)
        if verdict["accepted"]:
            accepted.append(
                {
                    "workstream": verdict["workstream"],
                    "patch_digest": verdict["patch_digest"],
                    "changed_file_count": verdict["changed_file_count"],
                }
            )
        else:
            withheld.append({"workstream": verdict["workstream"], "reason": verdict["problems"]})
    return {
        "schema": "ask.reviewer_inputs.v1",
        "accepted_manifests": accepted,
        "withheld": withheld,
        "grants_filesystem_access": False,
    }
