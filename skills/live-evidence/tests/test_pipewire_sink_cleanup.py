"""PipeWire null-sink cleanup regressions."""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from eval_live_youtube_oracle import destroy_virtual_sink, virtual_sink_node_ids


def test_virtual_sink_node_ids_reads_pw_dump(monkeypatch) -> None:
    dump = [
        {
            "id": 119,
            "type": "PipeWire:Interface:Node",
            "info": {"props": {"node.name": "le-campaign-44397"}},
        },
        {
            "id": 33,
            "type": "PipeWire:Interface:Node",
            "info": {"props": {"node.name": "jabra"}},
        },
    ]

    def fake_run(argv, **kwargs):
        assert argv == ["pw-dump"]
        return SimpleNamespace(stdout=json.dumps(dump))

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert virtual_sink_node_ids("le-campaign-44397") == ["119"]


def test_destroy_virtual_sink_destroys_resolved_node_id(monkeypatch) -> None:
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if argv == ["pw-dump"]:
            return SimpleNamespace(
                stdout=json.dumps(
                    [
                        {
                            "id": 121,
                            "type": "PipeWire:Interface:Node",
                            "info": {"props": {"node.name": "le-eval-sink-123"}},
                        }
                    ]
                )
            )
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    destroy_virtual_sink("le-eval-sink-123")

    assert calls == [["pw-dump"], ["pw-cli", "destroy", "121"]]
