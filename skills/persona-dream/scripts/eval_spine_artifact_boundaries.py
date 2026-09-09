#!/usr/bin/env python3
"""Exercise the real step CLI with retained production artifacts and corruptions.

No mocked subprocess, provider, or alternate gate. Positive evidence is an
existing live cycle, checked before faults are applied to temporary copies.
This proves artifact admission/refusal, not fresh model/media quality.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from pydantic_step_gate import validate_artifact
from spine_artifact_models import SPINE_ARTIFACT_MODELS

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production-cycle", type=Path,
                        default=ROOT / "reports/goal_v3/cycles/cycle_20260909T130904Z")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = args.production_cycle.resolve()
    rows = []
    payloads = {}
    for name in SPINE_ARTIFACT_MODELS:
        path = source / name
        errors = validate_artifact(path, require_schema=True)
        if errors:
            raise SystemExit(f"production positive control rejected: {name}: {errors}")
        payloads[name] = path.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="persona-dream-boundary-eval-") as tmp:
        tmp = Path(tmp)

        def invoke(label, filename, text, expected_error=None, produces=""):
            directory = tmp / label / source.name
            directory.mkdir(parents=True)
            if filename in {"conversation.jsonl", "JOURNAL_AUDIO_RECEIPT.json", "dynamic_conversation_receipt.v1.json"}:
                for audio in source.glob("*.wav"):
                    shutil.copyfile(audio, directory / audio.name)
            path = directory / filename
            path.write_text(text, encoding="utf-8")
            receipt_path = directory / "node.json"
            command = [sys.executable, str(ROOT / "scripts/dag_step.py"),
                       "--node-id", "boundary-eval", "--command", "check-agentic-eval-no-pytest",
                       "--receipt", str(receipt_path), "--run-dir", str(directory),
                       "--consumes", filename, "--produces", produces,
                       "--step-arg=" + str(ROOT / "fixtures/agentic_eval.json"), "--step-arg=--json"]
            proc = subprocess.run(command, text=True, capture_output=True, timeout=120)
            receipt = json.loads(receipt_path.read_text())
            expected_exit = 1 if expected_error else 0
            assert proc.returncode == expected_exit, (label, proc.returncode, proc.stdout, proc.stderr)
            assert receipt["status"] == ("BLOCKED" if expected_error else "PASS"), (label, receipt)
            if expected_error:
                assert expected_error in json.dumps(receipt), (label, receipt)
                assert all(row["code"] and row["cause"] and row["next_command"] for row in receipt["triage_errors"])
                if not produces:
                    assert receipt["commands_run"][0]["exit_code"] is None, (label, "consumer ran")
            else:
                assert receipt["commands_run"][0]["exit_code"] == 0
            rows.append({"case": label, "command": command, "exit_code": proc.returncode,
                         "receipt": receipt, "stdout": proc.stdout, "stderr": proc.stderr})

        invoke("valid-production-input", "phase14_tom.json", payloads["phase14_tom.json"])
        invoke("missing-fields", "phase14_tom.json", json.dumps({"schema": "persona_dream.tom_validation_receipt.v1", "canonical_memory_write_allowed": True}), "pydantic_gate_input")
        invoke("unknown-schema", "input.json", '{"schema":"persona_dream.unregistered.v999"}', "artifact_schema_unknown")
        invoke("non-string-schema", "input.json", '{"schema":[]}', "pydantic_gate_input")
        invoke("duplicate-status", "input.json", '{"schema":"tau.generic_dag_node_receipt.v1","status":"BLOCKED","status":"PASS"}', "duplicate JSON key")
        invoke("malformed-jsonl", "conversation.jsonl", '{not json}\n', "artifact_unreadable")
        invoke("empty-jsonl", "conversation.jsonl", '\n', "artifact_empty")
        invoke("valid-jsonl", "conversation.jsonl", payloads["conversation.jsonl"])
        invoke("schema-spoof", "phase14_tom.json", payloads["storyboard_plan.json"], "literal_error")
        wrong_cycle = json.loads(payloads["phase14_tom.json"])
        wrong_cycle["revision_id"] = "some_other_cycle"
        invoke("wrong-cycle", "phase14_tom.json", json.dumps(wrong_cycle), "artifact_cycle_mismatch")
        wrong_journal = json.loads(payloads["dream_journal.v1.json"])
        wrong_journal["session_mood"]["source_cycle"] = "some_other_cycle"
        invoke("mixed-journal-lineage", "dream_journal.v1.json", json.dumps(wrong_journal), "value_error")
        wrong_audio = json.loads(payloads["JOURNAL_AUDIO_RECEIPT.json"])
        wrong_audio["failed_gates"] = ["audio_missing"]
        invoke("false-pass-audio", "JOURNAL_AUDIO_RECEIPT.json", json.dumps(wrong_audio), "too_long")
        wrong_audio = json.loads(payloads["JOURNAL_AUDIO_RECEIPT.json"])
        wrong_audio["audio"] = 'journal.wav'
        wrong_audio["audio_sha256"] = 'sha256:' + '0' * 64
        invoke("false-audio-digest", "JOURNAL_AUDIO_RECEIPT.json", json.dumps(wrong_audio), "artifact_audio_hash_mismatch")
        wrong_count = json.loads(payloads["dynamic_conversation_receipt.v1.json"])
        wrong_count["turn_count"] += 2
        invoke("false-turn-count", "dynamic_conversation_receipt.v1.json", json.dumps(wrong_count), "value_error")
        invoke("stale-output", "storyboard_plan.json", payloads["storyboard_plan.json"],
               "not produced by this execution", produces="storyboard_plan.json")
        invoke("empty-output", "empty.txt", "", "artifact is empty", produces="empty.txt")
        invoke("path-escape", "../escape.json", payloads["storyboard_plan.json"], "artifact_path_escape")

        # Reuse the actual upstream receipt; corrupt only temporary copies of it.
        upstream_path = Path('/mnt/storage12tb/skills/persona-dream/outputs/full-persona-dream-auto-20260909T130904Z/dag_receipts/dream_cycle.json')
        upstream = json.loads(upstream_path.read_text())
        for label in ['valid-upstream', 'tampered-upstream-hash', 'contradictory-upstream', 'malformed-upstream-ref']:
            document = json.loads(json.dumps(upstream))
            if label == 'tampered-upstream-hash':
                for artifact in document['artifacts']:
                    if Path(artifact['path']).name == 'phase14_tom.json':
                        artifact['sha256'] = 'sha256:' + '0' * 64
            if label == 'contradictory-upstream':
                document['verdict'] = 'BLOCKED'
            if label == 'malformed-upstream-ref':
                document['artifacts'][0]['path'] = ['invalid path']
            input_receipt = tmp / (label + '.json')
            input_receipt.write_text(json.dumps(document))
            receipt_path = tmp / (label + '-result.json')
            command = [sys.executable, str(ROOT / 'scripts/dag_step.py'), '--node-id', 'upstream-eval',
                       '--command', 'check-agentic-eval-no-pytest', '--receipt', str(receipt_path),
                       '--run-dir', str(source), '--consumes', 'phase14_tom.json',
                       '--input-receipt', str(input_receipt), '--goal-hash', upstream['goal_hash'],
                       '--step-arg=' + str(ROOT / 'fixtures/agentic_eval.json'), '--step-arg=--json']
            proc = subprocess.run(command, text=True, capture_output=True, timeout=120)
            receipt = json.loads(receipt_path.read_text())
            assert proc.returncode == (0 if label == 'valid-upstream' else 1), (label, proc.stderr)
            if label != 'valid-upstream':
                assert receipt['commands_run'][0]['exit_code'] is None
                assert receipt['triage_errors']
            rows.append({'case': label, 'command': command, 'exit_code': proc.returncode, 'receipt': receipt})

        # Real DAG compiler must bind every input to its producing node receipt.
        spec_path = tmp / "compiled.json"
        command = [sys.executable, str(ROOT / "scripts/build_dream_dag.py"),
                   "--run-dir", str(tmp / "dag"), "--cycle-id", source.name, "--out", str(spec_path)]
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
        spec = json.loads(spec_path.read_text())
        assert all("--input-receipt" in node["command"] for node in spec["nodes"][1:])
        assert "--input-receipt" not in spec["nodes"][0]["command"]
        rows.append({"case": "compiler-binds-upstream-receipts", "command": command, "exit_code": 0})

    report = {"schema": "persona_dream.spine_artifact_boundary_eval.v1", "status": "PASS",
              "production_cycle": str(source), "positive_artifact_count": len(payloads), "cases": rows,
              "mocked": False, "live": False, "fault_injected": True,
              "proof_boundary": "Real production artifacts and actual dag_step/run.sh/triage CLI; controlled corruptions, no fresh provider calls."}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print("SPINE_ARTIFACT_BOUNDARIES_OK", len(rows), "checks", len(payloads), "production artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
