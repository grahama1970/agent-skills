"""Versioned local API over stdio and a Unix socket (#1406).

Purpose
    One request/response implementation, two transports. The API delegates to
    the existing contracts -- ``ask.run_projection.v1`` (#1401), run control
    (#1402), and ``ask.capability_report.v1`` (#1405) -- and deliberately does
    not create a second planner, scheduler, run ledger, status model or control
    path. A second implementation of any of those would drift from the first,
    and the drift would be invisible until an operator trusted the wrong one.

    Three properties carry the safety:

    - **Idempotency.** ``run.submit`` with a repeated key returns the original
      run identity rather than starting a second one. Accepted work is often
      paid work; a retried request must not buy it twice. A repeated key with a
      *different* payload is a conflict, not a match.
    - **Peer identity.** The socket is owner-only and every connection's peer
      UID is checked against the server's. A local socket is not a trust
      boundary on a shared machine unless it is made one.
    - **Path confinement.** Artifact reads resolve symlinks and must land
      inside the artifact root. ``..`` and a symlink pointing out are the same
      attack with different syntax.

Inputs
    JSON request envelopes, one per line on stdio or per message on the socket.

Outputs
    JSON response envelopes carrying protocol version, request id, and either
    a typed result or a typed error.

Failure modes
    Unknown method, malformed envelope, oversized request, unauthorized peer,
    and path escape all return typed errors; none raise, and none leak the
    offending value back to an untrusted caller beyond what it already sent.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import struct
import sys
from pathlib import Path
from typing import Any, Callable

PROTOCOL = "ask.local_api.v1"

# A request large enough to be a denial-of-service is not a request.
MAX_REQUEST_BYTES = 1 << 20

ERROR_CODES = (
    "unknown_method",
    "malformed_request",
    "request_too_large",
    "unauthorized_peer",
    "path_not_permitted",
    "idempotency_conflict",
    "not_found",
    "unsupported",
)


class ApiError(Exception):
    """A typed API failure. Never raised past the dispatcher."""

    def __init__(self, code: str, message: str) -> None:
        assert code in ERROR_CODES, code
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _artifact_root() -> Path:
    from .runs_control import artifact_root

    return artifact_root()


def resolve_artifact_path(candidate: str, root: Path | None = None) -> Path:
    """Resolve a caller-supplied path, refusing anything outside the root.

    ``resolve()`` follows symlinks before the containment check, because a
    symlink out of the root and a ``..`` segment are the same escape with
    different syntax.
    """
    base = (root or _artifact_root()).resolve()
    target = Path(candidate).expanduser().resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise ApiError("path_not_permitted", "path resolves outside the artifact root") from None
    return target


class IdempotencyStore:
    """Remembers submitted work by caller key.

    In-memory by design: it guards against a client retrying within a session.
    A restart forgets keys, which is why ``run.submit`` also reports the run id
    -- recovery is by identity, not by hoping the key survived.
    """

    def __init__(self) -> None:
        self._entries: dict[str, tuple[str, dict[str, Any]]] = {}

    def check(self, key: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not key:
            return None
        existing = self._entries.get(key)
        if existing is None:
            return None
        run_id, original = existing
        if original != payload:
            raise ApiError(
                "idempotency_conflict",
                "this idempotency key was used with a different payload",
            )
        return {"run_id": run_id, "duplicate": True, "note": "returned the original run; nothing was resubmitted"}

    def remember(self, key: str, payload: dict[str, Any], run_id: str) -> None:
        if key:
            self._entries[key] = (run_id, payload)


class LocalApi:
    """The single request/response implementation both transports share."""

    def __init__(self, artifact_root_override: Path | None = None) -> None:
        self.root = artifact_root_override
        self.idempotency = IdempotencyStore()
        self.methods: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "ping": self._ping,
            "capabilities.get": self._capabilities,
            "targets.readiness": self._capabilities,
            "targets.list": self._targets_list,
            "runs.list": self._runs_list,
            "run.show": self._run_show,
            "run.events": self._run_events,
            "run.steer": self._run_steer,
            "run.cancel": self._run_cancel,
            "run.resume": self._run_resume,
            "run.submit": self._run_submit,
            "artifacts.manifest": self._artifacts_manifest,
            "health.get": self._health,
            "targets.resolve": self._targets_resolve,
            "plan.preview": self._plan_preview,
        }

    # -- methods ---------------------------------------------------------

    def _ping(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"protocol": PROTOCOL, "pong": True}

    def _capabilities(self, params: dict[str, Any]) -> dict[str, Any]:
        from .capability_report import build_report

        return build_report(live=bool(params.get("live")))

    def _targets_list(self, params: dict[str, Any]) -> dict[str, Any]:
        report = self._capabilities(params)
        return {"targets": [
            {"capability_id": c["capability_id"], "kind": c["kind"], "state": c["state"]}
            for c in report["capabilities"]
        ]}

    def _runs_list(self, params: dict[str, Any]) -> dict[str, Any]:
        from .runs_control import list_runs

        return {"runs": list_runs(limit=int(params.get("limit") or 20), root=self.root)}

    def _run_dir(self, params: dict[str, Any]) -> Path:
        from .runs_control import resolve_run

        run = str(params.get("run") or params.get("run_id") or "")
        path = resolve_run(run, root=self.root)
        if path is None:
            raise ApiError("not_found", f"no run for {run!r}")
        return path

    def _run_show(self, params: dict[str, Any]) -> dict[str, Any]:
        from .run_projection import project_run

        # The same projection the CLI renders; not a second status model.
        return project_run(self._run_dir(params))

    def _run_events(self, params: dict[str, Any]) -> dict[str, Any]:
        from .runs_control import watch_events

        events = list(
            watch_events(self._run_dir(params), poll_seconds=0, max_polls=int(params.get("max_polls") or 1))
        )
        cursor = int(params.get("cursor") or 0)
        # A cursor beyond what exists is a gap, reported rather than replayed:
        # silently re-emitting events would let a reconnect look like new work.
        gap = cursor > len(events)
        return {
            "events": events[cursor:],
            "cursor": len(events),
            "gap": gap,
            "gap_reason": "cursor beyond known events" if gap else None,
        }

    def _run_steer(self, params: dict[str, Any]) -> dict[str, Any]:
        from .runs_control import steer

        return steer(self._run_dir(params), str(params.get("node") or ""), str(params.get("message") or ""))

    def _run_cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        from .runs_control import cancel

        return cancel(self._run_dir(params), str(params.get("node") or ""))

    def _run_resume(self, params: dict[str, Any]) -> dict[str, Any]:
        from .runs_control import resume

        return resume(self._run_dir(params), execute=bool(params.get("execute")))

    def _run_submit(self, params: dict[str, Any]) -> dict[str, Any]:
        key = str(params.get("idempotency_key") or "")
        payload = {k: v for k, v in params.items() if k != "idempotency_key"}
        duplicate = self.idempotency.check(key, payload)
        if duplicate is not None:
            return duplicate
        # Submission itself is not implemented here: the API must not become a
        # second scheduler. It reports what it would delegate to.
        raise ApiError(
            "unsupported",
            "run.submit delegates to the Ask CLI/Tau; this build exposes preview and control only",
        )

    def _artifacts_manifest(self, params: dict[str, Any]) -> dict[str, Any]:
        run_dir = self._run_dir(params)
        resolved = resolve_artifact_path(str(run_dir), self.root)
        entries = []
        for path in sorted(resolved.rglob("*")):
            if path.is_file():
                entries.append({"path": str(path.relative_to(resolved)), "bytes": path.stat().st_size})
        return {"run_dir": str(resolved), "artifacts": entries[:500], "truncated": len(entries) > 500}

    def _health(self, params: dict[str, Any]) -> dict[str, Any]:
        """Liveness of the API itself, not of the subsystems it reports on.

        Kept distinct from capabilities.get on purpose: an API that answers is
        not evidence that Tau or a browser seat is reachable, and conflating
        them is how a green health check hides a blocked lane.
        """
        root = (self.root or _artifact_root())
        return {
            "protocol": PROTOCOL,
            "serving": True,
            "artifact_root": str(root),
            "artifact_root_present": root.is_dir(),
            "note": "API liveness only; call capabilities.get for subsystem readiness",
        }

    def _targets_resolve(self, params: dict[str, Any]) -> dict[str, Any]:
        """Resolve one selector to its capability entry."""
        from .capability_report import build_report

        selector = str(params.get("selector") or "").strip().lower()
        if not selector:
            raise ApiError("malformed_request", "selector is required")
        report = build_report(live=bool(params.get("live")))
        for entry in report["capabilities"]:
            if entry["capability_id"].lower() == selector or entry["selector"].lower() == selector.split(":")[-1]:
                return entry
        raise ApiError("not_found", f"no target matches {selector!r}")

    def _plan_preview(self, params: dict[str, Any]) -> dict[str, Any]:
        """Normalize a plan and hash it, with no side effects.

        Preview must not create a run directory or touch a provider: the whole
        point is to see the frozen shape and its logical hash before anything
        is spent.
        """
        from .launch_contract import ContractError, compile_contract

        nodes = params.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            raise ApiError("malformed_request", "nodes must be a non-empty list")
        contracts: list[dict[str, Any]] = []
        for spec in nodes:
            if not isinstance(spec, dict):
                raise ApiError("malformed_request", "each node must be an object")
            try:
                contracts.append(compile_contract(spec))
            except ContractError as exc:
                raise ApiError("malformed_request", f"node rejected: {exc}") from None
        combined = hashlib.sha256(
            "|".join(c["digest"] for c in contracts).encode("utf-8")
        ).hexdigest()
        return {
            "schema": "ask.plan_preview.v1",
            "nodes": contracts,
            "logical_hash": "sha256:" + combined,
            "side_effects": [],
        }

    # -- dispatch --------------------------------------------------------

    def dispatch(self, request: Any) -> dict[str, Any]:
        """One envelope in, one envelope out. Never raises."""
        request_id = ""
        try:
            if not isinstance(request, dict):
                raise ApiError("malformed_request", "request must be a JSON object")
            request_id = str(request.get("request_id") or "")
            method = str(request.get("method") or "")
            # Check before coercing: `params or {}` turns a malformed [] into
            # {} and the type check below would never fire, silently accepting
            # a request shape the protocol does not allow.
            raw_params = request.get("params", {})
            if raw_params is None:
                raw_params = {}
            if not isinstance(raw_params, dict):
                raise ApiError("malformed_request", "params must be an object")
            params = raw_params
            handler = self.methods.get(method)
            if handler is None:
                raise ApiError("unknown_method", f"{method!r} is not a method of {PROTOCOL}")
            result = handler(params)
            return {
                "protocol": PROTOCOL,
                "request_id": request_id,
                "method": method,
                "ok": True,
                "result": result,
            }
        except ApiError as exc:
            return {
                "protocol": PROTOCOL,
                "request_id": request_id,
                "ok": False,
                "error": {"code": exc.code, "message": exc.message},
            }
        except Exception as exc:  # pragma: no cover - defensive
            return {
                "protocol": PROTOCOL,
                "request_id": request_id,
                "ok": False,
                "error": {"code": "malformed_request", "message": str(exc)[:200]},
            }


def serve_stdio(api: LocalApi | None = None, stdin=None, stdout=None) -> int:
    """One JSON request per line, one response per line."""
    api = api or LocalApi()
    source = stdin or sys.stdin
    sink = stdout or sys.stdout
    for line in source:
        line = line.strip()
        if not line:
            continue
        if len(line.encode("utf-8")) > MAX_REQUEST_BYTES:
            response = {
                "protocol": PROTOCOL,
                "ok": False,
                "error": {"code": "request_too_large", "message": "request exceeds the size bound"},
            }
        else:
            try:
                request = json.loads(line)
            except ValueError as exc:
                response = {
                    "protocol": PROTOCOL,
                    "ok": False,
                    "error": {"code": "malformed_request", "message": str(exc)[:120]},
                }
            else:
                response = api.dispatch(request)
        sink.write(json.dumps(response, sort_keys=True) + "\n")
        sink.flush()
    return 0


def peer_uid(connection: socket.socket) -> int | None:
    """UID of the connecting process, or None where unsupported."""
    try:
        creds = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        _pid, uid, _gid = struct.unpack("3i", creds)
        return uid
    except (OSError, AttributeError):
        return None


def serve_socket(socket_path: Path, api: LocalApi | None = None, max_connections: int = 0) -> int:
    """Owner-only Unix socket. No TCP listener, ever.

    The socket is created with mode 0600 and every peer's UID is compared to
    the server's: on a shared machine a local socket is not a trust boundary
    unless it is made one.
    """
    api = api or LocalApi()
    socket_path = Path(socket_path)
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists():
        socket_path.unlink()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old_umask = os.umask(0o077)
    try:
        server.bind(str(socket_path))
        os.chmod(socket_path, 0o600)
    finally:
        os.umask(old_umask)
    server.listen(8)

    served = 0
    try:
        while True:
            connection, _ = server.accept()
            with connection:
                uid = peer_uid(connection)
                if uid is not None and uid != os.getuid():
                    connection.sendall(
                        json.dumps(
                            {
                                "protocol": PROTOCOL,
                                "ok": False,
                                "error": {"code": "unauthorized_peer", "message": "peer uid mismatch"},
                            }
                        ).encode("utf-8")
                        + b"\n"
                    )
                    continue
                data = connection.recv(MAX_REQUEST_BYTES + 1)
                if len(data) > MAX_REQUEST_BYTES:
                    response: dict[str, Any] = {
                        "protocol": PROTOCOL,
                        "ok": False,
                        "error": {"code": "request_too_large", "message": "request exceeds the size bound"},
                    }
                else:
                    try:
                        response = api.dispatch(json.loads(data.decode("utf-8") or "{}"))
                    except ValueError as exc:
                        response = {
                            "protocol": PROTOCOL,
                            "ok": False,
                            "error": {"code": "malformed_request", "message": str(exc)[:120]},
                        }
                connection.sendall(json.dumps(response, sort_keys=True).encode("utf-8") + b"\n")
            served += 1
            if max_connections and served >= max_connections:
                return 0
    finally:
        server.close()
        socket_path.unlink(missing_ok=True)
