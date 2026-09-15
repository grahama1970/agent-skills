#!/usr/bin/env python3
"""Exercise Battle's real Tau handoff against a deterministic HTTP seat."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


BATTLE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BATTLE_DIR.parents[1]
TAU_REPO = Path(
    os.environ.get("TAU_REPO", "/home/graham/workspace/experiments/tau")
).expanduser().resolve()

for candidate in (BATTLE_DIR / "src", REPO_ROOT / "skills"):
    raw = str(candidate)
    if raw not in sys.path:
        sys.path.insert(0, raw)

from battle_skill.arena_live_battle_proof import (  # noqa: E402
    _annotate_tau_authoring_route,
    _run_tau_harness,
)
from battle_skill.team_artifact_pipeline import tau_authoring_route_errors  # noqa: E402


BATTLE_ID = "battle-004"
RUN_ID = "battle-b25-scripted-tau-route"
SCENARIO_ID = "scenario-b25-scripted-route"
MODEL = "gpt-5.5"
API_KEY = "battle-b25-scripted-seat"


def _utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"expected JSON object: {path}")
    return value


def _red_artifact() -> dict[str, Any]:
    return {
        "artifact_type": "red_exploit",
        "exploit_py": """import argparse
import tempfile
import zipfile
from pathlib import Path

from app import import_zip

parser = argparse.ArgumentParser()
parser.add_argument("--expect-vulnerable", action="store_true")
args = parser.parse_args()
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    archive = root / "payload.zip"
    destination = root / "destination"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../arena_escape.txt", "battle-b25")
    import_zip(archive, destination)
    escaped = root / "arena_escape.txt"
    if args.expect_vulnerable and escaped.exists():
        print("RED_EXPLOIT_CONFIRMED")
    else:
        raise SystemExit(1)
""",
        "rationale": "Exercise the public import_zip contract with a traversal member.",
        "strategy_genome": {
            "selected_methods": ["zip_path_traversal"],
            "rejected_methods": ["network_probe"],
            "parameters": {"member": "../arena_escape.txt"},
            "mutation_origin": "battle-b25-scripted-seat",
            "expected_observation": "The vulnerable importer writes outside destination.",
        },
    }


def _blue_artifact() -> dict[str, Any]:
    return {
        "artifact_type": "blue_patch",
        "app_py": """import shutil
from pathlib import Path
from zipfile import ZipFile

def import_zip(zip_path, destination):
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=True)
    written = []
    with ZipFile(zip_path) as archive:
        for member in archive.infolist():
            relative = Path(member.filename)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("unsafe zip member")
            target = (root / relative).resolve()
            if target != root and root not in target.parents:
                raise ValueError("unsafe zip destination")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            written.append(str(target))
    return written
""",
        "rationale": "Reject absolute and parent-traversal archive members.",
        "strategy_genome": {
            "selected_methods": ["resolved_path_containment"],
            "rejected_methods": ["filename_prefix_check"],
            "parameters": {"reject_parent_parts": True},
            "mutation_origin": "battle-b25-scripted-seat",
            "expected_observation": "Traversal members are rejected before extraction.",
        },
    }


def _handoff_from_request(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages missing")
    user = messages[-1]
    if not isinstance(user, dict) or not isinstance(user.get("content"), str):
        raise ValueError("user message missing")
    content = user["content"]
    marker = "PUBLIC_BATTLE_HANDOFF_JSON:\n"
    suffix = "\nReturn the required JSON object now."
    if marker not in content or suffix not in content:
        raise ValueError("Tau public handoff markers missing")
    team_line = content.splitlines()[0]
    team = team_line.removeprefix("TEAM: ").strip()
    handoff_text = content.split(marker, 1)[1].rsplit(suffix, 1)[0]
    handoff = json.loads(handoff_text)
    if team not in {"red", "blue"} or not isinstance(handoff, dict):
        raise ValueError("invalid team handoff")
    return team, handoff


class _ScriptedSeat:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def handler(self) -> type[BaseHTTPRequestHandler]:
        seat = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *_args: object) -> None:
                return

            def _send(self, status: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                if self.path != "/v1/scillm/auth":
                    self._send(404, {"error": "not_found"})
                    return
                seat.requests.append(
                    {
                        "method": "GET",
                        "path": self.path,
                        "caller_skill": self.headers.get("X-Caller-Skill"),
                        "bearer_present": self.headers.get("Authorization") == f"Bearer {API_KEY}",
                    }
                )
                self._send(200, {"codex": {"status": "authenticated"}})

            def do_POST(self) -> None:  # noqa: N802
                try:
                    if self.path != "/v1/chat/completions":
                        raise ValueError(f"unexpected path: {self.path}")
                    size = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(size).decode("utf-8"))
                    team, handoff = _handoff_from_request(payload)
                    seat.requests.append(
                        {
                            "method": "POST",
                            "path": self.path,
                            "team": team,
                            "model": payload.get("model"),
                            "caller_skill": self.headers.get("X-Caller-Skill"),
                            "bearer_present": self.headers.get("Authorization")
                            == f"Bearer {API_KEY}",
                            "handoff": handoff,
                        }
                    )
                    artifact = _red_artifact() if team == "red" else _blue_artifact()
                    self._send(
                        200,
                        {"choices": [{"message": {"content": json.dumps(artifact)}}]},
                    )
                except (ValueError, json.JSONDecodeError) as exc:
                    seat.errors.append(str(exc))
                    self._send(422, {"error": str(exc)})

        return Handler


def _assert_tau_receipts(manifest_path: Path, seat: _ScriptedSeat) -> list[dict[str, Any]]:
    manifest = _read_json(manifest_path)
    if manifest.get("status") != "PASS":
        raise AssertionError(f"Tau manifest did not pass: {manifest_path}")
    _annotate_tau_authoring_route(
        battle_id=BATTLE_ID,
        run_id=RUN_ID,
        tau_manifest=manifest,
    )
    manifest = _read_json(manifest_path)
    posts = [item for item in seat.requests if item.get("method") == "POST"]
    if len(posts) != 2 or {item.get("team") for item in posts} != {"red", "blue"}:
        raise AssertionError(f"scripted seat did not receive one Red and one Blue call: {posts}")

    checks: list[dict[str, Any]] = []
    for entry in manifest.get("teams", []):
        team = str(entry.get("team") or "")
        if team not in {"red", "blue"}:
            raise AssertionError(f"unexpected Tau team entry: {team!r}")
        post = next(item for item in posts if item.get("team") == team)
        handoff_path = Path(str(entry["handoff"]))
        scillm_path = Path(str(entry["scillm_call"]))
        subagent_path = Path(str(entry["subagent_receipt"]))
        materialized_path = Path(str(entry["materialized_artifact"]["path"])).parent / (
            "materialized-artifact-receipt.json"
        )
        handoff = _read_json(handoff_path)
        scillm = _read_json(scillm_path)
        subagent = _read_json(subagent_path)
        materialized = _read_json(materialized_path)
        if post["handoff"] != handoff:
            raise AssertionError(f"{team} HTTP handoff differs from Tau handoff receipt")
        if any(
            [
                handoff.get("schema") != "tau.battle_team_handoff.v1",
                handoff.get("battle_id") != BATTLE_ID,
                handoff.get("run_id") != RUN_ID,
                handoff.get("team") != team,
                handoff.get("visibility_model") != "team_public_only",
                post.get("model") != MODEL,
                post.get("caller_skill") != "battle",
                post.get("bearer_present") is not True,
                scillm.get("status") != "PASS",
                scillm.get("surface") != "scillm.chat_completions",
                subagent.get("result", {}).get("status") != "PASS",
                materialized.get("status") != "PASS",
            ]
        ):
            raise AssertionError(f"{team} Tau boundary receipt contract failed")
        route_errors = tau_authoring_route_errors(
            team=team,
            battle_id=BATTLE_ID,
            run_id=RUN_ID,
            provider_payload=subagent,
            materialization_payload=materialized,
        )
        if route_errors:
            raise AssertionError(f"{team} Tau route errors: {route_errors}")
        bypassed_subagent = copy.deepcopy(subagent)
        bypassed_materialized = copy.deepcopy(materialized)
        bypassed_subagent["route_identity"]["router"] = "battle-local-provider"
        bypassed_materialized["route_identity"]["router"] = "battle-local-provider"
        bypass_errors = tau_authoring_route_errors(
            team=team,
            battle_id=BATTLE_ID,
            run_id=RUN_ID,
            provider_payload=bypassed_subagent,
            materialization_payload=bypassed_materialized,
        )
        if not any("Battle-local provider path" in error for error in bypass_errors):
            raise AssertionError(f"{team} Battle-local route bypass was accepted")
        retained = materialized["retained_response_receipt"]
        if retained["path"] != str(scillm_path) or retained["sha256"] != _sha256(scillm_path):
            raise AssertionError(f"{team} retained SciLLM receipt binding failed")
        for state in ("TIMEOUT", "PROVIDER_QUOTA_EXCEEDED", "CANCELLED"):
            probe_path = scillm_path.parent / f"{scillm_path.name}.non-competitive-{state.lower()}.json"
            probe_payload = copy.deepcopy(scillm)
            probe_payload["status"] = state
            _write_json(probe_path, probe_payload)
            probe_sha = _sha256(probe_path)
            probe_materialized = copy.deepcopy(materialized)
            probe_materialized["retained_response_receipt"] = {
                "path": str(probe_path),
                "sha256": probe_sha,
            }
            probe_materialized["scillm_call_receipt_sha256"] = probe_sha
            probe_errors = tau_authoring_route_errors(
                team=team,
                battle_id=BATTLE_ID,
                run_id=RUN_ID,
                provider_payload=subagent,
                materialization_payload=probe_materialized,
            )
            if not any(
                "retained response receipt non-competitive status cannot be a win" in error
                for error in probe_errors
            ):
                raise AssertionError(
                    f"{team} non-competitive retained status {state} was accepted: {probe_errors}"
                )
        if materialized["route_identity"]["router"] != "tau.battle_live_handoff":
            raise AssertionError(f"{team} route bypassed Tau")
        checks.append(
            {
                "team": team,
                "status": "PASS",
                "handoff": str(handoff_path),
                "scillm_call": str(scillm_path),
                "subagent_receipt": str(subagent_path),
                "materialization_receipt": str(materialized_path),
                "route_id": materialized["route_identity"]["route_id"],
                "tau_task_id": materialized["tau_task"]["id"],
                "battle_local_bypass_rejected": True,
                "non_competitive_retained_status_rejected": True,
            }
        )
    if len(checks) != 2:
        raise AssertionError(f"expected two Tau team receipts, got {len(checks)}")
    return checks


def run(out_dir: Path) -> dict[str, Any]:
    out_dir = out_dir.expanduser().resolve()
    run_dir = out_dir / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    context_path = _write_json(
        out_dir / "tau-public-context.json",
        {
            "schema": "tau.battle_context_bundle.v1",
            "summary": {
                "mode": "bounded_worker_matrix",
                "battle_id": BATTLE_ID,
                "run_id": RUN_ID,
                "scenario_id": SCENARIO_ID,
                "visibility_rule": "teams receive public artifacts only",
                "teams": {
                    "red": {"objective": "Author one Red proposal."},
                    "blue": {"objective": "Author one Blue proposal."},
                },
            },
        },
    )
    seat = _ScriptedSeat()
    server = ThreadingHTTPServer(("127.0.0.1", 0), seat.handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    prior_key = os.environ.get("SCILLM_API_KEY")
    prior_disable = os.environ.get("TAU_SCILLM_DISABLE_PROXY_RECREATE")
    os.environ["SCILLM_API_KEY"] = API_KEY
    os.environ["TAU_SCILLM_DISABLE_PROXY_RECREATE"] = "1"
    try:
        manifest_path = _run_tau_harness(
            out_dir=run_dir,
            battle_id=BATTLE_ID,
            run_id=RUN_ID,
            scenario_id=SCENARIO_ID,
            context_path=context_path,
            red_persona="battle-b25-red-scripted-seat",
            blue_persona="battle-b25-blue-scripted-seat",
            model=MODEL,
            scillm_base_url=f"http://127.0.0.1:{server.server_port}",
            timeout_s=20,
            red_workers=1,
            blue_workers=1,
        )
        checks = _assert_tau_receipts(manifest_path, seat)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        if prior_key is None:
            os.environ.pop("SCILLM_API_KEY", None)
        else:
            os.environ["SCILLM_API_KEY"] = prior_key
        if prior_disable is None:
            os.environ.pop("TAU_SCILLM_DISABLE_PROXY_RECREATE", None)
        else:
            os.environ["TAU_SCILLM_DISABLE_PROXY_RECREATE"] = prior_disable
    if seat.errors:
        raise AssertionError(f"scripted seat errors: {seat.errors}")
    requests_path = _write_json(
        out_dir / "scripted-seat-requests.json",
        {
            "schema": "battle.tau_scripted_seat_requests.v1",
            "mocked": True,
            "live_http": True,
            "requests": seat.requests,
        },
    )
    return {
        "schema": "battle.tau_authoring_route_eval.v1",
        "status": "PASS",
        "mocked": True,
        "live": True,
        "live_path": "Battle _run_tau_harness -> Tau CLI -> HTTP chat-completions",
        "provider": "deterministic_loopback_scripted_seat",
        "battle_id": BATTLE_ID,
        "run_id": RUN_ID,
        "checks": checks,
        "artifacts": {
            "tau_manifest": str(manifest_path),
            "scripted_seat_requests": str(requests_path),
            "tau_stdout": str(run_dir / "tau-live-command.stdout.txt"),
            "tau_stderr": str(run_dir / "tau-live-command.stderr.txt"),
        },
        "created_at": _utc(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    receipt = run(args.out)
    receipt_path = _write_json(args.out.expanduser().resolve() / "receipt.json", receipt)
    print(f"BATTLE_B25_TAU_SCRIPTED_ROUTE_PASS receipt={receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
