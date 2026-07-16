from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import bootstrap_phase11_payload_binding as bootstrap_cli  # noqa: E402
import capture_phase11_provider_source_snapshot as provider_capture  # noqa: E402
import phase11_payload_binding as binding_module  # noqa: E402
from phase11_fixture_helpers import make_compilation_inputs  # noqa: E402


def load_binding(inputs):
    return json.loads(inputs.candidate_binding_path.read_text(encoding="utf-8"))


def validate(inputs, binding):
    return binding_module.validate_payload_binding(
        binding,
        context=inputs.context,
        phase10_payload_path=inputs.phase10_payload_path,
        media_lock_path=inputs.media_lock_path,
    )


def test_bootstrap_binding_has_exact_roles_two_packs_standard_and_silent_sb003(tmp_path: Path):
    inputs, _request, _urls = make_compilation_inputs(tmp_path)
    binding = validate(inputs, load_binding(inputs))

    assert binding["model"] == binding_module.STANDARD_ENDPOINT
    assert binding["mode"] == "standard"
    assert binding["media_roles"]["role_counts"] == {
        "global_start_anchor": 1,
        "global_end_anchor": 1,
        "continuity_only": 6,
        "element_packs": 2,
    }
    assert binding["media_roles"]["global_start_anchor"]["artifact_id"] == "sb_001.start_frame"
    assert binding["media_roles"]["global_end_anchor"]["artifact_id"] == "sb_004.end_frame"
    assert [item["artifact_id"] for item in binding["media_roles"]["continuity_only"]] == [
        "sb_001.end_frame",
        "sb_002.start_frame",
        "sb_002.end_frame",
        "sb_003.start_frame",
        "sb_003.end_frame",
        "sb_004.start_frame",
    ]
    packs = binding["media_roles"]["character_element_packs"]
    assert [pack["identity"] for pack in packs] == ["embry", "kai"]
    assert all(len(pack["references"]) == 2 for pack in packs)
    prompts = binding["input"]["multi_prompt"]
    assert [item["duration"] for item in prompts] == ["2", "3", "2", "3"]
    assert all("Kling v3 Standard I2V" in item["prompt"] for item in prompts)
    assert all("Kling v3 Pro I2V" not in item["prompt"] for item in prompts)
    sb003 = prompts[2]["prompt"]
    assert "If we paddle now" not in sb003
    assert "Dialogue cue:" not in sb003
    assert "quietly says" not in sb003
    assert "No spoken dialogue." in sb003
    assert binding["input"]["generate_audio"] is False
    assert binding["actual_provider_call_attempts"] == 0
    assert binding["submitted"] is False
    assert binding["provider_ready"] is False
    assert binding["live_submit_ready"] is False


def test_missing_binding_is_canonical_blocker_and_provider_capture_does_not_fetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    inputs, _request, _urls = make_compilation_inputs(tmp_path)
    inputs.candidate_binding_path.unlink()

    with pytest.raises(binding_module.PayloadBindingBlocked) as missing:
        binding_module.load_and_validate_payload_binding(
            inputs.candidate_binding_path,
            context=inputs.context,
            phase10_payload_path=inputs.phase10_payload_path,
            media_lock_path=inputs.media_lock_path,
        )
    assert missing.value.code == "BLOCKED_PHASE11_PAYLOAD_BINDING_MISSING"
    assert missing.value.details["next_command"] == "bootstrap-phase11-payload-binding"

    monkeypatch.setattr(provider_capture, "resolve_active_context", lambda *_args, **_kwargs: inputs.context)

    def forbidden_fetch(*_args, **_kwargs):
        raise AssertionError("provider source fetch must not occur before binding validation")

    monkeypatch.setattr(provider_capture, "fetch_remote", forbidden_fetch)
    rc = provider_capture.main([
        "--run-root", str(inputs.context.run_root),
        "--revision-id", inputs.context.revision_id,
        "--json",
    ])
    output = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert output["schema"] == "persona_dream.phase11_provider_source_capture_receipt.v1"
    assert output["status"] == "BLOCKED_PHASE11_PAYLOAD_BINDING_MISSING"
    assert output["gate_status"] == "BLOCKED_PROVIDER_GATE"
    assert output["actual_provider_call_attempts"] == 0


def test_binding_rejects_active_revision_mismatch(tmp_path: Path):
    inputs, _request, _urls = make_compilation_inputs(tmp_path)
    binding = load_binding(inputs)
    binding["revision_id"] = "rev_repair_a8b93ffeca8f"
    with pytest.raises(binding_module.PayloadBindingBlocked) as blocked:
        validate(inputs, binding)
    assert blocked.value.code == "BLOCKED_PHASE11_PAYLOAD_BINDING_IDENTITY"
    assert "revision_id" in blocked.value.details["mismatches"]


def test_binding_rejects_rejected_revision_url(tmp_path: Path):
    inputs, _request, _urls = make_compilation_inputs(tmp_path)
    binding = load_binding(inputs)
    old_revision = "rev_repair_a8b93ffeca8f"
    current_revision = inputs.context.revision_id
    record = binding["media_roles"]["global_start_anchor"]
    old_url = record["public_url"].replace(
        f"/.persona-dream/revisions/{current_revision}/",
        f"/.persona-dream/revisions/{old_revision}/",
    )
    record["public_url"] = old_url
    binding["input"]["start_image_url"] = old_url
    binding["media_roles"]["character_element_packs"][1]["references"][0]["public_url"] = old_url
    binding["input"]["elements"][1]["reference_image_urls"][0] = old_url
    with pytest.raises(binding_module.PayloadBindingBlocked) as blocked:
        validate(inputs, binding)
    assert blocked.value.code == "BLOCKED_PHASE11_PAYLOAD_BINDING_OLD_REVISION_URL"


def test_binding_rejects_standard_pro_prompt_mismatch(tmp_path: Path):
    inputs, _request, _urls = make_compilation_inputs(tmp_path)
    binding = load_binding(inputs)
    binding["input"]["multi_prompt"][0]["prompt"] = binding["input"]["multi_prompt"][0]["prompt"].replace(
        "Kling v3 Standard I2V", "Kling v3 Pro I2V"
    )
    with pytest.raises(binding_module.PayloadBindingBlocked) as blocked:
        validate(inputs, binding)
    assert blocked.value.code == "BLOCKED_PROVIDER_STANDARD_PRO_NAMING_CONFLICT"


def test_binding_rejects_spoken_sb003_when_audio_is_disabled(tmp_path: Path):
    inputs, _request, _urls = make_compilation_inputs(tmp_path)
    binding = deepcopy(load_binding(inputs))
    binding["input"]["multi_prompt"][2]["prompt"] += ' Kai says "go now".'
    with pytest.raises(binding_module.PayloadBindingBlocked) as blocked:
        validate(inputs, binding)
    assert blocked.value.code == "BLOCKED_PROVIDER_AUDIO_OFF_SPOKEN_DIALOGUE"


def test_bootstrap_command_writes_missing_binding_from_active_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    inputs, _request, _urls = make_compilation_inputs(tmp_path)
    inputs.candidate_binding_path.unlink()
    monkeypatch.setattr(bootstrap_cli, "resolve_active_context", lambda *_args, **_kwargs: inputs.context)
    args = bootstrap_cli.parser().parse_args(
        [
            "--run-root", str(inputs.context.run_root),
            "--revision-id", inputs.context.revision_id,
            "--publication-commit", "1" * 40,
            "--json",
        ]
    )
    receipt = bootstrap_cli.bootstrap(args)
    assert receipt["status"] == "PASS_PHASE11_PAYLOAD_BINDING_BOOTSTRAP"
    assert receipt["created"] is True
    assert receipt["role_counts"] == {
        "global_start_anchor": 1,
        "global_end_anchor": 1,
        "continuity_only": 6,
        "element_packs": 2,
    }
    assert receipt["actual_provider_call_attempts"] == 0
    assert inputs.candidate_binding_path.is_file()
    validate(inputs, load_binding(inputs))


def test_provider_capture_invalid_binding_is_json_blocker_before_remote_fetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    inputs, _request, _urls = make_compilation_inputs(tmp_path)
    binding = load_binding(inputs)
    binding["revision_id"] = "rev_repair_a8b93ffeca8f"
    inputs.candidate_binding_path.write_text(
        json.dumps(binding, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(provider_capture, "resolve_active_context", lambda *_args, **_kwargs: inputs.context)

    def forbidden_fetch(*_args, **_kwargs):
        raise AssertionError("invalid binding must block before official source fetch")

    monkeypatch.setattr(provider_capture, "fetch_remote", forbidden_fetch)
    rc = provider_capture.main([
        "--run-root", str(inputs.context.run_root),
        "--revision-id", inputs.context.revision_id,
        "--json",
    ])
    output = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert output["status"] == "BLOCKED_PHASE11_PAYLOAD_BINDING_IDENTITY"
    assert output["gate_status"] == "BLOCKED_PROVIDER_GATE"
    assert output["actual_provider_call_attempts"] == 0
    assert output["provider_live"] is False
    assert output["submitted"] is False


def test_multi_prompt_unicode_character_boundary_and_required_semantics() -> None:
    base = binding_module.compile_concise_prompt(
        "Waterline wide at Kahaluʻu Bay. Embry and Kai wait outside the lineup over visible lava reef.",
        panel_id="sb_001",
        start=0,
        end=2,
    )
    exact = base + (" " * (binding_module.MAX_MULTI_PROMPT_CHARS - len(base)))
    assert len(exact) == 512
    assert binding_module.compiled_prompt_blockers(
        exact, panel_id="sb_001", start=0, end=2
    ) == []

    over = exact + "x"
    blockers = binding_module.compiled_prompt_blockers(
        over, panel_id="sb_001", start=0, end=2
    )
    assert "BLOCKED_PROVIDER_MULTI_PROMPT_MAX_512:sb_001:513" in blockers


def test_compiled_prompts_preserve_required_tokens_and_change_failed_request_hash(
    tmp_path: Path,
) -> None:
    inputs, _request, _urls = make_compilation_inputs(tmp_path)
    body, blockers, _changes = __import__("phase11_canonical_common").compile_request_body(inputs)
    assert blockers == []
    prompts = body["multi_prompt"]
    assert [len(item["prompt"]) for item in prompts] == [247, 268, 362, 271]
    for index, item in enumerate(prompts):
        panel_id = f"sb_{index + 1:03d}"
        start = sum((2, 3, 2, 3)[:index])
        end = start + (2, 3, 2, 3)[index]
        assert binding_module.compiled_prompt_blockers(
            item["prompt"], panel_id=panel_id, start=start, end=end
        ) == []
    assert __import__("phase11_canonical_common").canonical_sha256(body) != (
        "sha256:444a5a27e35c70848819aa561fc429f6e48d633c2bcc8ac805f675ac5b5f4b71"
    )
