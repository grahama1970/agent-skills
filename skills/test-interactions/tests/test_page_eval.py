"""Focused tests for strict page-eval finding normalization."""

from __future__ import annotations

import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from page_eval import normalize_page_eval_findings, validate_page_eval_finding
from ticket_integration import run_ticket_integration


def _write_fake_ticket(root: Path) -> Path:
    script = root / "fake-ticket.py"
    script.write_text(textwrap.dedent("""\
        #!/usr/bin/env python3
        import json
        import sys

        args = sys.argv[1:]
        if args[:1] == ["lookup"] and "--search" in args:
            print("[]")
            raise SystemExit(0)
        if args[:1] == ["bug"] and "--json" in args:
            print(json.dumps({"title": args[1], "body": args[args.index("--observed") + 1]}))
            raise SystemExit(0)
        raise SystemExit(2)
    """))
    script.chmod(script.stat().st_mode | 0o111)
    return script


class PageEvalTests(unittest.TestCase):
    def test_impeccable_design_findings_are_included_as_advisory_design(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            impeccable = root / "impeccable.json"
            impeccable.write_text(json.dumps({
                "findings": [{
                    "antipattern": "weak_visual_hierarchy",
                    "severity": "medium",
                    "description": "Primary CTA has weak contrast against surrounding content",
                    "file": "index.html",
                    "line": 42,
                }]
            }))
            output = root / "page-eval.jsonl"
            summary = normalize_page_eval_findings(
                repo="grahama1970/agent-skills",
                target="experiments/impeccable",
                route="/",
                viewport="1280x800",
                replay_command="replay",
                output=output,
                impeccable_findings=impeccable,
            )
            rows = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual(summary["counts"]["design"], 1)
            self.assertEqual(rows[0]["finding_type"], "design")
            self.assertEqual(rows[0]["source_tool"], "impeccable")
            self.assertEqual(rows[0]["proof_grade"], "advisory")
            self.assertEqual(rows[0]["deterministic_status"], "")

    def test_disable_impeccable_excludes_design_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            impeccable = root / "impeccable.json"
            impeccable.write_text(json.dumps([{"antipattern": "weak_visual_hierarchy"}]))
            output = root / "page-eval.jsonl"
            summary = normalize_page_eval_findings(
                repo="grahama1970/agent-skills",
                target="experiments/impeccable",
                route="/",
                viewport="1280x800",
                replay_command="replay",
                output=output,
                impeccable_findings=impeccable,
                disable_impeccable=True,
            )
            self.assertEqual(summary["finding_count"], 0)
            self.assertFalse(summary["impeccable_included"])
            self.assertEqual(output.read_text(), "")

    def test_interaction_findings_share_schema_but_keep_deterministic_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            discovery = root / "discovery-findings.jsonl"
            discovery.write_text(json.dumps({
                "schema": "test-interactions.discovery-finding.v1",
                "finding_kind": "qs_action_missing",
                "message": "QID interactive is missing data-qs-action",
                "qid": "hero:cta:primary",
                "selector": "[data-qid='hero:cta:primary']",
                "tag": "button",
                "state_fingerprint": "abc",
            }) + "\n")
            output = root / "page-eval.jsonl"
            normalize_page_eval_findings(
                repo="grahama1970/agent-skills",
                target="experiments/impeccable",
                route="/",
                viewport="1280x800",
                replay_command="replay",
                output=output,
                discovery_findings=discovery,
            )
            row = json.loads(output.read_text().splitlines()[0])
            self.assertEqual(row["finding_type"], "instrumentation")
            self.assertEqual(row["source_tool"], "test-interactions")
            self.assertEqual(row["proof_grade"], "deterministic")
            self.assertEqual(row["deterministic_status"], "FAIL")

    def test_validation_rejects_impeccable_deterministic_status(self):
        item = {
            "schema": "page-eval.finding.v1",
            "finding_id": "page-eval-x",
            "fingerprint": "x",
            "repo": "repo",
            "target": "target",
            "route": "/",
            "viewport": "1280x800",
            "finding_type": "design",
            "evidence_class": "design",
            "proof_grade": "advisory",
            "source_tool": "impeccable",
            "source_path": "impeccable.json",
            "source_index": 0,
            "target_info": {},
            "finding_kind": "contrast",
            "severity": "medium",
            "observed": "observed",
            "expected": "expected",
            "reproduction": "replay",
            "deterministic_status": "FAIL",
            "evidence_paths": [],
            "raw_finding": {},
        }
        ok, errors = validate_page_eval_finding(item)
        self.assertFalse(ok)
        self.assertTrue(any("deterministic PASS/FAIL" in error for error in errors))

    def test_ticket_preview_accepts_page_eval_design_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            impeccable = root / "impeccable.json"
            impeccable.write_text(json.dumps([{"antipattern": "weak_visual_hierarchy", "description": "CTA lacks hierarchy"}]))
            page_eval = root / "page-eval.jsonl"
            normalize_page_eval_findings(
                repo="grahama1970/agent-skills",
                target="experiments/impeccable",
                route="/",
                viewport="1280x800",
                replay_command="replay",
                output=page_eval,
                impeccable_findings=impeccable,
            )
            result = run_ticket_integration(
                repo="grahama1970/agent-skills",
                target="experiments/impeccable",
                policy="preview",
                output_dir=root / "tickets",
                ticket_skill=_write_fake_ticket(root),
                replay_command="replay",
                page_eval_findings=page_eval,
            )
            self.assertEqual(result["candidate_count"], 1)
            self.assertEqual(result["preview_count"], 1)
            candidate = result["previews"][0]["candidate"]
            self.assertEqual(candidate["evidence_class"], "design")
            self.assertEqual(candidate["proof_grade"], "advisory")
            self.assertEqual(candidate["source_tool"], "impeccable")


if __name__ == "__main__":
    unittest.main()
