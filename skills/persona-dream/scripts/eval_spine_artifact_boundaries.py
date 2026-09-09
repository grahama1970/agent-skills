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
        path = next((p for p in (source / name, source / "voice_weights" / name) if p.is_file()), source / name)
        errors = validate_artifact(path, require_schema=True)
        if errors:
            raise SystemExit(f"production positive control rejected: {name}: {errors}")
        payloads[name] = path.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="persona-dream-boundary-eval-") as tmp:
        tmp = Path(tmp)

        DEFAULT_SIDE = {
            "JOURNAL_SPOKEN_TEXT_RECEIPT.json": ("journal_spoken.txt", "dream_journal.v1.json"),
            "JOURNAL_AUDIO_RECEIPT.json": ("journal_spoken.txt",),
            "dynamic_conversation_receipt.v1.json": ("conversation.jsonl", "journal_spoken.txt"),
            "conversation.jsonl": ("journal_spoken.txt",),
        }

        def invoke(label, filename, text, expected_error=None, produces="", side=None, extra=None):
            directory = tmp / label / source.name
            directory.mkdir(parents=True)
            if filename in {"conversation.jsonl", "JOURNAL_AUDIO_RECEIPT.json", "dynamic_conversation_receipt.v1.json"}:
                for audio in source.glob("*.wav"):
                    shutil.copyfile(audio, directory / audio.name)
            for name in (DEFAULT_SIDE.get(filename, ()) if side is None else side):
                shutil.copyfile(source / name, directory / name)
            for name, content in (extra or {}).items():
                (directory / name).write_text(content, encoding="utf-8")
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

        # Cross-artifact lineage: individually valid receipts must bind to the
        # ACTUAL cycle bytes they claim to describe (WebGPT review P0-3).
        invoke("valid-spoken-receipt", "JOURNAL_SPOKEN_TEXT_RECEIPT.json", payloads["JOURNAL_SPOKEN_TEXT_RECEIPT.json"])
        invoke("valid-audio-receipt", "JOURNAL_AUDIO_RECEIPT.json", payloads["JOURNAL_AUDIO_RECEIPT.json"])
        invoke("valid-conversation-receipt", "dynamic_conversation_receipt.v1.json", payloads["dynamic_conversation_receipt.v1.json"])
        invoke("spoken-receipt-target-missing", "JOURNAL_SPOKEN_TEXT_RECEIPT.json",
               payloads["JOURNAL_SPOKEN_TEXT_RECEIPT.json"], "artifact_lineage_target_missing", side=())
        forged = json.loads(payloads["JOURNAL_SPOKEN_TEXT_RECEIPT.json"])
        forged["spoken_text_sha256"] = "sha256:" + "0" * 64
        invoke("spoken-receipt-forged-digest", "JOURNAL_SPOKEN_TEXT_RECEIPT.json",
               json.dumps(forged), "artifact_lineage_hash_mismatch")
        fake = b"FAKE-BYTES-NOT-A-RIFF-WAVE-CONTAINER"
        not_wav = json.loads(payloads["JOURNAL_AUDIO_RECEIPT.json"])
        not_wav.update(audio="journal.wav", audio_bytes=len(fake),
                       audio_sha256="sha256:" + __import__("hashlib").sha256(fake).hexdigest())
        invoke("audio-receipt-not-wav", "JOURNAL_AUDIO_RECEIPT.json", json.dumps(not_wav),
               "artifact_audio_not_wav", extra={"journal.wav": fake.decode()})
        detached = json.loads(payloads["JOURNAL_AUDIO_RECEIPT.json"])
        detached["source_spoken_text_sha256"] = "sha256:" + "0" * 64
        invoke("audio-receipt-detached-source", "JOURNAL_AUDIO_RECEIPT.json",
               json.dumps(detached), "artifact_lineage_hash_mismatch")
        transcript_rows = [line for line in payloads["conversation.jsonl"].splitlines() if line.strip()]
        invoke("conversation-receipt-transcript-mismatch", "dynamic_conversation_receipt.v1.json",
               payloads["dynamic_conversation_receipt.v1.json"], "artifact_lineage_count_mismatch",
               side=("journal_spoken.txt",), extra={"conversation.jsonl": "\n".join(transcript_rows[:-1]) + "\n"})
        rebound = json.loads(transcript_rows[0])
        rebound["journal_spoken_sha256"] = "sha256:" + "0" * 64
        invoke("jsonl-turn-foreign-journal", "conversation.jsonl",
               json.dumps(rebound) + "\n", "artifact_lineage_hash_mismatch")

        # Reuse the actual upstream receipt; corrupt only temporary copies of it.
        upstream_path = Path('/mnt/storage12tb/skills/persona-dream/outputs/full-persona-dream-auto-20260909T130904Z/dag_receipts/dream_cycle.json')
        upstream = json.loads(upstream_path.read_text())
        for label in ['valid-upstream', 'tampered-upstream-hash', 'contradictory-upstream', 'malformed-upstream-ref', 'wrong-producer-owner']:
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
                       '--input-owner',
                       'phase14_tom.json=' + ('journal_entry' if label == 'wrong-producer-owner' else str(upstream['node_id'])),
                       '--step-arg=' + str(ROOT / 'fixtures/agentic_eval.json'), '--step-arg=--json']
            proc = subprocess.run(command, text=True, capture_output=True, timeout=120)
            receipt = json.loads(receipt_path.read_text())
            assert proc.returncode == (0 if label == 'valid-upstream' else 1), (label, proc.stderr)
            if label != 'valid-upstream':
                assert receipt['commands_run'][0]['exit_code'] is None
                assert receipt['triage_errors']
            rows.append({'case': label, 'command': command, 'exit_code': proc.returncode, 'receipt': receipt})

        # Real DAG compiler must bind every input to its producing node receipt
        # AND refuse a cycle id that would move the trusted artifact root.
        spec_path = tmp / "compiled.json"
        command = [sys.executable, str(ROOT / "scripts/build_dream_dag.py"),
                   "--run-dir", str(tmp / "dag"), "--cycle-id", source.name, "--out", str(spec_path)]
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
        spec = json.loads(spec_path.read_text())
        assert all("--input-receipt" in node["command"] for node in spec["nodes"][1:])
        assert all("--input-owner" in node["command"] for node in spec["nodes"][1:])
        assert "--input-receipt" not in spec["nodes"][0]["command"]
        rows.append({"case": "compiler-binds-upstream-receipts", "command": command, "exit_code": 0})
        for label, bad_cycle in (("compiler-refuses-absolute-cycle-id", str(tmp / "escaped")),
                                 ("compiler-refuses-traversal-cycle-id", "../escaped")):
            command = [sys.executable, str(ROOT / "scripts/build_dream_dag.py"),
                       "--run-dir", str(tmp / "dag2"), "--cycle-id", bad_cycle, "--out", str(tmp / "bad.json")]
            proc = subprocess.run(command, capture_output=True, text=True, timeout=30)
            assert proc.returncode != 0 and "BLOCKED_UNSAFE_CYCLE_ID" in proc.stderr + proc.stdout, (label, proc.stdout, proc.stderr)
            rows.append({"case": label, "command": command, "exit_code": proc.returncode})

        # Direct spine producer entrypoints are refused outside the executor.
        proc = subprocess.run(["bash", str(ROOT / "run.sh"), "write-dream-journal", "--cycle", "x"],
                              capture_output=True, text=True, timeout=60,
                              env={k: v for k, v in __import__("os").environ.items()
                                   if k not in {"PERSONA_DREAM_STEP_EXECUTOR", "PERSONA_DREAM_ALLOW_DIRECT"}})
        assert proc.returncode == 3 and "BLOCKED_DIRECT_SPINE_ENTRYPOINT" in proc.stderr, (proc.returncode, proc.stderr)
        rows.append({"case": "direct-spine-entrypoint-refused", "exit_code": proc.returncode,
                     "stderr": proc.stderr[-400:]})

        command = [sys.executable, "-c", """
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path('scripts').resolve()))
import pydantic_step_gate as g
schema = json.load(open('schemas/persona_journal.v1.schema.json'))
g.GENERATED_MODEL_LOAD_FAILURES['persona_journal_v1_schema'] = 'SyntaxError: simulated import failure'
errors = g.validate_payload(schema, {'schema': 'persona_dream.persona_journal.v1', 'journal': 'x'})
assert errors and errors[0]['type'] == 'generated_model_load_failed', errors
print(errors[0]['type'])
"""]
        proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0 and "generated_model_load_failed" in proc.stdout, (proc.stdout, proc.stderr)
        rows.append({"case": "generated-model-import-failure-fails-closed", "command": command,
                     "exit_code": proc.returncode, "stdout": proc.stdout.strip()})

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
