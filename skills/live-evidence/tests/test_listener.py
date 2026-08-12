"""Tests for live audio listener command construction."""

import httpx

from live_evidence.listener import _backend_client, _pipewire_record_command


def test_pipewire_source_capture_uses_plain_target() -> None:
    command = _pipewire_record_command("alsa_input.usb-example")

    assert command[:3] == ["pw-record", "--target", "alsa_input.usb-example"]
    assert "-P" not in command


def test_pipewire_sink_capture_sets_sink_monitor_property() -> None:
    command = _pipewire_record_command("sink:alsa_output.usb-speakers")

    assert command[:5] == [
        "pw-record",
        "-P",
        "{ stream.capture.sink=true }",
        "--target",
        "alsa_output.usb-speakers",
    ]


def test_backend_client_ignores_host_proxy_and_ca_environment() -> None:
    timeout = httpx.Timeout(connect=1.0, read=1.0, write=1.0, pool=1.0)

    client = _backend_client("http://127.0.0.1:8787/", timeout=timeout)
    try:
        assert client.base_url == "http://127.0.0.1:8787"
        assert client.trust_env is False
    finally:
        client.close()
