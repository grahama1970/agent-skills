"""Regression tests for /hack final proof-candidate closure reports."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def load_script(name: str):
    path = SCRIPTS_DIR / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


final_report = load_script("generate_final_report.py")
final_infographic = load_script("generate_final_infographic.py")
package_review = load_script("package_final_review.py")


class FinalReportClosureTests(unittest.TestCase):
    def _write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n")

    def _write_jsonl(self, path: Path, rows: list[dict[str, object]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))

    def _make_run_root(self, tmp: str) -> Path:
        root = Path(tmp) / "run"
        evolve = root / "evolve-campaign-20260512T000000Z-127.0.0.1-18789"
        chaos = root / "chaos-campaign-20260512T000000Z-127.0.0.1-18789"
        session = root / "session-openclaw"

        seed_payload = root / "seed.json"
        self._write_json(
            seed_payload,
            {
                "source_urls": ["https://example.invalid/dogpile"],
                "artifact_paths": ["session/reports/semgrep.json"],
                "research_confidence": {"overall": "medium", "reason": "fixture"},
                "recommended_fuzzing_lanes": [
                    {
                        "lane_id": "websocket_control",
                        "supporting_sources": [
                            {
                                "source_type": "artifact_path",
                                "source": "session/reports/semgrep.json",
                                "quote_or_fact": "WebSocket control hook /hooks/wake observed.",
                            }
                        ],
                        "false_positive_filters": [],
                    }
                ],
            },
        )
        self._write_json(
            evolve / "strategies.seed.json",
            {
                "seed_source": "validated_seed",
                "seed_validation": {
                    "valid": True,
                    "path": str(seed_payload),
                    "seed_sha256": "abc123",
                },
                "research_insights": [],
            },
        )
        self._write_json(
            evolve / "summary.json",
            {
                "target": "http://127.0.0.1:18789",
                "attempts": 2,
                "anomalies": 1,
                "promotion_tasks": 1,
                "proof_status": "not_proven",
            },
        )
        self._write_json(chaos / "summary.json", {"attempts": 1, "anomalies": 0})
        self._write_json(evolve / "loop-contract.json", {"loop": "fixture"})
        self._write_json(evolve / "next-dogpile-seed.json", {"promotion_tasks": [{"id": "p1"}]})
        self._write_json(evolve / "generation-000.json", {"generation": 0, "attempts": 1, "anomalies": 1, "best_score": 9.5})
        self._write_json(evolve / "promotion-tasks" / "task-001.json", {"id": "task-001"})
        self._write_jsonl(
            evolve / "attempts.jsonl",
            [
                {
                    "attempt": "a1",
                    "generation": 0,
                    "classification": "websocket",
                    "gene": {
                        "source": "websocket_control",
                        "transport": "websocket",
                        "path": "/hooks/wake",
                        "gene_id": "seed-003-websocket_control-0",
                    },
                }
            ],
        )
        self._write_jsonl(
            evolve / "anomalies.jsonl",
            [
                {
                    "attempt": "a1",
                    "generation": 0,
                    "score": 9.5,
                    "anomaly": "unauthenticated-websocket-upgrade",
                    "gene": {
                        "path": "/hooks/wake",
                        "gene_id": "seed-003-websocket_control-0",
                        "header_variant": "null-origin",
                        "mutation": "baseline",
                        "lineage": ["seed-003"],
                    },
                    "result": {"status_line": "HTTP/1.1 101 Switching Protocols"},
                }
            ],
        )
        self._write_json(
            evolve / "proof-candidates" / "hooks-wake-websocket-repro.json",
            {
                "accepted_runs": 15,
                "total_runs": 15,
                "pass": True,
                "runs": [{"status_line": "HTTP/1.1 101 Switching Protocols"}],
            },
        )

        (session / "logs").mkdir(parents=True)
        (session / "logs" / "target-head.log").write_text("## stdout\n8aa7b7a4ca177752f9b9ddc93494f03f1d8c24b9\n\n## stderr\n\n")
        (session / "logs" / "target-origin.log").write_text("## stdout\nhttps://github.com/openclaw/openclaw.git\n\n## stderr\n\n")
        self._write_json(session / "reports" / "target-launch-plan.json", {"target_url": "http://127.0.0.1:18789"})
        (session / "reports" / "HACK_REPORT.md").write_text("# report\n")
        (session / "reports" / "semgrep.json").write_text("{}\n")
        self._write_json(
            root / "session-audit-assessment.json",
            {
                "status": "ran",
                "session_dir": str(session),
                "has_hack_report": True,
                "has_semgrep": True,
                "has_launch_plan": True,
            },
        )
        self._write_json(
            root / "OPENCLAW_PREFLIGHT.json",
            {
                "status": "ready",
                "target": "http://127.0.0.1:18789",
                "repo": str(session / "target" / "repo"),
                "commit": "ERROR:CalledProcessError: bad git state",
                "branch": "ERROR:CalledProcessError: bad git state",
                "origin": "ERROR:CalledProcessError: bad git state",
                "docker_version": "28.2.2",
                "docker_images_digest_listing": ["hack-session-scanner:test <none> deadbeef"],
                "docker_image_digest_captured": False,
                "provenance_complete": False,
            },
        )
        self._write_json(
            root / "CLOSURE_VERDICT.json",
            {
                "status": "closed_with_patch_pending_allowed",
                "green_allowed": True,
                "proof_candidate_reproduced": True,
                "verified_fixed": False,
                "verification_status": "blocked_patch_not_applied",
                "provenance_complete": False,
            },
        )
        (root / "battle-command.log").write_text(
            "Memory skill not available\nDogpile skill not available\nBattle ending: Null production (no findings for 3 rounds)\nFindings: 0\n"
        )
        self._write_json(
            root / "battle-mode-assessment.json",
            {
                "status": "ran_with_artifacts",
                "battle_files": [str(root / "battle-command.log")],
                "zero_finding_is_not_success": True,
            },
        )
        self._write_json(
            root / "openclaw-hooks-wake-patch-objective.json",
            {
                "finding": "unauthenticated WebSocket upgrade on /hooks/wake",
                "patch_status": "blocked_patch_not_applied",
                "required_fix_contract": "disallowed handshakes must not return HTTP 101",
            },
        )
        self._write_json(root / "focused-repro-assessment.json", {"accepted_runs": 15, "total_runs": 15, "pass": True})
        return root

    def test_final_report_normalizes_round4_closure_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_run_root(tmp)
            report_json, report_markdown = final_report.build_report(root)
            html = final_infographic.build_html(root)

        serialized = json.dumps(report_json)
        self.assertEqual(report_json["status"], "proof_candidate_reproduced_patch_pending")
        self.assertNotIn("green_allowed", serialized)
        self.assertNotEqual(report_json["status"], "unknown")
        self.assertNotIn("Status: `unknown`", report_markdown)
        self.assertNotIn("RUN STATUS</span><span class=\"v\">unknown", html)
        self.assertTrue(report_json["patch_pending"])
        self.assertFalse(report_json["verified_fixed"])
        self.assertEqual(report_json["verification_status"], "blocked_patch_not_applied")
        self.assertIn("proof_candidate_reproduced_patch_pending", report_markdown)
        self.assertIn("proof_candidate_reproduced_patch_pending", html)
        self.assertIn("Verified fixed: `false`", report_markdown)
        self.assertIn("blocked_patch_not_applied", html)
        self.assertFalse(report_json["provenance_complete"])
        self.assertFalse(report_json["mode_evidence"]["preflight"]["provenance_complete"])
        self.assertFalse(report_json["mode_evidence"]["preflight"]["docker_image_digest_captured"])
        self.assertEqual(report_json["mode_evidence"]["preflight"]["commit"], "8aa7b7a4ca177752f9b9ddc93494f03f1d8c24b9")
        self.assertNotIn("ERROR:CalledProcessError", serialized)
        self.assertNotIn("report exists `None`", report_markdown)
        self.assertNotIn("Semgrep exists `None`", report_markdown)
        self.assertIn("memory_skill_unavailable", report_markdown)
        self.assertIn("dogpile_skill_unavailable", report_markdown)
        self.assertIn("null_production_no_findings", report_markdown)
        self.assertIn("zero_findings_not_success", report_markdown)
        self.assertIn("memory_skill_unavailable", report_json["mode_evidence"]["battle"]["limitations"])
        self.assertIn("dogpile_skill_unavailable", report_json["mode_evidence"]["battle"]["limitations"])
        self.assertIn("null_production_no_findings", report_json["mode_evidence"]["battle"]["limitations"])
        self.assertIn("zero_findings_not_success", report_json["mode_evidence"]["battle"]["limitations"])
        self.assertIn("not captured", html)
        self.assertNotIn("Image digest</span><span class=\"v\">captured", html)

    def test_review_package_contains_raw_ledgers_and_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_run_root(tmp)
            report_json, report_markdown = final_report.build_report(root)
            (root / "HACK_FINAL_REPORT.json").write_text(json.dumps(report_json, indent=2) + "\n")
            (root / "HACK_FINAL_REPORT.md").write_text(report_markdown)
            (root / "HACK_FINAL_REPORT.html").write_text(final_infographic.build_html(root))
            output = root / "package.zip"
            package_review.main_for_test(root, output) if hasattr(package_review, "main_for_test") else None
            if not output.exists():
                import sys

                old_argv = sys.argv
                try:
                    sys.argv = ["package_final_review.py", str(root), "--output", str(output)]
                    package_review.main()
                finally:
                    sys.argv = old_argv

            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                manifest = json.loads(archive.read("MANIFEST.json"))

        required = {
            "raw-ledgers/attempts.jsonl",
            "raw-ledgers/anomalies.jsonl",
            "raw-ledgers/generation-000.json",
            "raw-ledgers/proof-candidates/hooks-wake-websocket-repro.json",
            "raw-ledgers/next-dogpile-seed.json",
            "raw-ledgers/promotion-tasks/task-001.json",
            "run-artifacts/openclaw-hooks-wake-patch-objective.json",
            "run-artifacts/post-patch-verification.MISSING.json",
        }
        self.assertTrue(required.issubset(names))
        by_path = {entry["path"]: entry for entry in manifest["entries"]}
        self.assertTrue(by_path["run-artifacts/openclaw-hooks-wake-patch-objective.json"]["exists"])
        self.assertIsNotNone(by_path["run-artifacts/openclaw-hooks-wake-patch-objective.json"]["sha256"])
        self.assertFalse(by_path["run-artifacts/post-patch-verification.MISSING.json"]["exists"])
        self.assertIsNotNone(by_path["run-artifacts/post-patch-verification.MISSING.json"]["sha256"])

    def test_review_package_contains_product_patch_handoff_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_run_root(tmp)
            patch_dir = root / "openclaw-product-patch"
            patch_dir.mkdir()
            (patch_dir / "0001-fix-gateway-reject-hook-websocket-upgrades.patch").write_text("patch\n")
            (patch_dir / "commit-summary.txt").write_text("summary\n")
            report_json, report_markdown = final_report.build_report(root)
            (root / "HACK_FINAL_REPORT.json").write_text(json.dumps(report_json, indent=2) + "\n")
            (root / "HACK_FINAL_REPORT.md").write_text(report_markdown)
            (root / "HACK_FINAL_REPORT.html").write_text(final_infographic.build_html(root))
            output = root / "package.zip"
            package_review.main_for_test(root, output)

            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                manifest = json.loads(archive.read("MANIFEST.json"))

        self.assertIn("product-patch/0001-fix-gateway-reject-hook-websocket-upgrades.patch", names)
        self.assertIn("product-patch/commit-summary.txt", names)
        by_path = {entry["path"]: entry for entry in manifest["entries"]}
        self.assertTrue(by_path["product-patch/0001-fix-gateway-reject-hook-websocket-upgrades.patch"]["exists"])
        self.assertIsNotNone(by_path["product-patch/0001-fix-gateway-reject-hook-websocket-upgrades.patch"]["sha256"])

    def test_final_infographic_renders_verified_fixed_without_stale_blocked_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_run_root(tmp)
            self._write_json(
                root / "post-patch-verification.json",
                {
                    "status": "verified_fixed",
                    "verification_status": "verified_fixed",
                    "pass": True,
                    "verified_fixed": True,
                    "disallowed_websocket": {"accepted_runs": 0, "total_runs": 15, "pass": True},
                    "allowed_gateway_websocket": {"accepted_runs": 15, "total_runs": 15, "pass": True},
                },
            )
            self._write_json(
                root / "CLOSURE_VERDICT.json",
                {
                    "status": "verified_fixed",
                    "proof_candidate_reproduced": True,
                    "patch_pending": False,
                    "verified_fixed": True,
                    "verification_status": "verified_fixed",
                    "provenance_complete": False,
                },
            )
            self._write_json(
                root / "openclaw-hooks-wake-patch-objective.json",
                {
                    "finding": "unauthenticated WebSocket upgrade on /hooks/wake",
                    "patch_status": "patch_applied_verified_in_local_branch",
                    "required_fix_contract": "disallowed handshakes must not return HTTP 101",
                },
            )
            report_json, _ = final_report.build_report(root)
            html = final_infographic.build_html(root)

        self.assertEqual(report_json["status"], "verified_fixed")
        self.assertFalse(report_json["patch_pending"])
        self.assertTrue(report_json["verified_fixed"])
        self.assertEqual(report_json["verification_status"], "verified_fixed")
        self.assertIn("Verified Fix", html)
        self.assertIn("Verification Gate", html)
        self.assertIn("verified_fixed", html)
        self.assertNotIn("blocked patch verification", html)
        self.assertNotIn("not a verified fix", html)
        self.assertNotIn("Patch implementation and rerun are still missing", html)
        self.assertNotIn("Apply patch, rerun focused Docker proof", html)


if __name__ == "__main__":
    unittest.main()
