#!/usr/bin/env python3
"""Exercise watchdog log delivery through the real bridge entrypoint.

This retained regression is deterministic fault-injection around the production
bridge script. It proves the producer/consumer mechanics and readbacks without
claiming live Discord, live Pi, or live GitHub proof.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "scripts" / "watchdog_notify_bridge.py"


class SwitchboardHandler(BaseHTTPRequestHandler):
    posts: list[dict[str, Any]] = []

    def do_POST(self) -> None:  # noqa: N802 - stdlib hook
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        payload = json.loads(body.decode("utf-8"))
        self.__class__.posts.append(payload)
        response = {
            "id": f"switch-{len(self.__class__.posts)}",
            "consumed": {
                "status": "ACK",
                "action": "queued_for_owner",
                "event_id": payload.get("event", {}).get("event_id"),
            },
        }
        data = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def start_switchboard() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), SwitchboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def write_fake_ops_discord(tmp: Path) -> tuple[Path, Path]:
    log = tmp / "ops-discord-posts.jsonl"
    script = tmp / "ops-discord-run.sh"
    script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, os, sys, time",
                f"log = {str(log)!r}",
                "Path = __import__('pathlib').Path",
                "Path(log).parent.mkdir(parents=True, exist_ok=True)",
                "Path(log).open('a').write(json.dumps({'argv': sys.argv[1:]}) + '\\n')",
                "print(json.dumps({'schema':'ops_discord.notification_receipt.v1','status':'SENT','message_id':'discord-1640','message_url':'https://discord.com/channels/test/test/discord-1640','sent_at':time.time()}))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script, log


def run_bridge(state: Path, switchboard_url: str, ops_run: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env.update(
        {
            "PROJECT_WATCHDOG_STATE_ROOT": str(state),
            "SWITCHBOARD_URL": switchboard_url,
            "PROJECT_WATCHDOG_OPS_DISCORD_RUN_SH": str(ops_run),
            "PROJECT_WATCHDOG_ALERT_CHANNEL": "horus",
            "WATCHDOG_BRIDGE_PI_INBOX": "agent-skills",
        }
    )
    proc = subprocess.run(
        [sys.executable, str(BRIDGE), "--once"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return json.loads(proc.stdout)


def receipt_payload(
    *,
    run_id: str,
    status: str,
    requires_human: bool,
    issue: int | None,
    repo: str | None,
    action: str = "ticket_repair",
) -> dict[str, Any]:
    handled: dict[str, Any] = {
        "action": action,
        "status": status,
        "attempt": 2,
        "summary": "provider HTTP429 surfaced with actionable recovery",
        "triage": {
            "code": "triage_classifier_unreachable",
            "cause": "provider adapter returned HTTP429",
            "next_command": "skills/project-watchdog/scripts/watchdog/recover_primary.py --root /repo --apply",
        },
        "authorized_agent_next_steps": [
            "skills/project-watchdog/scripts/watchdog/recover_primary.py --root /repo --apply"
        ],
    }
    if issue is not None:
        handled["issue_number"] = issue
    if repo is not None:
        handled["repo"] = repo
    return {
        "schema": "agent_skills.project_watchdog.tick_receipt.v1",
        "run_id": run_id,
        "status": status,
        "source_time": "2026-09-09T21:59:33Z",
        "stop_reason": "provider_rate_limited",
        "requires_human_input": requires_human,
        "handled_issues": [handled],
        "errors": [
            {
                "exit_code": 429,
                "field_path": ["provider", "response", "status_code"],
                "raw": "HTTP 429 from reviewer provider",
            }
        ],
        "retry_budget": {"remaining": 1, "not_before": "2026-09-09T22:04:33Z"},
        "not_before": "2026-09-09T22:04:33Z",
        "resolution_ref": "native-ticket://grahama1970/agent-skills/1640#retry",
    }


def write_receipt(state: Path, dirname: str, payload: dict[str, Any]) -> Path:
    directory = state / "receipts" / dirname
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "receipt.json").write_text(json.dumps(payload), encoding="utf-8")
    (directory / "tau-stream-monitor.json").write_text(
        json.dumps(
            {
                "process_running": True,
                "current_status": "RUNNING",
                "current_node": "creator",
                "elapsed_seconds": 77,
                "latest_event": {"event_id": "evt-1", "node_id": "creator", "status": "RUNNING"},
            }
        ),
        encoding="utf-8",
    )
    ask = directory / "ask" / "run-1" / "tau-receipts"
    ask.mkdir(parents=True, exist_ok=True)
    (ask / "source-dag.json").write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "creator",
                        "context": {
                            "handler_policy": {
                                "model_policy": {
                                    "requested_model": "gpt-5.5-high",
                                    "fallback_model": "fable-5-low",
                                }
                            }
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return directory


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def assert_true(checks: dict[str, bool], key: str, value: bool) -> None:
    checks[key] = bool(value)
    if not value:
        raise AssertionError(key)


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/watchdog-log-delivery-proof.json")
    checks: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(prefix="watchdog-log-delivery-") as raw:
        tmp = Path(raw)
        state = tmp / "state"
        (state / "receipts").mkdir(parents=True)
        ops_run, ops_log = write_fake_ops_discord(tmp)
        server, switchboard_url = start_switchboard()
        try:
            run1 = write_receipt(
                state,
                "run-machine",
                receipt_payload(
                    run_id="run153002Z-fb03aee164b3",
                    status="NEEDS_ATTENTION",
                    requires_human=False,
                    issue=1640,
                    repo="grahama1970/agent-skills",
                ),
            )
            first = run_bridge(state, switchboard_url, ops_run)
            events = jsonl(state / "events.jsonl")
            receipt_event = next(row for row in events if row["kind"] == "receipt")
            event_id = receipt_event["event_id"]
            checkpoint = json.loads((state / "notify-bridge-checkpoints.json").read_text())
            agent_receipt = json.loads(
                next((state / "agent-push-receipts").glob("*.json")).read_text()
            )

            assert_true(checks, "real_bridge_entrypoint_ran", first["status"] == "OK")
            assert_true(checks, "jsonl_bytes_rendered_terminal_event", receipt_event["issue"] == "1640")
            assert_true(checks, "identity_correlated_no_none_none", "None#None" not in json.dumps(receipt_event))
            assert_true(checks, "source_time_separate_from_observed_at", receipt_event["source_time"] != receipt_event["observed_at"])
            assert_true(checks, "triage_error_and_original_error_visible", receipt_event["triage"] and receipt_event["original_errors"][0]["exit_code"] == 429)
            assert_true(checks, "owning_next_action_visible", "recover_primary.py" in receipt_event["next"])
            assert_true(checks, "terminal_checkpoint_after_ack", event_id in checkpoint["destinations"]["terminal"]["delivered_event_ids"])
            assert_true(checks, "pi_checkpoint_after_ack", event_id in checkpoint["destinations"]["pi_agent"]["delivered_event_ids"])
            assert_true(checks, "agent_action_receipt_retained", agent_receipt["consumed_or_action_receipt"]["status"] == "ACK")
            assert_true(checks, "machine_action_did_not_page_discord", not ops_log.exists())

            second = run_bridge(state, switchboard_url, ops_run)
            receipt_rows_after_second = [
                row for row in jsonl(state / "events.jsonl") if row["kind"] == "receipt" and row["event_id"] == event_id
            ]
            assert_true(checks, "duplicate_delivery_deduped", len(receipt_rows_after_second) == 1 and not second["pushed"])

            pending_dir = state / "receipts" / "run-late"
            pending_dir.mkdir()
            run_bridge(state, switchboard_url, ops_run)
            pending_checkpoint = json.loads((state / "notify-bridge-checkpoints.json").read_text())
            assert_true(checks, "late_receipt_dir_retained_for_catchup", "run-late" in pending_checkpoint["pending_dirs"])
            write_receipt(
                state,
                "run-late",
                receipt_payload(
                    run_id="run155307Z-0204513fba51",
                    status="COMPLETED",
                    requires_human=False,
                    issue=None,
                    repo=None,
                ),
            )
            run_bridge(state, switchboard_url, ops_run)
            unknown_event = [
                row
                for row in jsonl(state / "events.jsonl")
                if row.get("run_id") == "run155307Z-0204513fba51"
            ][0]
            assert_true(checks, "unknown_identity_explicit_reason", unknown_event["repo"].startswith("UNKNOWN(repo:") and unknown_event["issue"].startswith("UNKNOWN(issue:"))

            down_dir = write_receipt(
                state,
                "run-down",
                receipt_payload(
                    run_id="run-down",
                    status="NEEDS_ATTENTION",
                    requires_human=False,
                    issue=1641,
                    repo="grahama1970/agent-skills",
                ),
            )
            failed = run_bridge(state, "http://127.0.0.1:9", ops_run)
            failed_event = failed["pushed"][0]["event_id"]
            failed_checkpoint = json.loads((state / "notify-bridge-checkpoints.json").read_text())
            assert_true(checks, "unavailable_destination_keeps_pending", failed_event in failed_checkpoint["pending"])
            run_bridge(state, switchboard_url, ops_run)
            recovered_checkpoint = json.loads((state / "notify-bridge-checkpoints.json").read_text())
            assert_true(checks, "restart_catchup_no_loss", failed_event in recovered_checkpoint["destinations"]["pi_agent"]["delivered_event_ids"])
            rows_for_failed = [row for row in jsonl(state / "events.jsonl") if row.get("event_id") == failed_event]
            assert_true(checks, "restart_catchup_no_replay_flood", len(rows_for_failed) == 1)

            (state / "events.jsonl").write_text("", encoding="utf-8")
            write_receipt(
                state,
                "run-after-rotation",
                receipt_payload(
                    run_id="run-after-rotation",
                    status="COMPLETED",
                    requires_human=False,
                    issue=1642,
                    repo="grahama1970/agent-skills",
                ),
            )
            run_bridge(state, switchboard_url, ops_run)
            assert_true(checks, "rotation_truncation_does_not_break_delivery", jsonl(state / "events.jsonl")[-1]["run_id"] == "run-after-rotation")

            human_dir = write_receipt(
                state,
                "run-human",
                receipt_payload(
                    run_id="run-human",
                    status="BLOCKED",
                    requires_human=True,
                    issue=1643,
                    repo="grahama1970/agent-skills",
                ),
            )
            run_bridge(state, switchboard_url, ops_run)
            human_checkpoint = json.loads((state / "notify-bridge-checkpoints.json").read_text())
            human_event = [row for row in jsonl(state / "events.jsonl") if row["run_id"] == "run-human"][0]
            assert_true(checks, "human_only_escalation_uses_ops_discord", ops_log.exists() and human_event["event_id"] in human_checkpoint["destinations"]["ops_discord"]["delivered_event_ids"])

            stale_time = time.time() - 2000
            for monitor in (state / "receipts").glob("*/tau-stream-monitor.json"):
                os.utime(monitor, (stale_time, stale_time))
            run_bridge(state, switchboard_url, ops_run)
            heartbeats = [row for row in jsonl(state / "events.jsonl") if row.get("kind") == "heartbeat"]
            assert_true(
                checks,
                "stale_progress_never_live",
                bool(heartbeats) and heartbeats[-1]["state"] != "LIVE",
            )

            lock = state / "notify-bridge.lock"
            fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = run_bridge(state, switchboard_url, ops_run)
                assert_true(checks, "concurrent_collector_refused_without_duplicate", locked["status"] == "LOCKED")
            finally:
                os.close(fd)
        finally:
            server.shutdown()
            server.server_close()

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "schema": "project_watchdog.watchdog_log_delivery_eval.v1",
                "passed": all(checks.values()),
                "checks": checks,
                "mocked": True,
                "live": False,
                "proof_scope": "real bridge entrypoint with temp receipts and fake local delivery endpoints",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
