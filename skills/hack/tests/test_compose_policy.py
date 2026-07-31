"""Tests for Hack Compose policy compilation and launch gating."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hack.compose_policy import (
    compile_compose_policy,
    mark_execution_started,
    sanitize_compose_model,
)


AUTHORIZATION = {
    "allowed_ports": [80, 443],
}


def service_model(service: dict) -> dict:
    return {"services": {"web": service}}


class ComposePolicyTests(unittest.TestCase):
    def test_safe_model_sanitizes_to_loopback_and_readonly_mount(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "public").mkdir()
            model = service_model(
                {
                    "image": "nginx:1.25-alpine",
                    "ports": ["127.0.0.1:80:80"],
                    "volumes": ["./public:/usr/share/nginx/html:ro"],
                    "environment": {"HACK_FIXTURE": "safe"},
                }
            )

            sanitized, allowed, errors = sanitize_compose_model(
                model,
                source_root=root,
                session_root=root / "session",
                authorization=AUTHORIZATION,
            )

        self.assertEqual(errors, [])
        self.assertIn("loopback_ports", allowed)
        self.assertIn("bounded_bind_mounts", allowed)
        self.assertEqual(sanitized["services"]["web"]["ports"][0]["host_ip"], "127.0.0.1")
        self.assertTrue(sanitized["services"]["web"]["volumes"][0]["read_only"])

    def test_negative_feature_matrix_rejects_before_launch(self) -> None:
        cases = {
            "privileged": ({"image": "alpine", "privileged": True}, "PRIVILEGED_DENIED"),
            "docker_socket": ({"image": "alpine", "volumes": ["/var/run/docker.sock:/sock"]}, "CONTAINER_SOCKET_MOUNT_DENIED"),
            "host_bind": ({"image": "alpine", "volumes": ["/etc:/host:ro"]}, "HOST_BIND_OUTSIDE_ROOT"),
            "source_write": ({"image": "alpine", "volumes": ["./src:/src:rw"]}, "SOURCE_BIND_WRITABLE_DENIED"),
            "host_network": ({"image": "alpine", "network_mode": "host"}, "HOST_NAMESPACE_DENIED"),
            "cap_add": ({"image": "alpine", "cap_add": ["SYS_ADMIN"]}, "CAP_ADD_DENIED"),
            "devices": ({"image": "alpine", "devices": ["/dev/kvm:/dev/kvm"]}, "DEVICES_DENIED"),
            "outside_build": ({"build": {"context": "../../"}}, "BUILD_CONTEXT_OUTSIDE_ROOT"),
            "env_file": ({"image": "alpine", "env_file": ["/etc/passwd"]}, "UNSUPPORTED_SERVICE_FIELD"),
            "public_port": ({"image": "alpine", "ports": ["0.0.0.0:80:80"]}, "NON_LOOPBACK_PORT_DENIED"),
            "extra_hosts": ({"image": "alpine", "extra_hosts": ["metadata:169.254.169.254"]}, "EXTRA_HOSTS_DENIED"),
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            for name, (service, expected_code) in cases.items():
                with self.subTest(name):
                    _sanitized, _allowed, errors = sanitize_compose_model(
                        service_model(service),
                        source_root=root,
                        session_root=root / "session",
                        authorization=AUTHORIZATION,
                    )
                    self.assertIn(expected_code, {error["code"] for error in errors})

    def test_compile_receipt_records_hashes_and_no_execution_started(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "docker-compose.yml"
            auth = root / "authorization.json"
            out = root / "sanitized.yml"
            receipt = root / "receipt.json"
            source.write_text("services:\n  web:\n    image: nginx\n")
            auth.write_text(json.dumps({"allowed_ports": [80, 443]}))

            result = compile_compose_policy(
                source_compose_path=source,
                authorization_manifest=auth,
                sanitized_compose_path=out,
                receipt_out=receipt,
                source_root=root,
                session_root=root / "session",
                normalizer=lambda _path: service_model({"image": "nginx"}),
            )
            payload = json.loads(receipt.read_text())

            self.assertEqual(result.status, "PASS")
            self.assertTrue(out.exists())
        self.assertEqual(payload["schema"], "hack.compose_policy_receipt.v1")
        self.assertEqual(payload["status"], "PASS")
        self.assertFalse(payload["execution_started"])
        self.assertRegex(payload["sanitized_compose_sha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(payload["normalized_model_sha256"], r"^[a-f0-9]{64}$")

    def test_mark_execution_started_updates_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "receipt.json"
            receipt.write_text(
                json.dumps(
                    {
                        "schema": "hack.compose_policy_receipt.v1",
                        "execution_started": False,
                    }
                )
            )

            mark_execution_started(receipt)
            payload = json.loads(receipt.read_text())

        self.assertTrue(payload["execution_started"])
        self.assertIn("execution_started_at", payload)


if __name__ == "__main__":
    unittest.main()
