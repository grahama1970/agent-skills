from pathlib import Path


def test_witness_script_exists():
    assert (Path(__file__).parents[1] / "scripts" / "record_pipewire_playback_witness.py").is_file()
