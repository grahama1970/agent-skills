from pathlib import Path

from battle_skill import production_infrastructure_probe as probe


def test_production_infrastructure_receipt_records_success_shape(tmp_path: Path, monkeypatch) -> None:
    _patch_probe_success(monkeypatch)

    receipt = probe.prove_production_infrastructure_deployment(
        out_dir=tmp_path,
        frontend_url="https://battle.example.com",
        backend_health_url="https://battle.example.com/health",
        websocket_url="wss://battle.example.com/live",
        commit="abc123",
        release_id="release-abc123",
        secret_source="production-secret-manager",
        websocket_bearer_token="example-token-not-secret",
    )

    assert receipt["schema"] == "battle.production_infrastructure_deployment_proof.v1"
    assert receipt["status"] == "PASS"
    assert receipt["mocked"] is False
    assert receipt["live"] == "production_infrastructure_deployment"
    assert receipt["target"]["environment"] == "production"
    assert receipt["evidence"]["secret_configuration"]["source"] == "production-secret-manager"
    assert "example-token-not-secret" not in str(receipt)
    assert (tmp_path / "production-infrastructure-deployment-proof.json").exists()


def test_production_infrastructure_receipt_blocks_private_target(tmp_path: Path, monkeypatch) -> None:
    _patch_probe_success(monkeypatch)

    receipt = probe.prove_production_infrastructure_deployment(
        out_dir=tmp_path,
        frontend_url="https://127.0.0.1",
        backend_health_url="https://127.0.0.1/health",
        websocket_url="wss://127.0.0.1/live",
        commit="abc123",
        release_id="release-abc123",
        secret_source="production-secret-manager",
    )

    assert receipt["status"] == "BLOCKED"
    assert any("globally routable" in error for error in receipt["errors"])


def test_production_infrastructure_receipt_blocks_bad_backend_health(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _patch_probe_success(monkeypatch)

    def bad_backend(url: str, *, timeout_s: float) -> dict:
        if url.endswith("/health"):
            return {"status": "BLOCKED", "status_code": 503}
        return {"status": "PASS", "status_code": 200, "body_sha256": "abc"}

    monkeypatch.setattr(probe, "_probe_https", bad_backend)

    receipt = probe.prove_production_infrastructure_deployment(
        out_dir=tmp_path,
        frontend_url="https://battle.example.com",
        backend_health_url="https://battle.example.com/health",
        websocket_url="wss://battle.example.com/live",
        commit="abc123",
        release_id="release-abc123",
        secret_source="production-secret-manager",
    )

    assert receipt["status"] == "BLOCKED"
    assert "production infrastructure backend_health_response.status_code must be 200" in receipt["errors"]


def _patch_probe_success(monkeypatch) -> None:
    monkeypatch.setattr(
        probe,
        "_probe_https",
        lambda url, *, timeout_s: {"status": "PASS", "status_code": 200, "body_sha256": "abc"},
    )
    monkeypatch.setattr(
        probe,
        "_probe_websocket",
        lambda url, *, bearer_token, timeout_s: {
            "status": "PASS",
            "connected": True,
            "authorization_header_present": bearer_token is not None,
        },
    )
    monkeypatch.setattr(
        probe,
        "_probe_tls_certificate",
        lambda url, *, timeout_s: {"status": "PASS", "valid": True},
    )
    monkeypatch.setattr(
        probe,
        "_resolve_dns",
        lambda url, *, allow_private_targets: {
            "status": "PASS",
            "resolves": True,
            "host": "battle.example.com",
            "addresses": ["93.184.216.34"],
        },
    )
