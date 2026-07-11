#!/usr/bin/env python3
"""Run the one-shot journal-bound PipeWire playback proof."""

from pathlib import Path
import json
import typer

from embry_voice_control.pipewire_playback import run_playback


def main(
    journal_db: Path = typer.Option(...), journal_url: str = typer.Option(...),
    session_id: str = typer.Option(...), turn_id: str = typer.Option(...),
    source_event_id: str = typer.Option(...), source_sequence: int = typer.Option(...),
    tau_plan_event_id: str = typer.Option(...), render_event_id: str = typer.Option(...),
    tau_plan_sha256: str = typer.Option(...), tts_text_sha256: str = typer.Option(...),
    audio_sha256: str = typer.Option(...), audio_bytes: int = typer.Option(...),
    sink_node_name: str = typer.Option(...), expected_current_node_id: int = typer.Option(...),
    expected_sink_description: str = typer.Option(...), expected_sink_volume: float = typer.Option(...),
    sink_volume_tolerance: float = typer.Option(0.02), pw_play: str = typer.Option("/usr/bin/pw-play"),
    start_timeout_ms: int = typer.Option(1500), graph_poll_ms: int = typer.Option(20),
    start_confirmations: int = typer.Option(2), duplicate_probe: bool = typer.Option(False),
    output_dir: Path = typer.Option(...),
) -> None:
    kwargs = locals().copy()
    kwargs.pop("duplicate_probe")
    receipt = run_playback(**kwargs)
    if duplicate_probe:
        duplicate = run_playback(**kwargs)
        if not duplicate["idempotent_replay"] or duplicate["process_spawned"]:
            raise typer.Exit(2)
        receipt["duplicate_probe"] = {"idempotent_replay": True, "process_spawned": False}
        (output_dir / "machine-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    typer.echo(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    typer.run(main)
