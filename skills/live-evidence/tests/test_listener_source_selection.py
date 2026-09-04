"""PipeWire source selection regressions for interview-day audio."""

from types import SimpleNamespace

import pytest

from live_evidence import listener


def _patch_pactl(monkeypatch, *, sources: str, sinks: str = "") -> None:
    def fake_run(command, **_kwargs):
        if command[:4] == ["pactl", "list", "short", "sources"]:
            return SimpleNamespace(stdout=sources)
        if command[:4] == ["pactl", "list", "short", "sinks"]:
            return SimpleNamespace(stdout=sinks)
        raise AssertionError(command)

    monkeypatch.setattr(listener.subprocess, "run", fake_run)


def test_auto_jabra_input_prefers_bluetooth_over_other_running_input(monkeypatch) -> None:
    _patch_pactl(
        monkeypatch,
        sources=(
            "64\talsa_input.usb-Webcam-00.source\tPipeWire\ts16le 1ch 48000Hz\tRUNNING\n"
            "134\tbluez_input.50_1A_A5_27_4B_1D.0\tPipeWire\ts16le 1ch 16000Hz\tSUSPENDED\n"
        ),
    )

    assert listener.resolve_pipewire_source("auto:jabra-input") == (
        "bluez_input.50_1A_A5_27_4B_1D.0",
        "auto_jabra_input",
    )


def test_auto_jabra_input_fails_closed_when_missing(monkeypatch) -> None:
    _patch_pactl(
        monkeypatch,
        sources="64\talsa_input.usb-Webcam-00.source\tPipeWire\ts16le 1ch 48000Hz\tRUNNING\n",
    )

    with pytest.raises(RuntimeError, match="found no Jabra input"):
        listener.resolve_pipewire_source("auto:jabra-input")


def test_stale_sink_request_fails_closed(monkeypatch) -> None:
    _patch_pactl(
        monkeypatch,
        sources="134\tbluez_input.50_1A_A5_27_4B_1D.0\tPipeWire\ts16le 1ch 16000Hz\tRUNNING\n",
        sinks="103\tbluez_output.50_1A_A5_27_4B_1D.1\tPipeWire\ts16le 1ch 16000Hz\tRUNNING\n",
    )

    with pytest.raises(RuntimeError, match="requested sink"):
        listener.resolve_pipewire_source(
            "sink:alsa_output.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.analog-stereo"
        )
