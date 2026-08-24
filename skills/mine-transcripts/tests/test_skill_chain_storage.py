import json
from pathlib import Path

from mine_transcripts import _chain_task_text, _store_mined_chains_to_typed_memory


def _fake_memory_run(path: Path) -> Path:
    recorder = path / "calls.jsonl"
    script = path / "memory-run.sh"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "with open(os.environ['CALLS_JSONL'], 'a', encoding='utf-8') as fh:\n"
        "    fh.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def _read_calls(path: Path) -> list[list[str]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_mined_chains_store_as_typed_skill_chains(monkeypatch, tmp_path):
    memory_run = _fake_memory_run(tmp_path)
    calls_path = tmp_path / "calls.jsonl"
    monkeypatch.setenv("CALLS_JSONL", str(calls_path))

    stored = _store_mined_chains_to_typed_memory(
        [
            {
                "request": "Fix the memory pipeline without legacy lesson writes",
                "chain": ["/memory", "/checkpoint", "/recommend-skill-chain"],
                "project": "memory",
                "source": "session.jsonl",
            }
        ],
        memory_run=memory_run,
    )

    assert stored == 1
    calls = _read_calls(calls_path)
    assert calls == [
        [
            "chain-learn",
            "--skills",
            "memory,checkpoint,recommend-skill-chain",
            "--task",
            "Fix the memory pipeline without legacy lesson writes (Project: memory; Source: session.jsonl)",
            "--source",
            "transcript",
        ]
    ]
    assert all(call[0] != "learn" for call in calls)


def test_mined_chain_storage_skips_short_chains(monkeypatch, tmp_path):
    memory_run = _fake_memory_run(tmp_path)
    calls_path = tmp_path / "calls.jsonl"
    monkeypatch.setenv("CALLS_JSONL", str(calls_path))

    stored = _store_mined_chains_to_typed_memory(
        [{"request": "Only one skill", "chain": ["/memory"], "project": "memory"}],
        memory_run=memory_run,
    )

    assert stored == 0
    assert not calls_path.exists()


def test_chain_task_text_is_bounded():
    task = _chain_task_text({
        "request": "x" * 600,
        "project": "memory",
        "source": "source.jsonl",
    })

    assert len(task) <= 500
    assert "Project: memory" in task
