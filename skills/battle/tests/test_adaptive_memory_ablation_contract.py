from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from battle_skill import adaptive_memory_ablation as ablation


SHA = "a" * 64
EXPECTED_PLAN_CANONICAL_SHA256 = "d01edb97c60a04fe11efc9306ebbe830745a6af811ca7aeb162696aaaa9f2bca"
EXPECTED_PLAN_FILE_SHA256 = "9c3d0f2473eaf56b964888f7785ebd1cf77efbfc45cb32d36688431d268efcdc"


def _source_binding() -> dict:
    return {
        "source_campaign_run_id": "battle-004-adaptive-red-blue-lineage-v13",
        "campaign_receipt_sha256": "1" * 64,
        "selection_receipt_sha256": "2" * 64,
        "target_identity_sha256": "3" * 64,
        "scenario_sha256": "4" * 64,
        "research_input_sha256": {"red": "5" * 64, "blue": "6" * 64},
        "parent_genome_sha256": {"red": "7" * 64, "blue": "8" * 64},
        "parent_artifact_sha256": {"red": "9" * 64, "blue": "0" * 64},
    }


def _memory_sources() -> dict:
    red = json.dumps(
        {
            "summary": "red selected evidence",
            "strategy": {
                "selected_methods": ["archive-path-probe"],
                "rejected_methods": ["blind-retry"],
                "parameters": {"depth": 2},
                "expected_observation": "unsafe extraction is observable",
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    blue = json.dumps(
        {
            "summary": "blue selected evidence",
            "strategy": {
                "selected_methods": ["canonical-path-guard"],
                "rejected_methods": ["extension-only-filter"],
                "parameters": {"preserve_api": True},
                "expected_observation": "traversal blocked and functionality preserved",
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "red": {
            "memory_content_sha256": "b" * 64,
            "solution_sha256": hashlib.sha256(red.encode()).hexdigest(),
            "solution_json": red,
            "source_recall_receipt_sha256": "c" * 64,
        },
        "blue": {
            "memory_content_sha256": "d" * 64,
            "solution_sha256": hashlib.sha256(blue.encode()).hexdigest(),
            "solution_json": blue,
            "source_recall_receipt_sha256": "e" * 64,
        },
    }


def _plan(
    seed: str = "v15-seed", *, memory_collection: str | None = None
) -> dict:
    return ablation.build_experiment_plan(
        battle_id="battle-004",
        experiment_id="battle-004-memory-ablation-v15",
        source_binding=_source_binding(),
        memory_sources=_memory_sources(),
        randomization_seed=seed,
        docker_image="python:3.12-slim",
        docker_image_identity="sha256:" + "f" * 64,
        model="gpt-5.5",
        scillm_base_url="http://localhost:4001",
        timeout_s=300,
        memory_collection=memory_collection,
        generated_at="2026-07-15T13:00:00Z",
    )


def test_plan_is_exact_blocked_2x2_by_three_and_hash_stable() -> None:
    first = _plan()
    second = _plan()
    report = ablation.validate_experiment_plan(first)
    assert report["approval"] == "CONTRACT_VALIDATED"
    assert report["trial_count"] == 12
    assert report["condition_counts"] == {
        "R0B0": 3,
        "R1B0": 3,
        "R0B1": 3,
        "R1B1": 3,
    }
    assert ablation.canonical_sha256(first) == ablation.canonical_sha256(second)
    assert ablation.canonical_sha256(first) == EXPECTED_PLAN_CANONICAL_SHA256
    assert {
        trial["memory_namespace"]["collection"] for trial in first["trials"]
    } == {ablation.MEMORY_COLLECTION}
    for block in first["randomization"]["blocks"]:
        assert sorted(block["condition_order"]) == sorted(ablation.CONDITION_ORDER)


def test_written_plan_keeps_canonical_and_file_hashes_distinct(tmp_path) -> None:
    plan = _plan()
    receipt = ablation.write_experiment_plan(plan=plan, out=tmp_path)
    plan_path = tmp_path / "memory-ablation-experiment.json"
    written = json.loads(plan_path.read_text(encoding="utf-8"))

    assert receipt["plan_sha256"] == ablation.canonical_sha256(written)
    assert receipt["plan_file_sha256"] == ablation.file_sha256(plan_path)
    assert receipt["plan_sha256"] == EXPECTED_PLAN_CANONICAL_SHA256
    assert receipt["plan_file_sha256"] == EXPECTED_PLAN_FILE_SHA256
    assert ablation.validate_experiment_plan(written)["plan_sha256"] == receipt["plan_sha256"]


def test_plan_rejects_any_nonregistered_memory_collection() -> None:
    with pytest.raises(ablation.ContractError, match="battle_experiment_memory"):
        _plan(memory_collection="battle-ablation-arbitrary")

    plan = _plan()
    plan["trials"][0]["memory_namespace"]["collection"] = "other"
    with pytest.raises(ablation.ContractError, match="memory collection"):
        ablation.validate_experiment_plan(plan)


def test_nested_runtime_command_cannot_repurpose_battle_uv_environment(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", "/tmp/battle-active-environment")
    payload = ablation._json_command(
        command=[
            sys.executable,
            "-c",
            "import json,os; print(json.dumps({'uv_env': os.getenv('UV_PROJECT_ENVIRONMENT')}))",
        ],
        cwd=tmp_path,
        label="environment isolation probe",
    )
    assert payload == {"uv_env": None}
    assert os.environ["UV_PROJECT_ENVIRONMENT"] == "/tmp/battle-active-environment"


def test_preflight_rejects_any_preexisting_trial_output(tmp_path) -> None:
    plan = _plan()
    used = tmp_path / plan["trials"][0]["output_relpath"]
    used.mkdir(parents=True)
    with pytest.raises(ablation.ContractError, match="output paths are already used"):
        ablation._assert_unused_trial_outputs(plan=plan, experiment_root=tmp_path)


def _write_test_plan(root: Path) -> tuple[dict, Path, str]:
    plan = _plan()
    path = root / "memory-ablation-experiment.json"
    ablation._write_json(path, plan)
    return plan, path, ablation.file_sha256(path)


def _write_terminal_blocked_receipt(
    *,
    plan: dict,
    trial: dict,
    plan_file_sha256: str,
    experiment_root: Path,
) -> Path:
    detail = "deterministic terminal test blocker"
    attempt = {
        "attempt": 1,
        "status": "BLOCKED",
        "family": "test_terminal",
        "signature": hashlib.sha256(
            f"test_terminal: {detail}".encode("utf-8")
        ).hexdigest(),
        "detail": detail,
        "live_started": True,
        "started_at": "2026-07-16T12:34:29Z",
    }
    receipt = ablation._blocked_trial_receipt(
        plan=plan,
        trial=trial,
        attempts=[attempt],
        family="test_terminal",
        detail=detail,
        blocked_by_systemic_failure=False,
        plan_file_sha256=plan_file_sha256,
    )
    receipt["attempts"] = [attempt]
    ablation.validate_trial_receipt(receipt)
    path = experiment_root / trial["output_relpath"] / "trial-receipt.json"
    ablation._write_json(path, receipt)
    return path


def test_run_experiment_resume_reuses_valid_terminal_receipt_without_rerun(
    tmp_path, monkeypatch
) -> None:
    plan, plan_path, plan_file_sha256 = _write_test_plan(tmp_path)
    experiment_root = tmp_path / "run"
    first_trial = sorted(
        plan["trials"], key=lambda item: (item["replicate"], item["order_index"])
    )[0]
    receipt_path = _write_terminal_blocked_receipt(
        plan=plan,
        trial=first_trial,
        plan_file_sha256=plan_file_sha256,
        experiment_root=experiment_root,
    )
    original_receipt_bytes = receipt_path.read_bytes()
    preflight_args: dict = {}
    executed_trial_ids: list[str] = []

    def fake_preflight(**kwargs):
        preflight_args.update(kwargs)
        return {"approval": "APPROVED_FOR_LIVE"}

    def fake_execute_live_trial(**kwargs):
        executed_trial_ids.append(kwargs["trial"]["trial_id"])
        raise ablation.TrialBlocked(
            "test_remaining", "bounded deterministic test blocker", retryable=False
        )

    monkeypatch.setattr(ablation, "preflight_experiment", fake_preflight)
    monkeypatch.setattr(ablation, "_execute_live_trial", fake_execute_live_trial)

    summary = ablation.run_experiment(
        plan_path=plan_path,
        source_root=tmp_path / "source",
        out_dir=experiment_root,
        memory_base_url="http://127.0.0.1:8601",
        scillm_base_url="http://localhost:4001",
        tau_root=tmp_path / "tau",
        resume=True,
    )

    assert len(summary["trial_receipts"]) == 12
    assert summary["trial_receipts"][0]["trial_id"] == first_trial["trial_id"]
    assert first_trial["trial_id"] not in executed_trial_ids
    assert receipt_path.read_bytes() == original_receipt_bytes
    assert list(preflight_args["reusable_trial_ids"]) == [first_trial["trial_id"]]


@pytest.mark.parametrize("receipt_contents", [None, "{not-json"])
def test_resume_rejects_partial_or_malformed_trial_output(
    tmp_path, receipt_contents
) -> None:
    plan, _plan_path, plan_file_sha256 = _write_test_plan(tmp_path)
    first_trial = sorted(
        plan["trials"], key=lambda item: (item["replicate"], item["order_index"])
    )[0]
    trial_dir = tmp_path / "run" / first_trial["output_relpath"]
    trial_dir.mkdir(parents=True)
    if receipt_contents is not None:
        (trial_dir / "trial-receipt.json").write_text(
            receipt_contents, encoding="utf-8"
        )

    with pytest.raises(
        ablation.ContractError, match="terminal receipt|trial receipt is malformed"
    ):
        ablation._load_resumable_trial_receipts(
            plan=plan,
            experiment_root=tmp_path / "run",
            plan_file_sha256=plan_file_sha256,
        )


def test_resume_rejects_wrong_plan_receipt(tmp_path) -> None:
    plan, _plan_path, plan_file_sha256 = _write_test_plan(tmp_path)
    first_trial = sorted(
        plan["trials"], key=lambda item: (item["replicate"], item["order_index"])
    )[0]
    receipt_path = _write_terminal_blocked_receipt(
        plan=plan,
        trial=first_trial,
        plan_file_sha256=plan_file_sha256,
        experiment_root=tmp_path / "run",
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["experiment_plan_file_sha256"] = "0" * 64
    ablation._write_json(receipt_path, receipt)

    with pytest.raises(ablation.ContractError, match="experiment_plan_file_sha256"):
        ablation._load_resumable_trial_receipts(
            plan=plan,
            experiment_root=tmp_path / "run",
            plan_file_sha256=plan_file_sha256,
        )


def test_resume_rejects_unknown_trial_directory(tmp_path) -> None:
    plan, _plan_path, plan_file_sha256 = _write_test_plan(tmp_path)
    (tmp_path / "run" / "trials" / "unknown-trial").mkdir(parents=True)

    with pytest.raises(ablation.ContractError, match="unknown trial output paths"):
        ablation._load_resumable_trial_receipts(
            plan=plan,
            experiment_root=tmp_path / "run",
            plan_file_sha256=plan_file_sha256,
        )


def test_run_experiment_fresh_mode_rejects_existing_terminal_receipt(
    tmp_path, monkeypatch
) -> None:
    plan, plan_path, plan_file_sha256 = _write_test_plan(tmp_path)
    experiment_root = tmp_path / "run"
    first_trial = sorted(
        plan["trials"], key=lambda item: (item["replicate"], item["order_index"])
    )[0]
    _write_terminal_blocked_receipt(
        plan=plan,
        trial=first_trial,
        plan_file_sha256=plan_file_sha256,
        experiment_root=experiment_root,
    )

    def fresh_preflight(**kwargs):
        return ablation._assert_unused_trial_outputs(
            plan=kwargs["plan"], experiment_root=kwargs["experiment_root"]
        )

    monkeypatch.setattr(ablation, "preflight_experiment", fresh_preflight)

    with pytest.raises(ablation.ContractError, match="output paths are already used"):
        ablation.run_experiment(
            plan_path=plan_path,
            source_root=tmp_path / "source",
            out_dir=experiment_root,
            memory_base_url="http://127.0.0.1:8601",
            scillm_base_url="http://localhost:4001",
            tau_root=tmp_path / "tau",
        )


def test_retryable_trial_blocker_uses_two_attempts(tmp_path, monkeypatch) -> None:
    plan, plan_path, _plan_file_sha256 = _write_test_plan(tmp_path)
    experiment_root = tmp_path / "run"

    monkeypatch.setattr(
        ablation,
        "preflight_experiment",
        lambda **_kwargs: {"approval": "APPROVED_FOR_LIVE"},
    )

    def fake_execute_live_trial(**_kwargs):
        raise ablation.TrialBlocked(
            "artifact_pipeline", "provider materialization was malformed"
        )

    monkeypatch.setattr(ablation, "_execute_live_trial", fake_execute_live_trial)

    summary = ablation.run_experiment(
        plan_path=plan_path,
        source_root=tmp_path / "source",
        out_dir=experiment_root,
        memory_base_url="http://127.0.0.1:8601",
        scillm_base_url="http://localhost:4001",
        tau_root=tmp_path / "tau",
    )

    first_trial = sorted(
        plan["trials"], key=lambda item: (item["replicate"], item["order_index"])
    )[0]
    receipt = json.loads(
        (
            experiment_root / first_trial["output_relpath"] / "trial-receipt.json"
        ).read_text()
    )
    assert summary["status"] == "BLOCKED"
    assert [attempt["attempt"] for attempt in receipt["attempts"]] == [1, 2]
    assert receipt["failure"]["family"] == "artifact_pipeline"


class _MemoryResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class _MemoryClient:
    def __init__(self) -> None:
        self.document: dict | None = None
        self.calls: list[tuple[str, dict]] = []
        self.semantic_exact_recall = True

    def __enter__(self) -> "_MemoryClient":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def get(self, path: str) -> _MemoryResponse:
        assert path == "/health"
        return _MemoryResponse({"status": "ok"})

    def post(self, path: str, json: dict) -> _MemoryResponse:
        self.calls.append((path, json))
        assert json.get("collection", ablation.MEMORY_COLLECTION) == ablation.MEMORY_COLLECTION
        if path == "/list":
            key = (json.get("filters") or {}).get("_key")
            if self.document is not None and key == self.document["_key"]:
                return _MemoryResponse({"documents": [dict(self.document)]})
            return _MemoryResponse({"documents": []})
        if path == "/upsert":
            self.document = dict(json["documents"][0])
            return _MemoryResponse(
                {"collection": ablation.MEMORY_COLLECTION, "inserted": 1, "errors": []}
            )
        if path == "/recall":
            assert self.document is not None
            noisy_candidate = {
                key: value for key, value in self.document.items() if key != "kind"
            }
            unrelated_candidate = {
                "_key": "unrelated-blue-memory",
                "team": "blue",
                "tags": ["team:blue", "battle:other"],
            }
            if json["tags"] == self.document["tags"]:
                if self.semantic_exact_recall:
                    return _MemoryResponse({"items": [noisy_candidate]})
                return _MemoryResponse({"items": [unrelated_candidate]})
            return _MemoryResponse({"items": [noisy_candidate, unrelated_candidate]})
        raise AssertionError(f"unexpected Memory path: {path}")


def test_preflight_uses_registered_document_and_proves_exact_isolation(
    tmp_path, monkeypatch
) -> None:
    plan = _plan()
    client = _MemoryClient()
    monkeypatch.setattr(
        ablation, "_validate_source_root_against_plan", lambda **_kwargs: None
    )
    monkeypatch.setattr(
        ablation,
        "resolve_docker_image_identity",
        lambda _image: plan["immutable_inputs"]["docker_image_identity"],
    )
    monkeypatch.setattr(
        ablation, "_tau_runtime_readiness", lambda **_kwargs: {"status": "PASS"}
    )
    monkeypatch.setattr(
        ablation, "_scillm_auth_readiness", lambda **_kwargs: {"status": "PASS"}
    )
    monkeypatch.setattr(
        ablation, "_judge_readiness", lambda **_kwargs: {"status": "PASS"}
    )
    monkeypatch.setattr(ablation.httpx, "Client", lambda **_kwargs: client)

    experiment_root = tmp_path / "experiment"
    receipt = ablation.preflight_experiment(
        plan=plan,
        source_root=tmp_path / "source",
        memory_base_url="http://127.0.0.1:8601",
        scillm_base_url="http://localhost:4001",
        tau_root=tmp_path / "tau",
        experiment_root=experiment_root,
        plan_file_sha256=EXPECTED_PLAN_FILE_SHA256,
    )

    assert receipt["approval"] == "APPROVED_FOR_LIVE"
    readiness = receipt["memory_readiness"]
    assert readiness["collection"] == ablation.MEMORY_COLLECTION
    assert readiness["exact_write_recall_passed"] is True
    assert readiness["opposite_team_item_count"] == 0
    assert readiness["other_trial_item_count"] == 0
    assert readiness["exact_isolation_passed"] is True
    assert client.document is not None
    assert set(client.document) == {
        "_key",
        "problem",
        "solution",
        "kind",
        "tags",
        "battle_id",
        "experiment_id",
        "trial_id",
        "block_id",
        "condition_id",
        "team",
        "source_memory_sha256",
        "status",
    }
    assert "visibility_scope" not in client.document
    recall_calls = [payload for path, payload in client.calls if path == "/recall"]
    assert len(recall_calls) == 3
    assert recall_calls[0]["tags"] == client.document["tags"]
    assert "team:blue" in recall_calls[1]["tags"]
    assert f"trial:{client.document['trial_id']}-other" in recall_calls[2]["tags"]
    assert not any(
        (experiment_root / trial["output_relpath"]).exists()
        for trial in plan["trials"]
    )


def test_live_memory_recall_uses_the_same_exact_identity_tags(tmp_path) -> None:
    plan = _plan()
    trial = next(item for item in plan["trials"] if item["condition_id"] == "R1B0")
    client = _MemoryClient()

    result = ablation._write_and_recall_memory(
        client=client,
        collection=ablation.MEMORY_COLLECTION,
        plan=plan,
        trial=trial,
        team="red",
        out_dir=tmp_path,
    )

    assert result["service_request_count"] == 4
    assert result["recall"]["cross_team_items_absent"] is True
    assert result["recall"]["cross_trial_items_absent"] is True
    assert result["recall"]["opposite_team_item_count"] == 0
    assert result["recall"]["other_trial_item_count"] == 0
    recall_calls = [payload for path, payload in client.calls if path == "/recall"]
    assert len(recall_calls) == 3
    assert recall_calls[0]["tags"] == result["document"]["tags"]
    assert "team:blue" in recall_calls[1]["tags"]
    assert f"trial:{trial['trial_id']}-other" in recall_calls[2]["tags"]


def test_live_memory_recall_falls_back_to_exact_key_lookup(tmp_path) -> None:
    plan = _plan()
    trial = next(item for item in plan["trials"] if item["condition_id"] == "R1B0")
    client = _MemoryClient()
    client.semantic_exact_recall = False

    result = ablation._write_and_recall_memory(
        client=client,
        collection=ablation.MEMORY_COLLECTION,
        plan=plan,
        trial=trial,
        team="red",
        out_dir=tmp_path,
    )

    assert result["service_request_count"] == 14
    assert result["recall"]["exact_match_source"] == "exact_key_lookup"
    list_calls = [payload for path, payload in client.calls if path == "/list"]
    assert list_calls == [
        {
            "collection": ablation.MEMORY_COLLECTION,
            "limit": 2,
            "filters": {"_key": result["document"]["_key"]},
        }
    ]


def test_judge_readiness_binds_frozen_policy_and_executable_hashes() -> None:
    receipt = ablation._judge_readiness(plan=_plan())
    assert receipt["status"] == "PASS"
    assert receipt["policy_id"] == ablation.JUDGE_POLICY_ID
    assert receipt["policy_sha256"] == hashlib.sha256(
        ablation.JUDGE_POLICY_ID.encode("utf-8")
    ).hexdigest()
    assert set(receipt["executable_sha256"]) == {
        "reviewed_pair",
        "judge_runtime",
        "judge_core",
    }


def test_judge_readiness_rejects_policy_drift() -> None:
    plan = _plan()
    plan["immutable_inputs"]["judge_policy_sha256"] = "0" * 64
    with pytest.raises(ablation.ContractError, match="Judge policy hash"):
        ablation._judge_readiness(plan=plan)


def test_plan_randomization_changes_only_predeclared_order() -> None:
    first = _plan("seed-a")
    second = _plan("seed-b")
    assert first["randomization"]["blocks"] != second["randomization"]["blocks"]
    assert {trial["condition_id"] for trial in first["trials"]} == set(
        ablation.CONDITION_ORDER
    )
    assert {trial["condition_id"] for trial in second["trials"]} == set(
        ablation.CONDITION_ORDER
    )


def test_experiment_schema_rejects_unknown_fields() -> None:
    plan = _plan()
    plan["invented_dashboard"] = True
    with pytest.raises(ablation.ContractError):
        ablation.validate_experiment_plan(plan)


def test_plan_rejects_trial_binding_drift() -> None:
    plan = _plan()
    plan["trials"][0]["condition"]["red_memory"] = not plan["trials"][0]["condition"][
        "red_memory"
    ]
    with pytest.raises(ablation.ContractError, match="condition flags|binding hash"):
        ablation.validate_experiment_plan(plan)


def test_plan_rejects_randomization_order_drift() -> None:
    plan = _plan()
    plan["randomization"]["blocks"][0]["condition_order"].reverse()
    with pytest.raises(ablation.ContractError, match="randomization|order"):
        ablation.validate_experiment_plan(plan)


def test_attention_matched_off_control_has_equal_bytes_without_memory_strategy() -> (
    None
):
    plan = _plan()
    off = next(trial for trial in plan["trials"] if trial["condition_id"] == "R0B0")
    on = next(trial for trial in plan["trials"] if trial["condition_id"] == "R1B0")
    off_context = ablation.build_attention_matched_context(
        plan=plan, trial=off, team="red"
    )
    on_context = ablation.build_attention_matched_context(
        plan=plan, trial=on, team="red"
    )
    assert (
        off_context["bytes"]
        == on_context["bytes"]
        == plan["controls"]["context_target_bytes"]
    )
    assert off_context["token_match_status"] == "NOT_VERIFIABLE"
    assert off_context["envelope"]["memory_available"] is False
    assert on_context["envelope"]["memory_available"] is True
    assert "archive-path-probe" not in json.dumps(off_context)
    assert "archive-path-probe" in json.dumps(on_context)
    assert "cite memory" not in ablation.PROMPT_TEMPLATE.lower()
    assert "retain at least one" not in ablation.PROMPT_TEMPLATE.lower()


def test_live_on_context_accepts_only_the_frozen_exact_recall() -> None:
    plan = _plan()
    on = next(trial for trial in plan["trials"] if trial["condition_id"] == "R1B0")
    solution = plan["immutable_inputs"]["memory_sources"]["red"]["solution_json"]
    context = ablation.build_attention_matched_context(
        plan=plan,
        trial=on,
        team="red",
        recalled_solution_json=solution,
    )
    assert context["envelope"]["memory_available"] is True
    with pytest.raises(ablation.ContractError, match="differs from the frozen memory"):
        ablation.build_attention_matched_context(
            plan=plan,
            trial=on,
            team="red",
            recalled_solution_json=json.dumps({"summary": "different"}),
        )


def test_memory_namespaces_are_unique_and_derived_from_battle_id() -> None:
    plan = _plan()
    keys = [
        trial["memory_namespace"][key]
        for trial in plan["trials"]
        for key in ("red_key", "blue_key")
    ]
    assert len(keys) == len(set(keys)) == 24
    assert all(key.startswith("battle-004:") for key in keys)
    assert all("battle-004-v13" not in key for key in keys)


def test_memory_document_matches_registered_source_and_exact_tags() -> None:
    plan = _plan()
    trial = next(item for item in plan["trials"] if item["condition_id"] == "R1B0")
    document = ablation._memory_document(plan=plan, trial=trial, team="red")

    assert set(document) == {
        "_key",
        "problem",
        "solution",
        "kind",
        "tags",
        "battle_id",
        "experiment_id",
        "trial_id",
        "block_id",
        "condition_id",
        "team",
        "source_memory_sha256",
        "status",
    }
    assert "visibility_scope" not in document
    assert document["tags"] == [
        "battle",
        "memory-ablation-v15",
        "battle:battle-004",
        f"experiment:{plan['experiment_id']}",
        f"trial:{trial['trial_id']}",
        f"block:{trial['block_id']}",
        "condition:R1B0",
        "team:red",
        "source-memory-sha:"
        f"{plan['immutable_inputs']['memory_sources']['red']['memory_content_sha256']}",
    ]


def _provider(duration: float = 10.0, tokens: int | None = None) -> dict:
    def optional(value: object) -> dict[str, object]:
        return {
            "status": "EMITTED" if value is not None else "NOT_EMITTED",
            "value": value,
        }

    return {
        "duration_seconds": optional(duration),
        "trial_wall_time_seconds": duration + 2,
        "provider_attempt_count": 1,
        "repair_used": False,
        "input_tokens": optional(tokens),
        "output_tokens": optional(tokens),
        "total_tokens": optional(tokens * 2 if tokens is not None else None),
        "cost_usd": optional(None),
    }


def test_team_outcomes_preserve_red_capability_under_blue_success() -> None:
    judge = {
        "verdict": "BLUE_SUCCESS",
        "judged_pair_count": 1,
        "attempts": [
            {
                "target_contact": "TARGET_CONTACT_UNPROVEN",
                "exploit_confirmed_before_patch": True,
                "exploit_blocked_after_patch": True,
                "functionality_preserved": True,
            }
        ],
    }
    pipeline = {"status": "PASS"}
    red = ablation.build_team_outcome_vector(
        team="red",
        judge=judge,
        pipeline=pipeline,
        provider_execution=_provider(),
        artifact_changed=True,
    )
    blue = ablation.build_team_outcome_vector(
        team="blue",
        judge=judge,
        pipeline=pipeline,
        provider_execution=_provider(),
        artifact_changed=True,
    )
    assert red["descriptive"]["pair_verdict"] == "BLUE_SUCCESS"
    assert red["security"]["exploit_confirmed_before_patch"] is True
    assert blue["security"]["exploit_blocked_after_patch"] is True
    assert blue["security"]["functionality_preserved"] is True


def _outcome(team: str, primary: bool, duration: float = 10.0) -> dict:
    if team == "red":
        security = {
            "exploit_confirmed_before_patch": primary,
            "target_contact": "CONFIRMED" if primary else "NOT_RUN",
            "pipeline_status": "PASS",
            "runtime_evaluated": True,
            "known_parent_failure_avoided": "NOT_EMITTED",
        }
    else:
        security = {
            "exploit_blocked_after_patch": primary,
            "functionality_preserved": primary,
            "pipeline_status": "PASS",
            "runtime_evaluated": True,
            "known_parent_failure_avoided": "NOT_EMITTED",
        }
    return {
        "team": team,
        "security": security,
        "efficiency": {
            "provider_attempt_count": 1,
            "repair_attempt_count": 0,
            "provider_duration_seconds": {"status": "EMITTED", "value": duration},
            "trial_wall_time_seconds": duration + 2,
            "input_tokens": {"status": "NOT_EMITTED", "value": None},
            "output_tokens": {"status": "NOT_EMITTED", "value": None},
            "total_tokens": {"status": "NOT_EMITTED", "value": None},
            "cost_usd": {"status": "NOT_EMITTED", "value": None},
        },
        "descriptive": {
            "pair_verdict": "BLUE_SUCCESS",
            "artifact_changed_from_parent": True,
        },
    }


def test_team_comparator_prioritizes_security_over_efficiency() -> None:
    treatment = _outcome("red", True, duration=20)
    control = _outcome("red", False, duration=1)
    result = ablation.compare_team_outcomes(
        team="red", treatment=treatment, control=control
    )
    assert result["sign"] == 1
    assert result["deciding_component"] == "exploit_confirmed_before_patch"


def test_duration_under_ten_percent_is_a_tie() -> None:
    treatment = _outcome("blue", True, duration=10.5)
    control = _outcome("blue", True, duration=10.0)
    result = ablation.compare_team_outcomes(
        team="blue", treatment=treatment, control=control
    )
    assert result["sign"] == 0


def _contrast(sign: int | None, *, block: int, opponent: bool) -> dict:
    return {
        "available": sign is not None,
        "sign": sign,
        "block_id": f"block-{block:02d}",
        "opponent_memory_on": opponent,
    }


@pytest.mark.parametrize(
    ("signs", "expected"),
    [
        ([1, 1, 1, 1, 0, 0], "OBSERVED_BENEFIT"),
        ([-1, -1, -1, -1, 0, 0], "OBSERVED_REGRESSION"),
        ([0, 0, 0, 0, 0, 0], "NO_OBSERVED_EFFECT"),
        ([1, -1, 1, -1, 0, 0], "INCONCLUSIVE"),
        ([1, 1, 1, 1, 1, None], "INCONCLUSIVE"),
    ],
)
def test_bounded_classification_rules(signs: list[int | None], expected: str) -> None:
    contrasts = [
        _contrast(sign, block=index // 2 + 1, opponent=bool(index % 2))
        for index, sign in enumerate(signs)
    ]
    assert ablation._classification(contrasts) == expected


def test_interaction_requires_two_opposite_sign_block_reversals() -> None:
    contrasts = [
        _contrast(1, block=1, opponent=False),
        _contrast(-1, block=1, opponent=True),
        _contrast(1, block=2, opponent=False),
        _contrast(-1, block=2, opponent=True),
        _contrast(0, block=3, opponent=False),
        _contrast(0, block=3, opponent=True),
    ]
    assert ablation._interaction(contrasts)["classification"] == "OBSERVED_INTERACTION"


def test_blocked_trial_is_preserved_and_cannot_be_called_live_pass() -> None:
    plan = _plan()
    trial = plan["trials"][0]
    receipt = ablation._blocked_trial_receipt(
        plan=plan,
        trial=trial,
        attempts=[
            {
                "attempt": 1,
                "status": "BLOCKED",
                "family": "memory_service",
                "signature": SHA,
                "detail": "service unavailable",
                "live_started": True,
                "started_at": "2026-07-15T13:00:00Z",
            }
        ],
        family="memory_service",
        detail="service unavailable",
        blocked_by_systemic_failure=False,
    )
    ablation.validate_trial_receipt(receipt)
    assert receipt["status"] == "BLOCKED"
    assert receipt["failure"]["blocked_by_systemic_failure"] is False


def test_result_validator_rejects_generalized_causal_language() -> None:
    result = {
        "schema": ablation.RESULT_SCHEMA,
        "status": "BLOCKED",
        "experiment_id": "exp",
        "battle_id": "battle-004",
        "experiment_plan_sha256": SHA,
        "experiment_plan_canonical_sha256": SHA,
        "trial_set_sha256": SHA,
        "aggregation_policy_sha256": SHA,
        "trial_receipts": [
            {
                "trial_id": f"t{i}",
                "condition_id": ablation.CONDITION_ORDER[i % 4],
                "block_id": f"block-{i // 4 + 1:02d}",
                "status": "BLOCKED",
                "sha256": SHA,
            }
            for i in range(12)
        ],
        "blocked_trials": [],
        "contrasts": {
            team: [
                {
                    "team": team,
                    "block_id": f"block-{i // 2 + 1:02d}",
                    "opponent_memory_on": bool(i % 2),
                    "control_trial_id": None,
                    "treatment_trial_id": None,
                    "available": False,
                    "sign": None,
                    "deciding_component": "trial_status",
                    "reason": "blocked",
                }
                for i in range(6)
            ]
            for team in ("red", "blue")
        },
        "classifications": {"red": "INCONCLUSIVE", "blue": "INCONCLUSIVE"},
        "interaction": {
            "red_memory_by_blue_memory": {
                "classification": "INCONCLUSIVE",
                "opposite_sign_reversal_blocks": 0,
                "unresolved_blocks": 3,
            },
            "blue_memory_by_red_memory": {
                "classification": "INCONCLUSIVE",
                "opposite_sign_reversal_blocks": 0,
                "unresolved_blocks": 3,
            },
        },
        "live_proof": {
            "required_trial_count": 12,
            "completed_live_trial_count": 0,
            "all_trials_crossed_tau_docker_judge": False,
        },
        "claims": {
            "may_claim": ["memory caused general improvement", "bounded result"],
            "must_not_claim": [
                "population",
                "production",
                "determinism",
                "exploit success",
            ],
        },
        "research_sources": list(ablation.RESEARCH_SOURCES),
        "created_at": "2026-07-15T13:00:00Z",
    }
    with pytest.raises(ablation.ContractError):
        ablation.validate_result(result)


def test_pass_trial_contract_binds_live_provider_pipeline_judge_and_off_controls() -> (
    None
):
    plan = _plan()
    trial = next(item for item in plan["trials"] if item["condition_id"] == "R0B0")
    binding = ablation.build_trial_input_binding(plan=plan, trial=trial)
    binding["receipt_sha256"] = SHA

    def optional(value: object) -> dict[str, object]:
        return {
            "status": "EMITTED" if value is not None else "NOT_EMITTED",
            "value": value,
        }

    provider_execution = {}
    for team in ("red", "blue"):
        provider_execution[team] = {
            "status": "PASS",
            "live": True,
            "mocked": False,
            "request_envelope_sha256": binding["request_envelopes"][team]["sha256"],
            "scillm_call_receipt_sha256": SHA,
            "tau_handoff_receipt_sha256": SHA,
            "tau_subagent_receipt_sha256": SHA,
            "materialized_artifact_sha256": SHA,
            "strategy_genome_sha256": SHA,
            "provider_identity": optional(None),
            "model": optional("gpt-5.5"),
            "persona": optional(plan["immutable_inputs"]["personas"][team]["id"]),
            "surface": optional("scillm.chat_completions"),
            "provider_request_sha256": optional(None),
            "seed": optional(None),
            "temperature": optional(None),
            "input_tokens": optional(None),
            "output_tokens": optional(None),
            "total_tokens": optional(None),
            "cost_usd": optional(None),
            "duration_seconds": optional(10.0),
            "trial_wall_time_seconds": 12.0,
            "provider_attempt_count": 1,
            "repair_used": False,
            "memory_identifier_citation_count": 0,
        }
    pipelines = {
        team: {
            "status": "PASS",
            "selected_artifact_sha256": SHA,
            "compile_receipt_sha256": SHA,
            "review_receipt_sha256": SHA,
            "handoff_sha256": SHA,
        }
        for team in ("red", "blue")
    }
    receipt = {
        "schema": ablation.TRIAL_SCHEMA,
        "status": "PASS",
        "trial_id": trial["trial_id"],
        "experiment_id": plan["experiment_id"],
        "experiment_plan_sha256": ablation.canonical_sha256(plan),
        "experiment_plan_file_sha256": SHA,
        "battle_id": plan["battle_id"],
        "block_id": trial["block_id"],
        "replicate": trial["replicate"],
        "order_index": trial["order_index"],
        "condition_id": trial["condition_id"],
        "condition": trial["condition"],
        "mocked": False,
        "live": True,
        "fixture_fallback_used": False,
        "input_binding": binding,
        "memory": {
            team: {
                "mode": "OFF",
                "service_request_count": 0,
                "memory_key": None,
                "source_memory_sha256": None,
                "write_receipt_sha256": None,
                "recall_receipt_sha256": None,
                "control_receipt_sha256": SHA,
                "use_was_optional": True,
            }
            for team in ("red", "blue")
        },
        "provider_execution": provider_execution,
        "pipelines": pipelines,
        "judge": {
            "status": "PASS",
            "verdict": "BLUE_SUCCESS",
            "judged_pair_count": 1,
            "receipt_sha256": SHA,
        },
        "outcomes": {
            "red": _outcome("red", True),
            "blue": _outcome("blue", True),
        },
        "failure": None,
        "claims": {
            "may_claim": ["one bounded live trial"],
            "must_not_claim": [
                "general improvement",
                "population-scale effect",
                "exploit success beyond Judge",
            ],
        },
        "created_at": "2026-07-15T13:00:00Z",
    }
    ablation.validate_trial_receipt(receipt)
