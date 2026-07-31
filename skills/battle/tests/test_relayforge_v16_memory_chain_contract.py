from __future__ import annotations

import json
from pathlib import Path

import pytest

from battle_skill import relayforge_v16_memory_chain as chain

SHA = "a" * 64


def _write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _source_root(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    broad = {
        "schema": "battle.v16.relayforge.broad_quarantine_regression.v1",
        "status": "PASS",
        "fixtures": [
            {"function_id": key, "passed": value}
            for key, value in chain.EXPECTED_REGRESSION_VECTOR.items()
        ],
    }
    _write_json(root / "broad-quarantine-regression-matrix.json", broad)
    judge = {"schema": "battle.v16.judge_outcome.v1", "status": "BLOCKED"}
    _write_json(root / "judge-outcome.json", judge)
    qualification = {
        "schema": "battle.v16.deterministic_qualification.v1",
        "status": "BLOCKED",
        "target_id": chain.TARGET_ID,
        "judge_outcome_sha256": chain.canonical_sha256(judge),
        "rf_a_vertical_status": "PASS",
        "rf_b_vertical_status": "PASS",
        "rf_c_vertical_status": "PASS",
        "rf_d_validation_status": "PASS",
        "broad_quarantine_status": "PASS",
        "decoy_shutdown_status": "PASS",
        "broad_quarantine_artifact_sha256": {
            "broad-quarantine-regression-matrix.json": chain.canonical_sha256(broad)
        },
        "blockers": sorted(chain.EXPECTED_SOURCE_BLOCKERS),
        "pass_emitted": False,
    }
    _write_json(root / "deterministic-qualification.json", qualification)
    return root


def test_source_observation_is_hash_bound_and_measured(tmp_path: Path) -> None:
    source_root = _source_root(tmp_path / "qualification")
    receipt, path = chain.build_source_observation(
        deterministic_qualification=source_root, out=tmp_path / "out"
    )
    assert receipt["status"] == "PASS"
    assert receipt["team"] == "blue"
    assert receipt["measured_regression_vector"] == chain.EXPECTED_REGRESSION_VECTOR
    assert receipt["outcome_improvement_proven"] is False
    assert path.is_file()


def test_source_observation_rejects_unexpected_blocker(tmp_path: Path) -> None:
    source_root = _source_root(tmp_path / "qualification")
    path = source_root / "deterministic-qualification.json"
    payload = json.loads(path.read_text())
    payload["blockers"].append("adjacent-blocker")
    _write_json(path, payload)
    with pytest.raises(chain.MemoryChainContractError, match="unexpected deterministic blocker"):
        chain.build_source_observation(
            deterministic_qualification=source_root, out=tmp_path / "out"
        )


def test_source_observation_rejects_judge_hash_drift(tmp_path: Path) -> None:
    source_root = _source_root(tmp_path / "qualification")
    _write_json(source_root / "judge-outcome.json", {"tampered": True})
    with pytest.raises(chain.MemoryChainContractError, match="Judge outcome hash drift"):
        chain.build_source_observation(
            deterministic_qualification=source_root, out=tmp_path / "out"
        )


class _Response:
    def __init__(self, body: dict):
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


class _FakeMemoryClient:
    document: dict | None = None
    leak_kind: str | None = None

    def __init__(self, **_: object):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get(self, path: str) -> _Response:
        assert path == "/health"
        return _Response({"status": "ok"})

    def post(self, path: str, json: dict) -> _Response:
        if path == "/list":
            return _Response({"documents": []})
        if path == "/upsert":
            self.__class__.document = json["documents"][0]
            return _Response({"upserted": 1})
        assert path == "/recall"
        assert self.document is not None
        tags = json["tags"]
        kind = None
        if "team:red" in tags:
            kind = "cross_team"
        elif any(tag.endswith(":wrong") for tag in tags if tag.startswith("memory-key:")):
            kind = "wrong_key"
        elif "source-observation-sha:" + ("0" * 64) in tags:
            kind = "wrong_source_hash"
        if kind is None:
            return _Response({"items": [self.document]})
        if self.leak_kind == kind:
            return _Response({"items": [self.document]})
        return _Response({"items": []})


def _source_receipt() -> dict:
    lesson = {
        "summary": "prefer measured narrow controls",
        "adopt_method": "evidence-targeted-boundary-control",
        "reject_method": "global-service-quarantine",
        "expected_observation": "contain while preserving functionality",
    }
    return {
        "deterministic_qualification_sha256": SHA,
        "judge_outcome_sha256": "b" * 64,
        "measured_artifact_sha256": "c" * 64,
        "lesson": lesson,
        "lesson_sha256": chain.canonical_sha256(lesson),
    }


def test_production_memory_contract_requires_exact_and_negative_isolation(
    tmp_path: Path,
) -> None:
    _FakeMemoryClient.document = None
    _FakeMemoryClient.leak_kind = None
    document, write, recall, write_path, recall_path = chain.write_and_recall_memory(
        source=_source_receipt(),
        source_receipt_sha256="d" * 64,
        out=tmp_path,
        memory_base_url="http://memory",
        client_factory=_FakeMemoryClient,
    )
    assert document["team"] == "blue"
    assert write["mocked"] is False and write["live"] is True
    assert recall["exact_match_count"] == 1
    assert recall["negative_item_counts"] == {
        "cross_team": 0,
        "wrong_key": 0,
        "wrong_source_hash": 0,
    }
    assert write_path.is_file() and recall_path.is_file()


def test_production_memory_contract_rejects_cross_team_recall(tmp_path: Path) -> None:
    _FakeMemoryClient.document = None
    _FakeMemoryClient.leak_kind = "cross_team"
    with pytest.raises(chain.MemoryChainContractError, match="cross_team recall returned"):
        chain.write_and_recall_memory(
            source=_source_receipt(),
            source_receipt_sha256="d" * 64,
            out=tmp_path,
            memory_base_url="http://memory",
            client_factory=_FakeMemoryClient,
        )
    _FakeMemoryClient.leak_kind = None


def _provider_inputs() -> tuple[dict, dict, dict]:
    source = _source_receipt()
    document = chain._memory_document(source=source, source_receipt_sha256="d" * 64)
    pre = {
        "schema": "battle.v16.memory_chain_strategy.v1",
        "status": "PASS",
        "phase": "PRE_MEMORY",
        "target_id": chain.TARGET_ID,
        "team": "blue",
        "strategy_id": "pre",
        "selected_methods": ["global-service-quarantine"],
        "rejected_methods": ["evidence-targeted-boundary-control"],
        "parameters": {"control_scope": "global"},
        "mutation_origin": "pre-memory baseline",
        "expected_observation": "all disabled",
        "memory_origin_reason": None,
        "memory_citations": {},
        "source_observation_receipt_sha256": "d" * 64,
        "source_lesson_sha256": source["lesson_sha256"],
        "mocked": False,
        "live": False,
        "outcome_improvement_proven": False,
    }
    parsed = {
        "rationale": f"Use {document['_key']} {document['content_sha256']} {'e' * 64} {'d' * 64}",
        "memory_origin_reason": "Memory changed selected_methods, rejected_methods, parameters, mutation_origin, expected_observation",
        "strategy_genome": {
            "selected_methods": ["evidence-targeted-boundary-control"],
            "rejected_methods": ["global-service-quarantine"],
            "parameters": {"control_scope": "measured_trust_boundary"},
            "mutation_origin": f"durable Memory record {document['_key']}",
            "expected_observation": "contain while preserving functionality",
            "memory_origin_reason": "Memory changed selected_methods",
        },
    }
    return document, pre, parsed


def test_provider_use_requires_exact_citations_and_strategy_mutation() -> None:
    document, pre, parsed = _provider_inputs()
    post, use = chain.validate_provider_strategy(
        parsed=parsed,
        provider_call={"live": True, "mocked": False, "parse_status": "PASS", "http_status": 200},
        manifest={"status": "PASS", "mocked": False, "live": True},
        document=document,
        recall_receipt_sha256="e" * 64,
        source_receipt_sha256="d" * 64,
        pre_strategy=pre,
        pre_strategy_sha256="f" * 64,
        memory_write_receipt_sha256="9" * 64,
        provider_call_sha256="1" * 64,
        tau_manifest_sha256="2" * 64,
    )
    assert post["phase"] == "POST_MEMORY"
    assert use["status"] == "PASS"
    assert all(use["provider_citations"].values())
    assert "selected_methods" in use["changed_strategy_fields"]
    assert use["outcome_improvement_proven"] is False


def test_provider_use_rejects_mocked_or_missing_origin() -> None:
    document, pre, parsed = _provider_inputs()
    with pytest.raises(chain.MemoryChainContractError, match="not live and non-mocked"):
        chain.validate_provider_strategy(
            parsed=parsed,
            provider_call={"live": True, "mocked": True, "parse_status": "PASS", "http_status": 200},
            manifest={}, document=document, recall_receipt_sha256="e" * 64,
            source_receipt_sha256="d" * 64, pre_strategy=pre,
            pre_strategy_sha256="f" * 64, memory_write_receipt_sha256="9" * 64,
            provider_call_sha256="1" * 64, tau_manifest_sha256="2" * 64,
        )
    parsed.pop("memory_origin_reason")
    parsed["strategy_genome"].pop("memory_origin_reason")
    with pytest.raises(chain.MemoryChainContractError, match="memory_origin_reason"):
        chain.validate_provider_strategy(
            parsed=parsed,
            provider_call={"live": True, "mocked": False, "parse_status": "PASS", "http_status": 200},
            manifest={}, document=document, recall_receipt_sha256="e" * 64,
            source_receipt_sha256="d" * 64, pre_strategy=pre,
            pre_strategy_sha256="f" * 64, memory_write_receipt_sha256="9" * 64,
            provider_call_sha256="1" * 64, tau_manifest_sha256="2" * 64,
        )


def test_full_gate_projects_only_live_topology_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = _source_root(tmp_path / "qualification")

    def fake_memory(**kwargs):
        out = kwargs["out"]
        source = kwargs["source"]
        source_sha = kwargs["source_receipt_sha256"]
        document = chain._memory_document(
            source=source, source_receipt_sha256=source_sha
        )
        write = {"status": "PASS"}
        recall = {"status": "PASS"}
        write_path = _write_json(out / "memory" / "blue" / "memory-write-receipt.json", write)
        recall_path = _write_json(out / "memory" / "blue" / "memory-recall-receipt.json", recall)
        return document, write, recall, write_path, recall_path

    def fake_provider(**kwargs):
        out = kwargs["out"]
        strategy = {
            "status": "PASS",
            "selected_methods": ["evidence-targeted-boundary-control"],
        }
        use = {"status": "PASS"}
        provider_root = out / "provider"
        context_path = _write_json(provider_root / "context" / "tau-public-context.json", {"status": "PASS"})
        manifest_path = _write_json(provider_root / "tau-live" / "manifest.json", {"status": "PASS"})
        call_path = _write_json(provider_root / "tau-live" / "blue" / "scillm-call-receipt.json", {"status": "PASS"})
        use.update({
            "context_path": str(context_path),
            "tau_manifest_path": str(manifest_path),
            "provider_call_path": str(call_path),
        })
        strategy_path = _write_json(out / "strategy-after-memory.json", strategy)
        use_path = _write_json(out / "memory-use-acknowledgement.json", use)
        return strategy, use, strategy_path, use_path

    monkeypatch.setattr(chain, "write_and_recall_memory", fake_memory)
    monkeypatch.setattr(chain, "run_live_provider_use", fake_provider)

    result = chain.run_relayforge_v16_memory_chain(
        target=chain.TARGET_ID,
        deterministic_qualification=source_root,
        out=tmp_path / "out",
    )
    assert result["status"] == "PASS"
    assert result["mocked"] is False
    assert result["live"] is True
    assert result["closed_blocker"] == "durable-memory-packets-unimplemented"
    assert result["remaining_blockers"] == ["live-topology-not-qualified"]
    assert result["outcome_improvement_proven"] is False


@pytest.mark.parametrize("leak_kind", ["wrong_key", "wrong_source_hash"])
def test_production_memory_contract_rejects_other_isolation_leaks(
    tmp_path: Path, leak_kind: str
) -> None:
    _FakeMemoryClient.document = None
    _FakeMemoryClient.leak_kind = leak_kind
    with pytest.raises(chain.MemoryChainContractError, match=f"{leak_kind} recall returned"):
        chain.write_and_recall_memory(
            source=_source_receipt(),
            source_receipt_sha256="d" * 64,
            out=tmp_path,
            memory_base_url="http://memory",
            client_factory=_FakeMemoryClient,
        )
    _FakeMemoryClient.leak_kind = None


def test_provider_use_rejects_missing_exact_hash_citation() -> None:
    document, pre, parsed = _provider_inputs()
    parsed["rationale"] = parsed["rationale"].replace(document["content_sha256"], "missing")
    with pytest.raises(chain.MemoryChainContractError, match="exact Memory provenance citations"):
        chain.validate_provider_strategy(
            parsed=parsed,
            provider_call={"live": True, "mocked": False, "parse_status": "PASS", "http_status": 200},
            manifest={"status": "PASS", "mocked": False, "live": True},
            document=document,
            recall_receipt_sha256="e" * 64,
            source_receipt_sha256="d" * 64,
            pre_strategy=pre,
            pre_strategy_sha256="f" * 64,
            memory_write_receipt_sha256="9" * 64,
            provider_call_sha256="1" * 64,
            tau_manifest_sha256="2" * 64,
        )


def test_provider_use_rejects_unchanged_decision_fields() -> None:
    document, pre, parsed = _provider_inputs()
    pre.update(
        {
            "selected_methods": ["evidence-targeted-boundary-control"],
            "rejected_methods": ["global-service-quarantine"],
            "parameters": {"control_scope": "measured_trust_boundary"},
            "mutation_origin": f"durable Memory record {document['_key']}",
            "expected_observation": "contain while preserving functionality",
        }
    )
    with pytest.raises(chain.MemoryChainContractError, match="changed no strategy decision field"):
        chain.validate_provider_strategy(
            parsed=parsed,
            provider_call={"live": True, "mocked": False, "parse_status": "PASS", "http_status": 200},
            manifest={"status": "PASS", "mocked": False, "live": True},
            document=document,
            recall_receipt_sha256="e" * 64,
            source_receipt_sha256="d" * 64,
            pre_strategy=pre,
            pre_strategy_sha256="f" * 64,
            memory_write_receipt_sha256="9" * 64,
            provider_call_sha256="1" * 64,
            tau_manifest_sha256="2" * 64,
        )
