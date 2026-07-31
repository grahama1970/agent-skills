#!/usr/bin/env python3
"""Tests for the no-Docker Dogpile-to-Hack scan request validator."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from hack.hack import app
from hack.hack_scan_request import REQUEST_SCHEMA, validate_scan_request

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "hack-scan-request"


def _load_valid_fixture(tmp: Path) -> Path:
    shutil.copytree(FIXTURE_DIR, tmp, dirs_exist_ok=True)
    return tmp / "valid.json"


def _mutate_fixture(tmp: Path, mutator) -> Path:
    request_path = _load_valid_fixture(tmp)
    payload = json.loads(request_path.read_text())
    mutator(payload, tmp)
    request_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return request_path


class HackScanRequestTests(unittest.TestCase):
    def test_module_import_and_validation_do_not_use_execution_entrypoints(self) -> None:
        module_path = Path(__file__).resolve().parents[1] / "hack_scan_request.py"
        source = module_path.read_text()
        forbidden_tokens = ("import docker", "import subprocess", "import socket", "import requests", "httpx", "urllib")
        for token in forbidden_tokens:
            self.assertNotIn(token, source)

        with TemporaryDirectory() as temp:
            request_path = _load_valid_fixture(Path(temp))
            receipt = validate_scan_request(request_path, expected_target="fixture-target@sha256:fixture")

        self.assertEqual(receipt["status"], "PASS", receipt["errors"])
        self.assertFalse(receipt["docker_invoked"])
        self.assertFalse(receipt["subprocess_invoked"])
        self.assertFalse(receipt["network_invoked"])

    def test_valid_fixture_passes_with_source_bearing_evidence(self) -> None:
        with TemporaryDirectory() as temp:
            request_path = _load_valid_fixture(Path(temp))
            receipt = validate_scan_request(request_path, expected_target="fixture-target@sha256:fixture")

        self.assertEqual(receipt["schema"], "hack.scan_request_validation_receipt.v1")
        self.assertEqual(receipt["status"], "PASS", receipt["errors"])
        self.assertEqual(receipt["target_identity"], "fixture-target@sha256:fixture")
        self.assertEqual(receipt["source_bearing_evidence_count"], 1)
        self.assertFalse(receipt["execution_started"])

    def test_cli_writes_receipt(self) -> None:
        with TemporaryDirectory() as temp:
            request_path = _load_valid_fixture(Path(temp))
            receipt_path = Path(temp) / "receipt.json"
            result = CliRunner().invoke(
                app,
                [
                    "validate-scan-request",
                    str(request_path),
                    "--expected-target",
                    "fixture-target@sha256:fixture",
                    "--receipt-out",
                    str(receipt_path),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.output)
            receipt = json.loads(receipt_path.read_text())

        self.assertEqual(receipt["status"], "PASS")
        self.assertFalse(receipt["docker_invoked"])

    def test_negative_fixtures_fail_closed(self) -> None:
        cases = {
            "expired": lambda payload, _tmp: payload.__setitem__("expires_at", "2000-01-01T00:00:00Z"),
            "wrong-target": lambda payload, _tmp: payload["target"].__setitem__("immutable_ref", "sha256:wrong"),
            "source-packet-hash-mismatch": lambda payload, _tmp: payload["source_packet"].__setitem__("sha256", "0" * 64),
            "evidence-hash-mismatch": lambda payload, _tmp: payload["selected_source_evidence"][0].__setitem__("content_sha256", "1" * 64),
            "zero-source-bearing-evidence": lambda payload, _tmp: payload["selected_source_evidence"][0].__setitem__("source_bearing", False),
            "unknown-field": lambda payload, _tmp: payload.__setitem__("unsafe_execution_hint", "run docker now"),
            "unknown-schema": lambda payload, _tmp: payload.__setitem__("schema", "dogpile.hack_scan_request.v2"),
        }
        for name, mutator in cases.items():
            with self.subTest(name=name), TemporaryDirectory() as temp:
                request_path = _mutate_fixture(Path(temp), mutator)
                receipt = validate_scan_request(
                    request_path,
                    expected_target="fixture-target@sha256:fixture",
                    now=datetime(2026, 7, 29, tzinfo=timezone.utc),
                )
                self.assertEqual(receipt["status"], "FAIL")
                self.assertTrue(receipt["errors"])
                self.assertFalse(receipt["docker_invoked"])
                self.assertFalse(receipt["subprocess_invoked"])
                self.assertFalse(receipt["network_invoked"])

    def test_selected_evidence_artifact_must_exist(self) -> None:
        with TemporaryDirectory() as temp:
            request_path = _mutate_fixture(
                Path(temp),
                lambda payload, _tmp: payload["selected_source_evidence"][0].__setitem__("retrieval_artifact", "evidence/missing.md"),
            )
            receipt = validate_scan_request(request_path, expected_target="fixture-target@sha256:fixture")

        self.assertEqual(receipt["status"], "FAIL")
        self.assertIn("retrieval_artifact does not exist", "; ".join(receipt["errors"]))

    def test_source_packet_artifact_must_exist(self) -> None:
        with TemporaryDirectory() as temp:
            request_path = _mutate_fixture(
                Path(temp),
                lambda payload, _tmp: payload["source_packet"].__setitem__("artifact_path", "missing-source-packet.json"),
            )
            receipt = validate_scan_request(request_path, expected_target="fixture-target@sha256:fixture")

        self.assertEqual(receipt["status"], "FAIL")
        self.assertIn("source_packet.artifact_path does not exist", "; ".join(receipt["errors"]))

    def test_cli_failure_returns_exit_code_two(self) -> None:
        with TemporaryDirectory() as temp:
            request_path = _mutate_fixture(Path(temp), lambda payload, _tmp: payload.__setitem__("schema", "wrong"))
            result = CliRunner().invoke(app, ["validate-scan-request", str(request_path)])

        self.assertEqual(result.exit_code, 2)

    def test_no_subprocess_call_during_api_validation(self) -> None:
        with TemporaryDirectory() as temp:
            request_path = _load_valid_fixture(Path(temp))
            original_run = subprocess.run

            def fail_run(*_args, **_kwargs):
                raise AssertionError("subprocess.run must not be called")

            subprocess.run = fail_run
            try:
                receipt = validate_scan_request(request_path, expected_target="fixture-target@sha256:fixture")
            finally:
                subprocess.run = original_run

        self.assertEqual(receipt["status"], "PASS", receipt["errors"])


if __name__ == "__main__":
    unittest.main()
