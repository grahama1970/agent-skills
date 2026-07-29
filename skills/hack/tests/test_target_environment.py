"""Tests for Hack sterile target environment boundaries."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from hack.compose_policy import compile_compose_policy
from hack.target_environment import (
    build_sterile_target_environment,
    parse_env_output,
    redact_text,
    run_sterile_target_environment_proof,
    write_target_environment_receipt,
)


class TargetEnvironmentTests(unittest.TestCase):
    def test_builder_does_not_inherit_operator_secret_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env, metadata = build_sterile_target_environment(
                session_dir=Path(tmp),
                gateway_port="80",
                inherited_environment={
                    "OPENAI_API_KEY": "must-not-cross-boundary",
                    "GITHUB_TOKEN": "must-not-cross-boundary",
                    "AWS_SECRET_ACCESS_KEY": "must-not-cross-boundary",
                    "HACK_TEST_SECRET": "must-not-cross-boundary",
                },
            )

        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", env)
        self.assertNotIn("HACK_TEST_SECRET", env)
        self.assertFalse(metadata["inherited_operator_environment"])
        self.assertIn("OPENCLAW_GATEWAY_PORT", env)

    def test_redaction_removes_secret_names_and_values(self) -> None:
        redacted, count = redact_text(
            "OPENAI_API_KEY=must-not-cross-boundary plain",
            [("OPENAI_API_KEY", "must-not-cross-boundary")],
        )

        self.assertNotIn("OPENAI_API_KEY", redacted)
        self.assertNotIn("must-not-cross-boundary", redacted)
        self.assertGreaterEqual(count, 2)

    def test_receipt_records_no_inherited_operator_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth = root / "auth.json"
            compose = root / "docker-compose.yml"
            sanitized = root / "sanitized.yml"
            receipt = root / "target-environment-receipt.json"
            auth.write_text("{}")
            compose.write_text("services:\n  envcheck:\n    image: python:3.12-slim\n")
            sanitized.write_text('{"services":{"envcheck":{"image":"python:3.12-slim"}}}\n')
            target_env = {"PATH": "/usr/bin:/bin", "OPENCLAW_GATEWAY_PORT": "80"}

            payload = write_target_environment_receipt(
                receipt_out=receipt,
                authorization_manifest=auth,
                sanitized_compose_path=sanitized,
                compose_source_path=compose,
                target_env=target_env,
                metadata={"generated_value_hashes": {"OPENCLAW_GATEWAY_PORT": "a" * 64}},
                rejected_variable_references=[],
                redaction_count=0,
            )

        self.assertEqual(payload["schema"], "hack.target_environment_receipt.v1")
        self.assertFalse(payload["inherited_operator_environment"])
        self.assertEqual(payload["status"], "PASS")

    def test_undeclared_compose_variable_rejects_before_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            compose = root / "docker-compose.yml"
            auth = root / "auth.json"
            compose.write_text(
                "services:\n"
                "  envcheck:\n"
                "    image: python:3.12-slim\n"
                "    environment:\n"
                "      LEAK_ME: \"${OPENAI_API_KEY}\"\n"
            )
            auth.write_text(json.dumps({"allowed_ports": [80]}))

            result = compile_compose_policy(
                source_compose_path=compose,
                authorization_manifest=auth,
                sanitized_compose_path=root / "sanitized.yml",
                receipt_out=root / "receipt.json",
                source_root=root,
                session_root=root,
                compose_env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                allowed_variable_names={"PATH"},
                normalizer=lambda _path: {"services": {"envcheck": {"image": "python:3.12-slim"}}},
            )
            receipt = json.loads((root / "receipt.json").read_text())

        self.assertEqual(result.status, "FAIL")
        self.assertIn("UNDECLARED_VARIABLE_REFERENCE", {item["code"] for item in receipt["rejected_features"]})

    def test_parse_env_output(self) -> None:
        env = parse_env_output("A=1\nB=two=2\n")

        self.assertEqual(env["A"], "1")
        self.assertEqual(env["B"], "two=2")

    def test_live_proof_can_be_called_with_fixture_paths(self) -> None:
        # The command-level proof runs Docker in the closure proof. This unit
        # test keeps the fixture paths importable and ensures the function is
        # available without executing Docker during import.
        self.assertTrue(callable(run_sterile_target_environment_proof))


if __name__ == "__main__":
    unittest.main()
