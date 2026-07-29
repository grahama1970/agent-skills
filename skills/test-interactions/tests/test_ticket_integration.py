"""Focused tests for preview-first ticket integration."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ticket_integration import (
    apply_policy,
    candidates_from_results,
    run_ticket_integration,
    stable_fingerprint,
)


def _write_fake_ticket(root: Path, *, duplicate: bool = False, bad_readback: bool = False) -> Path:
    script = root / "fake-ticket.py"
    state = root / "fake-ticket-state.txt"
    issue_body = "missing required content" if bad_readback else (
        "Target skills/test-interactions backend_python_or_skill_runtime coder "
        "Replay command Required proof fingerprint-placeholder"
    )
    script.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env python3
        import json
        import sys

        args = sys.argv[1:]
        if args[:1] == ["lookup"] and "--search" in args:
            if {str(duplicate)}:
                fp = args[args.index("--search") + 1]
                print(json.dumps([{{"number": 2222, "url": "https://github.com/o/r/issues/2222", "body": fp}}]))
            else:
                print("[]")
            raise SystemExit(0)
        if args[:1] == ["lookup"] and "--issue" in args:
            fp = ""
            try:
                fp = open({str(state)!r}).read().strip()
            except OSError:
                pass
            body = {issue_body!r}.replace("fingerprint-placeholder", fp)
            print(json.dumps({{"number": int(args[args.index("--issue") + 1]), "state": "OPEN", "url": "https://github.com/o/r/issues/3333", "body": body}}))
            raise SystemExit(0)
        if args[:1] == ["bug"]:
            observed = args[args.index("--observed") + 1]
            fp = observed.split("Source finding fingerprint: ", 1)[1].split("\\n", 1)[0]
            body = {issue_body!r}.replace("fingerprint-placeholder", fp)
            if "--json" in args:
                print(json.dumps({{"title": args[1], "body": body, "labels": ["type:bug"]}}))
            elif "--apply" in args:
                open({str(state)!r}, "w").write(fp)
                print("https://github.com/o/r/issues/3333")
            raise SystemExit(0)
        raise SystemExit(2)
    """))
    script.chmod(script.stat().st_mode | 0o111)
    return script


class TicketIntegrationTests(unittest.TestCase):
    def test_fingerprint_is_stable_across_runs(self):
        kwargs = {
            "repo": "grahama1970/agent-skills",
            "target": "skills/test-interactions",
            "surface": "main",
            "identity": "fixture:no-action",
            "finding_kind": "qs_action_missing",
            "expected_outcome": "Live DOM should satisfy discovery invariant: qs_action_missing",
        }
        self.assertEqual(stable_fingerprint(**kwargs), stable_fingerprint(**kwargs))

    def test_deterministic_only_excludes_visual_candidate(self):
        candidates = apply_policy([
            type("C", (), {"deterministic": True, "visual": False, "confidence": None, "report_only_reason": "", "eligible": False})(),
            type("C", (), {"deterministic": False, "visual": True, "confidence": 0.99, "report_only_reason": "", "eligible": False})(),
        ], "deterministic-only", threshold=0.85)
        self.assertTrue(candidates[0].eligible)
        self.assertFalse(candidates[1].eligible)

    def test_high_confidence_excludes_low_confidence_visual_candidate(self):
        candidates = apply_policy([
            type("C", (), {"deterministic": False, "visual": True, "confidence": 0.95, "report_only_reason": "", "eligible": False})(),
            type("C", (), {"deterministic": False, "visual": True, "confidence": 0.5, "report_only_reason": "", "eligible": False})(),
        ], "high-confidence", threshold=0.85)
        self.assertTrue(candidates[0].eligible)
        self.assertFalse(candidates[1].eligible)

    def test_preview_mode_performs_no_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results.json"
            results.write_text(json.dumps({
                "interactions": [{
                    "status": "FAIL",
                    "surface": "main",
                    "element": "fixture:no-action",
                    "evidence": "assertion failed",
                    "screenshot": str(root / "shot.png"),
                }]
            }))
            ticket = _write_fake_ticket(root)
            out = root / "out"
            result = run_ticket_integration(
                repo="grahama1970/agent-skills",
                target="skills/test-interactions",
                policy="preview",
                output_dir=out,
                ticket_skill=ticket,
                replay_command="skills/test-interactions/run.sh run --manifest fixture.json",
                results=results,
            )
            self.assertEqual(result["preview_count"], 1)
            self.assertEqual(result["created_count"], 0)
            self.assertTrue((out / "ticket-previews.json").exists())

    def test_duplicate_suppresses_preview_and_proposes_comment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results.json"
            results.write_text(json.dumps({"interactions": [{"status": "FAIL", "surface": "main", "element": "fixture:dup", "evidence": "failed"}]}))
            result = run_ticket_integration(
                repo="grahama1970/agent-skills",
                target="skills/test-interactions",
                policy="preview",
                output_dir=root / "out",
                ticket_skill=_write_fake_ticket(root, duplicate=True),
                replay_command="replay",
                results=results,
            )
            self.assertEqual(result["preview_count"], 0)
            self.assertEqual(result["duplicate_count"], 1)

    def test_missing_ticket_runtime_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results.json"
            results.write_text(json.dumps({"interactions": [{"status": "FAIL", "surface": "main", "element": "fixture:missing", "evidence": "failed"}]}))
            with self.assertRaises(RuntimeError):
                run_ticket_integration(
                    repo="grahama1970/agent-skills",
                    target="skills/test-interactions",
                    policy="preview",
                    output_dir=root / "out",
                    ticket_skill=root / "missing-ticket",
                    replay_command="replay",
                    results=results,
                )

    def test_apply_confirmed_creates_one_and_verifies_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results.json"
            results.write_text(json.dumps({"interactions": [{"status": "FAIL", "surface": "main", "element": "fixture:apply", "evidence": "failed"}]}))
            result = run_ticket_integration(
                repo="grahama1970/agent-skills",
                target="skills/test-interactions",
                policy="apply-confirmed",
                output_dir=root / "out",
                ticket_skill=_write_fake_ticket(root),
                replay_command="Replay command",
                results=results,
            )
            self.assertEqual(result["created_count"], 1)
            self.assertTrue(result["created"][0]["readback"]["verified"])

    def test_failed_readback_refuses_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results.json"
            results.write_text(json.dumps({"interactions": [{"status": "FAIL", "surface": "main", "element": "fixture:bad-readback", "evidence": "failed"}]}))
            with self.assertRaises(RuntimeError):
                run_ticket_integration(
                    repo="grahama1970/agent-skills",
                    target="skills/test-interactions",
                    policy="apply-confirmed",
                    output_dir=root / "out",
                    ticket_skill=_write_fake_ticket(root, bad_readback=True),
                    replay_command="Replay command",
                    results=results,
                )


if __name__ == "__main__":
    unittest.main()
