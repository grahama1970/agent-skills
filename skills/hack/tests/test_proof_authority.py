"""Tests for Hack proof observation and independent validation receipts."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[3]
for import_path in (REPO_ROOT, REPO_ROOT / "skills"):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from hack.hack import app
from hack.proof_authority import (
    build_probe_observation,
    build_proof_validation_receipt,
    file_sha256,
    resolve_session_proof_status,
    run_proof_authority_matrix,
    validate_probe_observation,
    validate_probe_observation_payload,
    validate_proof_validation_receipt,
    write_json,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "proof-authority"


def _hash(name: str) -> str:
    return file_sha256(FIXTURE / name)


def _write_observation(root: Path) -> Path:
    evidence = root / "evidence.json"
    evidence.write_text('{"safe":"signal"}\n')
    observation = build_probe_observation(
        observation_id="obs-test",
        executor_identity="hack-probe-test",
        target_identity="fixture-target@sha256:fixture",
        authorization_manifest_sha256=_hash("authorization-manifest.json"),
        target_runtime_sha256=_hash("runtime-state.json"),
        scan_request_sha256=_hash("scan-request.json"),
        probe_spec_sha256=_hash("probe-spec.json"),
        probe_exit_code=0,
        signal_type="fixture_reflected_signal",
        finding_class="fixture command signal",
        target_summary="fixture local target",
        evidence_summary="bounded signal observed",
        evidence_artifacts=[
            {
                "path": str(evidence),
                "sha256": file_sha256(evidence),
                "redaction": "safe_summary_only",
                "summary": "bounded signal",
            }
        ],
    )
    path = root / "attacks" / "probe-observation.json"
    write_json(path, observation)
    return path


def _write_validation(root: Path, observation_path: Path) -> Path:
    validation = build_proof_validation_receipt(
        validation_id="validation-test",
        observation_path=observation_path,
        replay_spec_sha256=_hash("replay-spec.json"),
        replay_spec_artifact=FIXTURE / "replay-spec.json",
        replay_receipt_sha256=_hash("replay-receipt.json"),
        replay_receipt_artifact=FIXTURE / "replay-receipt.json",
        replay_command=["fixture-replay", "--observation", str(observation_path)],
    )
    path = root / "attacks" / "proof-validation-receipt.json"
    write_json(path, validation)
    return path


class ProofAuthorityTests(unittest.TestCase):
    def test_arbitrary_proof_file_does_not_confirm_exploit(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            attacks = root / "attacks"
            attacks.mkdir()
            (attacks / "proof.json").write_text('{"status":"proved"}\n')

            status = resolve_session_proof_status(root)

        self.assertEqual(status["status"], "OBSERVED_UNCONFIRMED")
        self.assertFalse(status["proven"])
        self.assertIn("Legacy proof-like file", status["reason"])

    def test_zero_exit_probe_without_validation_remains_unconfirmed(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "logs").mkdir()
            (root / "logs" / "probe-command-injection.exit-code").write_text("0\n")
            observation_path = _write_observation(root)

            status = resolve_session_proof_status(root)
            receipt = validate_probe_observation(observation_path)

        self.assertEqual(receipt["status"], "PASS", receipt["errors"])
        self.assertEqual(status["status"], "OBSERVED_UNCONFIRMED")
        self.assertFalse(status["proven"])

    def test_confirmed_requires_independent_bound_validation(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            observation_path = _write_observation(root)
            validation_path = _write_validation(root, observation_path)

            receipt = validate_proof_validation_receipt(validation_path, observation_path)
            status = resolve_session_proof_status(root)

        self.assertEqual(receipt["status"], "PASS", receipt["errors"])
        self.assertTrue(receipt["confirms_exploit"])
        self.assertEqual(status["status"], "CONFIRMED")
        self.assertTrue(status["proven"])

    def test_validation_negative_bindings_fail_closed(self) -> None:
        cases = {
            "wrong-target": lambda payload: payload.__setitem__("target_identity", "wrong@sha256:target"),
            "wrong-authorization": lambda payload: payload.__setitem__("authorization_manifest_sha256", "0" * 64),
            "wrong-runtime": lambda payload: payload.__setitem__("target_runtime_sha256", "1" * 64),
            "wrong-probe": lambda payload: payload.__setitem__("probe_spec_sha256", "2" * 64),
            "wrong-scan-request": lambda payload: payload.__setitem__("scan_request_sha256", "3" * 64),
            "wrong-observation": lambda payload: payload.__setitem__("observation_artifact_sha256", "4" * 64),
            "self-validator": lambda payload: payload.__setitem__("validator_identity", "hack-probe-test"),
            "replay-receipt-mismatch": lambda payload: payload.__setitem__("replay_receipt_sha256", "5" * 64),
            "stale": lambda payload: payload.__setitem__("created_at", "2000-01-01T00:00:00+00:00"),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name), TemporaryDirectory() as temp:
                root = Path(temp)
                observation_path = _write_observation(root)
                validation_path = _write_validation(root, observation_path)
                payload = json.loads(validation_path.read_text())
                mutate(payload)
                write_json(validation_path, payload)

                receipt = validate_proof_validation_receipt(validation_path, observation_path)

            self.assertEqual(receipt["status"], "FAIL")
            self.assertFalse(receipt["confirms_exploit"])
            self.assertTrue(receipt["errors"])

    def test_bound_observation_byte_change_invalidates_confirmation(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            observation_path = _write_observation(root)
            validation_path = _write_validation(root, observation_path)
            observation = json.loads(observation_path.read_text())
            observation["evidence_summary"] = "changed after validation"
            write_json(observation_path, observation)

            receipt = validate_proof_validation_receipt(validation_path, observation_path)

        self.assertEqual(receipt["status"], "FAIL")
        self.assertIn("observation_artifact_sha256", "; ".join(receipt["errors"]))

    def test_unknown_observation_field_fails_strict_schema(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            observation_path = _write_observation(root)
            observation = json.loads(observation_path.read_text())
            observation["exploit_proven"] = True

            errors = validate_probe_observation_payload(observation)

        self.assertIn("observation contains unknown field: exploit_proven", errors)

    def test_matrix_command_writes_required_receipts(self) -> None:
        with TemporaryDirectory() as temp:
            out = Path(temp) / "proof-authority"
            matrix = run_proof_authority_matrix(FIXTURE, out)

            receipt = json.loads((out / "proof-authority-matrix.json").read_text())

        self.assertEqual(matrix["status"], "PASS")
        self.assertEqual(receipt["schema"], "hack.proof_authority_matrix.v1")
        self.assertFalse(receipt["mocked"])
        self.assertEqual(receipt["observed_unconfirmed"]["status"], "OBSERVED_UNCONFIRMED")
        self.assertEqual(receipt["confirmed"]["status"], "CONFIRMED")
        self.assertGreaterEqual(len(receipt["mutation_matrix"]), 8)
        self.assertTrue(all(item["actual_status"] == "FAIL" for item in receipt["mutation_matrix"]))

    def test_cli_prove_proof_authority_writes_matrix(self) -> None:
        with TemporaryDirectory() as temp:
            out = Path(temp) / "proof-authority"
            result = CliRunner().invoke(
                app,
                [
                    "prove-proof-authority",
                    "--fixture",
                    str(FIXTURE),
                    "--out",
                    str(out),
                ],
            )

            matrix = json.loads((out / "proof-authority-matrix.json").read_text())

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(matrix["status"], "PASS")

    def test_module_import_has_no_execution_tokens(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "proof_authority.py").read_text()
        for forbidden in ("import subprocess", "subprocess.run", "import docker", "import socket", "httpx", "requests"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
