import json
from pathlib import Path

from src import elevenlabs_articulation as ea
from src.articulated_psola_renderer import REQUIRED_TOKENS


class FakeResponse:
    def __init__(self, token: str):
        self.status_code = 200
        self.content = f"fake-audio-{token}".encode()
        self.headers = {"content-type": "audio/mpeg", "request-id": f"req-{token}"}


class FakeClient:
    def __init__(self):
        self.requests = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, *, params, headers, json, timeout):
        token = f"token-{len(self.requests)}"
        self.requests.append(
            {
                "url": url,
                "params": params,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return FakeResponse(token)


def test_generate_elevenlabs_articulation_inventory_writes_12_tokens(monkeypatch, tmp_path: Path):
    fake_client = FakeClient()
    monkeypatch.setattr(ea.httpx, "Client", lambda: fake_client)

    def fake_convert(input_audio: Path, output_wav: Path, sample_rate: int) -> None:
        output_wav.write_bytes(b"RIFFfake-wave")

    monkeypatch.setattr(ea, "_convert_to_wav", fake_convert)

    result = ea.generate_elevenlabs_articulation_inventory(
        output_dir=tmp_path / "inventory",
        api_key="test_key",
        duration_seconds=1.2,
        prompt_influence=0.72,
    )

    assert result.token_count == len(REQUIRED_TOKENS) == 12
    manifest = json.loads(Path(result.manifest_json).read_text())
    receipts = json.loads(Path(result.receipt_json).read_text())
    assert manifest["schema"] == "hum.elevenlabs_articulation_inventory.v1"
    assert manifest["api"] == "sound-generation"
    assert manifest["endpoint"] == "https://api.elevenlabs.io/v1/sound-generation"
    assert manifest["duration_seconds"] == 1.2
    assert manifest["prompt_influence"] == 0.72
    assert len(manifest["tokens"]) == 12
    assert len(receipts["receipts"]) == 12
    for token in REQUIRED_TOKENS:
        assert (Path(result.samples_dir) / f"{token}.wav").is_file()
    assert len(fake_client.requests) == 12
    assert fake_client.requests[0]["url"] == "https://api.elevenlabs.io/v1/sound-generation"
    assert fake_client.requests[0]["headers"]["xi-api-key"] == "test_key"
    assert fake_client.requests[0]["params"]["output_format"] == "mp3_44100_128"
    assert fake_client.requests[0]["json"]["model_id"] == "eleven_text_to_sound_v2"
    assert fake_client.requests[0]["json"]["duration_seconds"] == 1.2
    assert fake_client.requests[0]["json"]["prompt_influence"] == 0.72
    assert "voice_settings" not in fake_client.requests[0]["json"]
