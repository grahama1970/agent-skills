"""Tests for live audio listener command construction."""

from live_evidence.listener import _pipewire_record_command


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
