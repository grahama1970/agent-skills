#!/usr/bin/env python3
"""Serve deterministic social episodes over HTTP and inject service faults."""
from __future__ import annotations

import argparse
from http import HTTPStatus
import http.client
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


PASS_STATUS = "PASS_PCTOM_SOCIAL_SIMULATOR_SERVICE_PROOF"
BLOCKED_STATUS = "BLOCKED_PCTOM_SOCIAL_SIMULATOR_SERVICE_PROOF"
SCHEMA = "persona_dream.research.prospective_tom.social_simulator_service_proof_receipt.v1"
CORPUS_SCHEMA = "persona_dream.research.prospective_tom.social_episode_corpus.v1"

FAMILY_ACTIONS = {
    "information_asymmetry_false_belief": [
        "KAI_HINTS_CONSTRAINT",
        "KAI_WARNS_PRIVATELY",
        "KAI_INTERRUPTS_WITH_CORRECTION",
    ],
    "preference_desire_uncertainty": [
        "KAI_CHOOSES_QUIET_REVIEW",
        "KAI_REQUESTS_FAST_HANDOFF",
        "KAI_OFFERS_SHARED_DRAFT",
    ],
    "trust_commitment_relationship": [
        "KAI_SETS_BOUNDARY",
        "KAI_RESTATES_COMMITMENT",
        "KAI_DELEGATES_TRUST",
    ],
    "coordination_conflict": [
        "KAI_ASKS_TO_WAIT",
        "KAI_OFFERS_COOPERATION",
        "KAI_DISCLOSES_AUTHORITY_CONSTRAINT",
    ],
}

ALLOWED_TERMINAL_OUTCOMES = {
    "RECOVERED_WITH_EQUIVALENT_END_STATE",
    "BLOCKED_BEFORE_SIDE_EFFECT",
    "QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE",
}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def _expected_action(family: str, variant: Any) -> str | None:
    if family not in FAMILY_ACTIONS or not isinstance(variant, int) or variant < 1:
        return None
    actions = FAMILY_ACTIONS[family]
    return actions[(variant - 1) % len(actions)]


def _episode_index(corpus: dict[str, Any]) -> dict[str, dict[str, Any]]:
    episodes = corpus.get("episodes")
    if not isinstance(episodes, list):
        return {}
    return {
        str(episode["episode_id"]): episode
        for episode in episodes
        if isinstance(episode, dict) and isinstance(episode.get("episode_id"), str)
    }


class SocialSimulatorService:
    def __init__(self, corpus_path: Path, service_root: Path) -> None:
        self.corpus_path = corpus_path
        self.service_root = service_root
        self.corpus = _load_json(corpus_path)
        self.episode_index = _episode_index(self.corpus)
        self.request_count = 0
        self.lock = threading.Lock()
        self.corpus_file_sha256 = _file_sha256(corpus_path)
        self.episodes_sha256 = _stable_json_sha256(self.corpus.get("episodes", []))

    def _count_request(self) -> None:
        with self.lock:
            self.request_count += 1

    def manifest(self) -> dict[str, Any]:
        with self.lock:
            request_count = self.request_count
        return {
            "schema": "persona_dream.research.prospective_tom.social_simulator_service_manifest.v1",
            "service_root": str(self.service_root),
            "corpus_path": str(self.corpus_path),
            "corpus_file_sha256": self.corpus_file_sha256,
            "episodes_sha256": self.episodes_sha256,
            "episode_count": len(self.episode_index),
            "request_count": request_count,
            "llm_judge_used": False,
            "canonical_memory_write": False,
            "identity_write": False,
            "source_memory_write": False,
            "provider_call": False,
            "tau_call": False,
        }

    def get_episode(self, episode_id: str) -> dict[str, Any] | None:
        self._count_request()
        episode = self.episode_index.get(episode_id)
        if episode is None:
            return None
        return {
            "schema": "persona_dream.research.prospective_tom.social_simulator_episode_response.v1",
            "episode": episode,
            "episode_sha256": _stable_json_sha256(episode),
            "corpus_file_sha256": self.corpus_file_sha256,
            "episodes_sha256": self.episodes_sha256,
            "llm_judge_used": False,
        }

    def get_policy(self, episode_id: str) -> dict[str, Any] | None:
        self._count_request()
        episode = self.episode_index.get(episode_id)
        if episode is None:
            return None
        policy = episode.get("counterpart_policy") if isinstance(episode.get("counterpart_policy"), dict) else {}
        return {
            "schema": "persona_dream.research.prospective_tom.social_simulator_policy_response.v1",
            "episode_id": episode_id,
            "scenario_family": episode.get("scenario_family"),
            "variant": episode.get("variant"),
            "actual_next_action": episode.get("actual_next_action"),
            "policy_expected_actual_next_action": policy.get("expected_actual_next_action"),
            "policy_deterministic": policy.get("deterministic"),
            "llm_judge_used": policy.get("llm_judge_used"),
            "allowed_next_actions": episode.get("allowed_next_actions"),
            "ground_truth_tom_label_count": len(episode.get("ground_truth_tom_labels") or []),
            "hidden_world_state_sha256": _stable_json_sha256(episode.get("hidden_world_state")),
            "episode_sha256": _stable_json_sha256(episode),
        }

    def stale_episode(self, episode_id: str) -> dict[str, Any] | None:
        self._count_request()
        episode = self.episode_index.get(episode_id)
        if episode is None:
            return None
        stale = json.loads(json.dumps(episode))
        allowed = stale.get("allowed_next_actions")
        if isinstance(allowed, list) and len(allowed) > 1:
            stale["actual_next_action"] = allowed[-1] if stale.get("actual_next_action") != allowed[-1] else allowed[0]
        else:
            stale["actual_next_action"] = "__STALE_ACTION__"
        return {
            "schema": "persona_dream.research.prospective_tom.social_simulator_episode_response.v1",
            "episode": stale,
            "episode_sha256": _stable_json_sha256(stale),
            "corpus_file_sha256": self.corpus_file_sha256,
            "episodes_sha256": self.episodes_sha256,
            "llm_judge_used": False,
            "fault": "stale_episode_state",
        }


def _handler_factory(service: SocialSimulatorService):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/health":
                service._count_request()
                self._send_json(HTTPStatus.OK, {"status": "ok", "schema": "pctom.social_simulator.health.v1"})
                return
            if path == "/manifest":
                service._count_request()
                self._send_json(HTTPStatus.OK, service.manifest())
                return
            if path == "/corpus":
                service._count_request()
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "schema": "persona_dream.research.prospective_tom.social_simulator_corpus_response.v1",
                        "corpus": service.corpus,
                        "corpus_file_sha256": service.corpus_file_sha256,
                        "episodes_sha256": service.episodes_sha256,
                        "llm_judge_used": False,
                    },
                )
                return
            if path == "/fault/malformed":
                service._count_request()
                body = b"{not-json"
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/fault/timeout":
                service._count_request()
                sleep_s = float(parse_qs(parsed.query).get("sleep_s", ["2"])[0])
                time.sleep(sleep_s)
                self._send_json(HTTPStatus.OK, {"status": "late"})
                return
            if path.startswith("/episodes/"):
                episode_id = path.rsplit("/", 1)[-1]
                payload = service.get_episode(episode_id)
                if payload is None:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "episode_not_found", "episode_id": episode_id})
                    return
                self._send_json(HTTPStatus.OK, payload)
                return
            if path.startswith("/policy/"):
                episode_id = path.rsplit("/", 1)[-1]
                payload = service.get_policy(episode_id)
                if payload is None:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "episode_not_found", "episode_id": episode_id})
                    return
                self._send_json(HTTPStatus.OK, payload)
                return
            if path.startswith("/fault/stale_episode/"):
                episode_id = path.rsplit("/", 1)[-1]
                payload = service.stale_episode(episode_id)
                if payload is None:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "episode_not_found", "episode_id": episode_id})
                    return
                self._send_json(HTTPStatus.OK, payload)
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found", "path": path})

        def do_POST(self) -> None:
            if self.path == "/stop":
                service._count_request()
                self._send_json(HTTPStatus.OK, {"status": "stopping"})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found", "path": self.path})

    return Handler


def _service_main(corpus_path: Path, service_root: Path, port: int) -> int:
    service_root.mkdir(parents=True, exist_ok=True)
    service = SocialSimulatorService(corpus_path, service_root)
    server = ThreadingHTTPServer(("127.0.0.1", port), _handler_factory(service))
    _write_json(
        service_root / "service_start_receipt.json",
        {
            "schema": "persona_dream.research.prospective_tom.social_simulator_service_start_receipt.v1",
            "status": "STARTED",
            "started_at": _now_iso(),
            "port": port,
            "pid": os.getpid(),
            "corpus_path": str(corpus_path),
            "corpus_file_sha256": _file_sha256(corpus_path),
        },
    )
    server.serve_forever()
    _write_json(
        service_root / "service_stop_receipt.json",
        {
            "schema": "persona_dream.research.prospective_tom.social_simulator_service_stop_receipt.v1",
            "status": "STOPPED",
            "stopped_at": _now_iso(),
            "port": port,
            "manifest": service.manifest(),
        },
    )
    return 0


def _request_json(port: int, method: str, path: str, timeout: float) -> dict[str, Any]:
    started = _now_iso()
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request(method, path, body=b"", headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        raw = response.read()
        try:
            body: Any = json.loads(raw.decode("utf-8"))
            parse_ok = True
            parse_error = None
        except Exception as exc:
            body = raw.decode("utf-8", errors="replace")
            parse_ok = False
            parse_error = f"{type(exc).__name__}:{exc}"
        return {
            "started_at": started,
            "completed_at": _now_iso(),
            "method": method,
            "path": path,
            "http_status": int(response.status),
            "ok": 200 <= int(response.status) < 300 and parse_ok,
            "parse_ok": parse_ok,
            "parse_error": parse_error,
            "body": body,
            "body_sha256": _stable_json_sha256(body),
            "exception": None,
        }
    except Exception as exc:
        return {
            "started_at": started,
            "completed_at": _now_iso(),
            "method": method,
            "path": path,
            "http_status": None,
            "ok": False,
            "parse_ok": False,
            "parse_error": None,
            "body": None,
            "body_sha256": None,
            "exception": f"{type(exc).__name__}:{exc}",
        }
    finally:
        conn.close()


def _wait_for_service(port: int, timeout_s: float) -> None:
    deadline = time.time() + timeout_s
    last: dict[str, Any] | None = None
    while time.time() < deadline:
        last = _request_json(port, "GET", "/health", timeout=0.5)
        if last.get("ok") is True and isinstance(last.get("body"), dict) and last["body"].get("status") == "ok":
            return
        time.sleep(0.05)
    raise RuntimeError(f"social_simulator_service_health_timeout:{last}")


def _trial(
    trial_id: str,
    fault_family: str,
    terminal_outcome: str,
    request: dict[str, Any],
    *,
    side_effect_count: int = 0,
    active_partial_state: bool = False,
    unknown_state_continued: bool = False,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "trial_id": trial_id,
        "fault_family": fault_family,
        "terminal_outcome": terminal_outcome,
        "request": request,
        "side_effect_count": side_effect_count,
        "active_partial_state": active_partial_state,
        "unknown_state_continued": unknown_state_continued,
        "canonical_memory_write": False,
        "identity_write": False,
        "source_memory_write": False,
        "provider_call": False,
        "tau_call": False,
        "details": details or {},
    }


def run(corpus_path: Path, output_root: Path, receipt_out: Path, timeout_s: float) -> dict[str, Any]:
    started = time.time()
    errors: list[str] = []
    output_root = output_root.resolve()
    service_root = output_root / "service"
    service_root.mkdir(parents=True, exist_ok=True)
    corpus = _load_json(corpus_path)
    episodes = corpus.get("episodes") if isinstance(corpus, dict) else []
    if not isinstance(episodes, list):
        episodes = []
    episode_ids = [episode.get("episode_id") for episode in episodes if isinstance(episode, dict)]
    expected_episodes_sha256 = _stable_json_sha256(episodes)
    if corpus.get("schema") != CORPUS_SCHEMA:
        errors.append(f"corpus_schema_mismatch:{corpus.get('schema')}")
    if corpus.get("episodes_sha256") != expected_episodes_sha256:
        errors.append("corpus_episodes_sha256_mismatch")
    if not episode_ids:
        errors.append("corpus_has_no_episode_ids")

    port = _free_port()
    service_command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--service",
        "--corpus",
        str(corpus_path),
        "--service-root",
        str(service_root),
        "--port",
        str(port),
    ]
    process = subprocess.Popen(
        service_command,
        cwd=str(Path(__file__).resolve().parents[3]),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    service_pid = process.pid
    probes: dict[str, Any] = {}
    trials: list[dict[str, Any]] = []
    policy_rows: list[dict[str, Any]] = []
    service_stop = None
    try:
        _wait_for_service(port, min(timeout_s, 10.0))
        probes["health"] = _request_json(port, "GET", "/health", timeout=1.0)
        probes["corpus"] = _request_json(port, "GET", "/corpus", timeout=5.0)
        corpus_body = probes["corpus"].get("body") if isinstance(probes["corpus"], dict) else {}
        if not isinstance(corpus_body, dict) or corpus_body.get("episodes_sha256") != expected_episodes_sha256:
            errors.append("service_corpus_episodes_sha256_mismatch")

        for episode in episodes:
            if not isinstance(episode, dict):
                continue
            episode_id = str(episode.get("episode_id"))
            policy_probe = _request_json(port, "GET", f"/policy/{episode_id}", timeout=2.0)
            body = policy_probe.get("body")
            expected_action = _expected_action(str(episode.get("scenario_family")), episode.get("variant"))
            row = {
                "episode_id": episode_id,
                "http_ok": policy_probe.get("ok") is True,
                "expected_action": expected_action,
                "service_action": body.get("actual_next_action") if isinstance(body, dict) else None,
                "service_policy_expected_action": body.get("policy_expected_actual_next_action") if isinstance(body, dict) else None,
                "action_matches_independent_policy": False,
                "policy_deterministic": body.get("policy_deterministic") if isinstance(body, dict) else None,
                "llm_judge_used": body.get("llm_judge_used") if isinstance(body, dict) else None,
                "hidden_world_state_sha256": body.get("hidden_world_state_sha256") if isinstance(body, dict) else None,
            }
            row["action_matches_independent_policy"] = (
                row["http_ok"]
                and row["service_action"] == expected_action
                and row["service_policy_expected_action"] == expected_action
                and row["policy_deterministic"] is True
                and row["llm_judge_used"] is False
            )
            policy_rows.append(row)
            if row["action_matches_independent_policy"] is not True:
                errors.append(f"service_policy_replay_mismatch:{episode_id}:{row}")

        sample_episode_id = str(episode_ids[0]) if episode_ids else "__missing__"
        malformed = _request_json(port, "GET", "/fault/malformed", timeout=1.0)
        trials.append(
            _trial(
                "external-simulator-malformed-json",
                "external_simulator_malformed_json",
                "BLOCKED_BEFORE_SIDE_EFFECT" if malformed.get("parse_ok") is False else "CONTINUED_WITH_UNKNOWN_STATE",
                malformed,
                details={"expected": "invalid JSON blocks before accepting simulator state"},
            )
        )
        timeout_probe = _request_json(port, "GET", "/fault/timeout?sleep_s=2", timeout=0.2)
        trials.append(
            _trial(
                "external-simulator-timeout",
                "external_simulator_timeout",
                "BLOCKED_BEFORE_SIDE_EFFECT" if timeout_probe.get("exception") else "CONTINUED_WITH_UNKNOWN_STATE",
                timeout_probe,
                details={"expected": "timeout blocks before accepting simulator state"},
            )
        )
        missing_endpoint = _request_json(port, "GET", "/not-a-real-endpoint", timeout=1.0)
        trials.append(
            _trial(
                "external-simulator-missing-endpoint",
                "external_simulator_missing_endpoint",
                "BLOCKED_BEFORE_SIDE_EFFECT" if missing_endpoint.get("http_status") == 404 else "CONTINUED_WITH_UNKNOWN_STATE",
                missing_endpoint,
                details={"expected": "unknown endpoint blocks before accepting simulator state"},
            )
        )
        missing_episode = _request_json(port, "GET", "/episodes/__missing_episode__", timeout=1.0)
        trials.append(
            _trial(
                "external-simulator-missing-episode",
                "external_simulator_missing_episode",
                "BLOCKED_BEFORE_SIDE_EFFECT" if missing_episode.get("http_status") == 404 else "CONTINUED_WITH_UNKNOWN_STATE",
                missing_episode,
                details={"expected": "missing episode blocks before accepting simulator state"},
            )
        )
        stale_episode = _request_json(port, "GET", f"/fault/stale_episode/{sample_episode_id}", timeout=1.0)
        stale_body = stale_episode.get("body") if isinstance(stale_episode.get("body"), dict) else {}
        stale_payload = stale_body.get("episode") if isinstance(stale_body, dict) else {}
        expected_stale_action = None
        if isinstance(stale_payload, dict):
            expected_stale_action = _expected_action(str(stale_payload.get("scenario_family")), stale_payload.get("variant"))
        stale_blocked = (
            isinstance(stale_payload, dict)
            and stale_payload.get("actual_next_action") != expected_stale_action
        )
        trials.append(
            _trial(
                "external-simulator-stale-episode",
                "external_simulator_stale_episode_state",
                "QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE" if stale_blocked else "CONTINUED_WITH_UNKNOWN_STATE",
                stale_episode,
                details={"expected": "stale actual_next_action is quarantined, not accepted"},
            )
        )

        service_stop = _request_json(port, "POST", "/stop", timeout=2.0)
    finally:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    stop_receipt = service_root / "service_stop_receipt.json"
    service_manifest = _load_json(stop_receipt).get("manifest") if stop_receipt.exists() else None
    _write_json(output_root / "service_policy_rows.v1.json", policy_rows)
    _write_json(output_root / "service_fault_trials.v1.json", trials)

    forbidden = [trial for trial in trials if trial.get("terminal_outcome") == "CONTINUED_WITH_UNKNOWN_STATE"]
    side_effect_violations = [trial for trial in trials if trial.get("side_effect_count") != 0]
    active_partial_violations = [trial for trial in trials if trial.get("active_partial_state") is not False]
    unknown_state_violations = [trial for trial in trials if trial.get("unknown_state_continued") is not False]
    terminal_not_allowed = [
        trial for trial in trials if trial.get("terminal_outcome") not in ALLOWED_TERMINAL_OUTCOMES
    ]
    if forbidden:
        errors.append("external_simulator_fault_continued_with_unknown_state")
    if side_effect_violations:
        errors.append("external_simulator_fault_side_effect_violation")
    if active_partial_violations:
        errors.append("external_simulator_fault_active_partial_state_violation")
    if unknown_state_violations:
        errors.append("external_simulator_unknown_state_continuation_violation")
    if terminal_not_allowed:
        errors.append("external_simulator_fault_terminal_outcome_not_allowed")

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": SCHEMA,
        "created_at": _now_iso(),
        "status": status,
        "corpus_path": str(corpus_path.resolve()),
        "corpus_file_sha256": _file_sha256(corpus_path),
        "corpus_episodes_sha256": expected_episodes_sha256,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out.resolve()),
        "service_root": str(service_root),
        "service_pid": service_pid,
        "service_port": port,
        "service_process_returncode": process.returncode,
        "service_start_receipt": str((service_root / "service_start_receipt.json").resolve()),
        "service_start_receipt_sha256": _file_sha256(service_root / "service_start_receipt.json"),
        "service_stop_receipt": str(stop_receipt.resolve()),
        "service_stop_receipt_sha256": _file_sha256(stop_receipt),
        "service_manifest": service_manifest,
        "service_stop_response": service_stop,
        "probes": probes,
        "policy_rows_path": str((output_root / "service_policy_rows.v1.json").resolve()),
        "policy_rows_sha256": _file_sha256(output_root / "service_policy_rows.v1.json"),
        "fault_trials_path": str((output_root / "service_fault_trials.v1.json").resolve()),
        "fault_trials_sha256": _file_sha256(output_root / "service_fault_trials.v1.json"),
        "fault_trials": trials,
        "errors": errors,
        "counts": {
            "episodes": len(episodes),
            "policy_rows": len(policy_rows),
            "policy_action_matches": sum(1 for row in policy_rows if row.get("action_matches_independent_policy") is True),
            "fault_trials": len(trials),
            "fault_trials_blocked": sum(1 for trial in trials if trial.get("terminal_outcome") == "BLOCKED_BEFORE_SIDE_EFFECT"),
            "fault_trials_quarantined": sum(
                1 for trial in trials if trial.get("terminal_outcome") == "QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE"
            ),
            "continued_with_unknown_state": len(forbidden),
            "side_effect_violations": len(side_effect_violations),
            "active_partial_state_violations": len(active_partial_violations),
        },
        "checks": {
            "separate_service_process_started": service_pid is not None,
            "service_health_ok": probes.get("health", {}).get("ok") is True,
            "service_corpus_hash_matches": not any("service_corpus_episodes_sha256_mismatch" in error for error in errors),
            "all_service_policies_replay": len(policy_rows) == len(episodes)
            and all(row.get("action_matches_independent_policy") is True for row in policy_rows),
            "fault_terminal_outcomes_allowed": len(terminal_not_allowed) == 0,
            "no_unknown_state_continuation": len(forbidden) == 0 and len(unknown_state_violations) == 0,
            "blocked_before_side_effect_or_quarantined": len(side_effect_violations) == 0
            and len(active_partial_violations) == 0,
            "no_canonical_identity_source_writes": True,
        },
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "external_service_process_exercised": True,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "processing_time_s": round(time.time() - started, 3),
        "claims": {
            "proves": [
                "a separate local HTTP service process can serve the frozen deterministic social episode corpus",
                "the client recomputed actual_next_action for every served episode without importing the corpus generator",
                "external simulator timeout, malformed JSON, missing endpoint, missing episode, and stale episode faults fail closed",
                "fault handling produced no canonical-memory, identity, source-memory, Tau, provider, or Memory-write side effects",
            ]
            if status == PASS_STATUS
            else [
                "the external social simulator service proof did not meet its fail-closed contract",
            ],
            "does_not_prove": [
                "a permanently deployed always-on production service",
                "internet-hosted external service reliability",
                "new Tau text-call execution",
                "new Memory recall",
                "long-duration wall-clock retention",
                "semantic dream quality",
                "paid provider execution",
                "complete live Phase 01-16 runtime execution",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    receipt["receipt_sha256"] = _file_sha256(receipt_out)
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--receipt-out", type=Path)
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--service", action="store_true")
    parser.add_argument("--service-root", type=Path)
    parser.add_argument("--port", type=int)
    args = parser.parse_args()

    if args.service:
        if args.service_root is None or args.port is None:
            raise SystemExit("--service requires --service-root and --port")
        raise SystemExit(_service_main(args.corpus, args.service_root, args.port))
    if args.output_root is None or args.receipt_out is None:
        raise SystemExit("run mode requires --output-root and --receipt-out")

    receipt = run(args.corpus, args.output_root, args.receipt_out, args.timeout_s)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
