"""Autonomous image generation must use the funded lane (#1309).

This environment is OAuth-only. The fixture used to shell out to $create-image
with `--backend scillm --model gpt-image-2 --prompt-file ...`, and every one of
those three was wrong: $create-image has no scillm backend, no --prompt-file,
and no --auth flag at all. The call died at argument parsing, so the pipeline
could never generate a panel on its own.

The lane that works is $ask --image-generate --image-auth codex-oauth. What
these tests protect is that the fixture keeps using it, and -- more importantly
-- that it fails loudly rather than quietly substituting a placeholder when
someone asks for an API-key lane. A fixture that silently ships flat colour as
"generated art" is worse than one that stops.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import storyboard_first_fixture as sbf  # noqa: E402


def test_an_api_key_lane_is_refused_rather_than_fallen_back_from(tmp_path):
    """401 is the symptom; a silent placeholder would be the real damage."""
    prompt = tmp_path / "p.md"
    prompt.write_text("a cube", encoding="utf-8")
    with pytest.raises(RuntimeError) as err:
        sbf.run_create_image(
            repo_root=Path.cwd(), prompt_path=prompt, output_path=tmp_path / "o.png",
            size="1024x1024", backend="scillm", model="gpt-image-2",
            attempt_id="t", timeout_s=60,
        )
    assert "OAuth-only" in str(err.value)
    assert sbf.OAUTH_IMAGE_BACKEND in str(err.value)


def test_the_default_lane_is_the_funded_one():
    src = Path(sbf.__file__).read_text(encoding="utf-8")
    assert 'default=OAUTH_IMAGE_BACKEND' in src, "the CLI must not default to an unfunded lane"
    assert '"scillm"' not in src.split("def run_create_image")[1].split("def artifact_ref")[0]


def test_generation_goes_through_ask_not_create_image():
    """$create-image cannot authenticate at all; $ask owns the codex-oauth lane."""
    src = Path(sbf.__file__).read_text(encoding="utf-8")
    body = src.split("def run_create_image")[1].split("def artifact_ref")[0]
    assert '"--image-generate"' in body
    assert '"codex-oauth"' in body
    assert '"generate.py"' not in body and "generate.py" not in body


def test_a_receipt_binds_the_bytes_to_the_call_that_made_them(tmp_path):
    """Otherwise 'generated over OAuth' is an unbacked claim about a PNG."""
    from PIL import Image

    out = tmp_path / "o.png"
    Image.new("RGB", (8, 8), "red").save(out)
    receipt = tmp_path / "o_receipt.json"
    sbf.write_generation_receipt(
        receipt_path=receipt, output_path=out, model="gpt-image-2",
        ask_result={"auth": "codex-oauth", "ask_id": "ask-123", "duration_seconds": 1.0},
    )
    import json
    payload = json.loads(receipt.read_text())
    assert payload["auth"] == "codex-oauth"
    assert payload["api_key_auth_used"] is False
    assert payload["ask_id"] == "ask-123"
    assert payload["sha256"] == __import__("hashlib").sha256(out.read_bytes()).hexdigest()


def test_the_provider_picks_its_own_dimensions_so_output_is_letterboxed(tmp_path):
    """gpt-image-2 returned 1254x1254 for a 1024x1024 request."""
    from PIL import Image

    out = tmp_path / "o.png"
    Image.new("RGB", (1254, 1254), "blue").save(out)
    receipt = tmp_path / "o_receipt.json"
    receipt.write_text("{}", encoding="utf-8")
    sbf.normalize_to_size(out, "1920x1080", receipt)
    with Image.open(out) as im:
        assert im.size == (1920, 1080)
    import json
    assert json.loads(receipt.read_text())["create_image_fit"] == "contain"


def test_a_trailing_json_object_is_recovered_from_noisy_stdout():
    """run.sh wrappers print banners; the payload is the last object."""
    out = sbf.parse_last_json_object('starting up\n{"a": 1}\nnote\n{"auth": "codex-oauth"}\n')
    assert out == {"auth": "codex-oauth"}
    assert sbf.parse_last_json_object("no json here") == {}
