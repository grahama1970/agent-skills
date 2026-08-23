"""Evidence-model behavioral checks, mixed into TestCleanup.

Split out of test_cleanup.py to keep every file under the 800-line rule from
/best-practices-python. These are methods, not standalone tests: TestCleanup
inherits them and run_all() invokes them in order.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cleanup  # noqa: E402


class EvidenceCasesMixin:
    def _write_evidence_artifact(self, files, **overrides):
        payload = {
            "contract": cleanup.CLEANUP_EVIDENCE_CONTRACT,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "repository_path": self.temp_dir,
            "analysis_complete": True,
            "proof_scope": {"languages_with_resolved_edges": ["python"]},
            "scan_failures": [],
            "files": files,
        }
        payload.update(overrides)
        Path(cleanup.CLEANUP_EVIDENCE_FILENAME).write_text(json.dumps(payload))
        return payload

    def test_candidate_evidence_is_joined_per_file(self):
        """Each candidate must get its own verdict, never an aggregate count."""
        print("\nTesting per-candidate dependency evidence join...")

        used = Path("used.py")
        used.write_text("VALUE = 1\n")
        orphan = Path("orphan.py")
        orphan.write_text("OTHER = 2\n")

        self._write_evidence_artifact({
            "used.py": {
                "content_sha256": cleanup._working_tree_sha256("used.py"),
                "language": "python",
                "parse_status": "ok",
                "inbound_references": [{"from_path": "cli.py", "kind": "static_import"}],
                "entrypoint_references": [],
                "dynamic_reference_warnings": [],
            },
            "orphan.py": {
                "content_sha256": cleanup._working_tree_sha256("orphan.py"),
                "language": "python",
                "parse_status": "ok",
                "inbound_references": [],
                "entrypoint_references": [],
                "dynamic_reference_warnings": [],
            },
        })
        artifact = cleanup.scan_cleanup_evidence_artifact()
        self.assert_equal(artifact["status"], "complete", "Artifact should parse as complete")

        referenced = cleanup.evaluate_candidate_dependency_evidence("used.py", artifact)
        self.assert_equal(referenced["verdict"], "referenced", "Inbound refs must be seen")
        self.assert_equal(
            referenced["mutation_allowed"], False, "Referenced files are never mutable"
        )

        orphaned = cleanup.evaluate_candidate_dependency_evidence("orphan.py", artifact)
        self.assert_equal(
            orphaned["verdict"], "no_inbound_references", "Unreferenced file gets its own verdict"
        )
        self.assert_equal(
            orphaned["mutation_allowed"],
            False,
            "Zero inbound references still requires readiness proof",
        )
        self.assert_in(
            "readiness_required", orphaned, "Readiness proof must be demanded explicitly"
        )

        # A file that is itself an entry root is never an orphan, even with
        # zero inbound references.
        Path("test_thing.py").write_text("def test_thing():\n    assert True\n")
        self._write_evidence_artifact({
            "test_thing.py": {
                "content_sha256": cleanup._working_tree_sha256("test_thing.py"),
                "language": "python",
                "parse_status": "ok",
                "inbound_references": [],
                "entrypoint_references": [],
                "entry_kinds": ["pytest_test"],
                "dynamic_reference_warnings": [],
            },
        })
        root = cleanup.evaluate_candidate_dependency_evidence(
            "test_thing.py", cleanup.scan_cleanup_evidence_artifact()
        )
        self.assert_equal(
            root["verdict"],
            "entry_root",
            "A pytest module runs without being imported and must not read as unused",
        )
        self.assert_equal(
            root["mutation_allowed"], False, "Entry roots are still never mutable"
        )

        uncovered = cleanup.evaluate_candidate_dependency_evidence("ghost.py", artifact)
        self.assert_equal(
            uncovered["verdict"], "outside_proof_scope", "Uncovered paths must not pass silently"
        )

        # A language the producer cannot resolve edges for must not read as unused.
        Path("app.ts").write_text("export const x = 1;\n")
        self._write_evidence_artifact({
            "app.ts": {
                "content_sha256": cleanup._working_tree_sha256("app.ts"),
                "language": "typescript",
                "parse_status": "not_analyzed",
                "inbound_references": [],
                "entrypoint_references": [],
                "dynamic_reference_warnings": [],
            },
        })
        out_of_scope = cleanup.evaluate_candidate_dependency_evidence(
            "app.ts", cleanup.scan_cleanup_evidence_artifact()
        )
        self.assert_equal(
            out_of_scope["verdict"],
            "outside_analysis_scope",
            "Languages without resolved edges must never read as unreferenced",
        )

        # Content change invalidates the record without touching mtime logic.
        orphan.write_text("OTHER = 3\n")
        stale = cleanup.evaluate_candidate_dependency_evidence("orphan.py", artifact)
        self.assert_equal(
            stale["verdict"], "stale_evidence", "Content hash mismatch must invalidate evidence"
        )

    def test_missing_artifact_blocks_tracked_mutation_not_assessment(self):
        """A missing index degrades verdicts; it must not stop assessment."""
        print("\nTesting phase separation without an evidence artifact...")

        Path(cleanup.CLEANUP_EVIDENCE_FILENAME).unlink(missing_ok=True)
        artifact = cleanup.scan_cleanup_evidence_artifact()
        self.assert_equal(artifact["status"], "missing", "Artifact should report missing")
        self.assert_in(
            "--local-artifacts-only",
            artifact["producer_command"],
            "Cleanup evidence refresh must not route agents into Memory-write scan paths",
        )

        verdict = cleanup.evaluate_candidate_dependency_evidence("any.py", artifact)
        self.assert_equal(
            verdict["verdict"], "no_dependency_evidence", "Missing artifact yields no evidence"
        )

        readiness = cleanup.evaluate_mutation_readiness(
            {"dead_files": [{"path": "any.py"}], "candidate_dependency_evidence": [verdict]},
            {"status": "missing"},
            artifact,
            {},
        )
        self.assert_equal(
            readiness["phases"]["assessment"],
            "complete",
            "Assessment must complete without any index",
        )
        self.assert_equal(
            readiness["mutation_classes"]["tracked_file_mutation"]["status"],
            "blocked",
            "Tracked mutation must stay blocked without per-candidate evidence",
        )

    def test_memory_outage_does_not_block_local_analysis(self):
        """Local analysis complete + marker missing means Memory alone is blocked."""
        print("\nTesting Memory-outage phase states...")

        Path("kept.py").write_text("KEPT = 1\n")
        self._write_evidence_artifact({
            "kept.py": {
                "content_sha256": cleanup._working_tree_sha256("kept.py"),
                "language": "python",
                "parse_status": "ok",
                "inbound_references": [],
                "entrypoint_references": [],
                "dynamic_reference_warnings": [],
            }
        })

        readiness = cleanup.evaluate_mutation_readiness(
            {"dead_files": [], "candidate_dependency_evidence": []},
            {"status": "missing"},
            cleanup.scan_cleanup_evidence_artifact(),
            {},
        )
        self.assert_equal(
            readiness["phases"]["local_dependency_analysis"],
            "complete",
            "Local Tree-sitter analysis must survive a Memory outage",
        )
        self.assert_equal(
            readiness["phases"]["memory_indexing"],
            "blocked",
            "Memory indexing must be reported as blocked, not fatal",
        )

    def test_junk_removal_requires_per_path_provenance(self):
        """Junk patterns nominate; only unreferenced untracked paths are removable."""
        print("\nTesting junk provenance...")

        Path("stray.log").write_text("noise\n")
        Path("fixtures").mkdir()
        Path("fixtures/needed.log").write_text("fixture\n")
        config = Path("config.py")
        config.write_text('LOG_FIXTURE = "fixtures/needed.log"\n')
        subprocess.run(["git", "add", str(config)], capture_output=True)
        subprocess.run(["git", "commit", "-m", "add config"], capture_output=True)

        verdicts = cleanup.evaluate_junk_candidates(["stray.log", "fixtures/needed.log"])
        self.assert_equal(
            verdicts["stray.log"]["removal_allowed"],
            True,
            "Unreferenced untracked junk should clear provenance",
        )
        self.assert_equal(
            verdicts["fixtures/needed.log"]["removal_allowed"],
            False,
            "Junk-pattern paths named by tracked code must be withheld",
        )

        actions = cleanup.execute_cleanup({
            "root_strays": [],
            "untracked_files": ["stray.log", "fixtures/needed.log"],
            "dead_files": [],
            "junk_verdicts": verdicts,
        }, force=True)

        self.assert_true(
            any("stray.log" in action for action in actions),
            "Cleared junk should be removed",
        )
        self.assert_true(
            Path("fixtures/needed.log").exists(),
            "Referenced junk-pattern file must survive execution",
        )

    def test_execute_without_verdicts_removes_nothing(self):
        """execute_cleanup fails closed when provenance verdicts are absent."""
        print("\nTesting fail-closed junk removal...")

        Path("unverified.log").write_text("noise\n")
        actions = cleanup.execute_cleanup({
            "root_strays": [],
            "untracked_files": ["unverified.log"],
            "dead_files": [],
        }, force=True)

        self.assert_equal(actions, [], "No verdict means no removal")
        self.assert_true(
            Path("unverified.log").exists(),
            "Junk pattern alone must never authorize deletion",
        )

    def test_all_blocked_junk_is_not_reported_as_no_candidates(self):
        """A blocked class must not read as an empty one."""
        print("\nTesting blocked-vs-empty junk status...")

        base = {"dead_files": [], "candidate_dependency_evidence": []}
        all_blocked = cleanup.evaluate_mutation_readiness(
            base,
            {"status": "missing"},
            {"status": "missing"},
            {"a.log": {"path": "a.log", "removal_allowed": False, "reason": "referenced"}},
        )
        self.assert_equal(
            all_blocked["mutation_classes"]["junk_untracked_removal"]["status"],
            "blocked",
            "Candidates that all fail provenance must report blocked",
        )

        empty = cleanup.evaluate_mutation_readiness(
            base, {"status": "missing"}, {"status": "missing"}, {}
        )
        self.assert_equal(
            empty["mutation_classes"]["junk_untracked_removal"]["status"],
            "no_candidates",
            "An empty class must stay distinguishable from a blocked one",
        )

    def test_unusable_evidence_is_distinguished_from_absent_evidence(self):
        """Absent evidence blocks; corrupt or foreign evidence is an error."""
        print("\nTesting unusable-evidence detection...")

        Path(cleanup.CLEANUP_EVIDENCE_FILENAME).unlink(missing_ok=True)
        absent = cleanup.unusable_evidence_errors({
            "cleanup_evidence_artifact": cleanup.scan_cleanup_evidence_artifact(),
            "ingest_code_evidence": {"status": "missing"},
            "untracked_files": [],
        })
        self.assert_equal(absent, [], "A missing artifact is a blocked state, not an error")

        Path(cleanup.CLEANUP_EVIDENCE_FILENAME).write_text("not json{{{")
        corrupt = cleanup.unusable_evidence_errors({
            "cleanup_evidence_artifact": cleanup.scan_cleanup_evidence_artifact(),
            "ingest_code_evidence": {"status": "missing"},
            "untracked_files": [],
        })
        self.assert_true(
            any("unreadable" in error for error in corrupt),
            "A corrupt artifact must be reported as unusable",
        )

        self._write_evidence_artifact({}, repository_path="/somewhere/else")
        foreign = cleanup.unusable_evidence_errors({
            "cleanup_evidence_artifact": cleanup.scan_cleanup_evidence_artifact(),
            "ingest_code_evidence": {"status": "missing"},
            "untracked_files": [],
        })
        self.assert_true(
            any("belongs to" in error for error in foreign),
            "An artifact from another repository must be reported as unusable",
        )
        Path(cleanup.CLEANUP_EVIDENCE_FILENAME).unlink(missing_ok=True)

    def test_last_commit_times_match_per_file_git_log(self):
        """The single history walk must agree with `git log -1` per file."""
        print("\nTesting single-walk commit timestamps...")

        doc = Path("history_doc.md")
        doc.write_text("# doc\n")
        subprocess.run(["git", "add", str(doc)], capture_output=True)
        subprocess.run(["git", "commit", "-m", "add doc"], capture_output=True)

        times = cleanup.get_last_commit_times()
        expected = subprocess.run(
            ["git", "log", "-1", "--format=%ct", str(doc)],
            capture_output=True,
            text=True,
        ).stdout.strip()

        self.assert_equal(
            str(times.get("history_doc.md")),
            expected,
            "Walked timestamp must equal the per-file git log timestamp",
        )

    def test_cleanup_does_not_report_its_own_outputs(self):
        """A successful run must not manufacture findings for the next run."""
        print("\nTesting own-output exclusion...")

        for path in (
            ".cleanup-evidence.json",
            ".ingest-code.json",
            "CLEANUP_PLAN.md",
            "artifacts/cleanup/cleanup_receipt.json",
            "local/CLEANUP_LOG.md",
        ):
            self.assert_true(
                cleanup.is_cleanup_output(path),
                f"{path} must be recognized as a cleanup output",
            )
        for path in ("src/app.py", "artifacts/model.pt", "local/data.csv"):
            self.assert_true(
                not cleanup.is_cleanup_output(path),
                f"{path} must not be treated as a cleanup output",
            )

        Path("artifacts/cleanup").mkdir(parents=True, exist_ok=True)
        Path("artifacts/cleanup/cleanup_receipt.json").write_text("{}")
        Path("local").mkdir(exist_ok=True)
        Path("local/CLEANUP_LOG.md").write_text("# log\n")

        strays = {s["path"] for s in cleanup.scan_root_strays()}
        self.assert_true(
            "local/" not in strays,
            "The cleanup log directory must not be reported as a root stray",
        )

        # Leave no stub behind: log_cleanup writes its own header on creation.
        Path("local/CLEANUP_LOG.md").unlink()

    def test_confirm_action_declines_without_a_terminal(self):
        """Nightly runs have no stdin; prompting there must not crash."""
        print("\nTesting non-interactive confirmation...")

        class _NoTTY:
            @staticmethod
            def isatty():
                return False

        original = sys.stdin
        sys.stdin = _NoTTY()
        try:
            self.assert_equal(
                cleanup.confirm_action("Remove something"),
                False,
                "A non-interactive run must decline rather than prompt",
            )
        finally:
            sys.stdin = original

    def test_phase_receipt_is_resumable(self):
        """The receipt must record phase states and how to resume them."""
        print("\nTesting phase receipt...")

        findings = {
            "root_strays": [],
            "untracked_files": [],
            "dead_files": [],
            "outdated_docs": [],
            "candidate_dependency_evidence": [],
            "ingest_code_evidence": cleanup.scan_ingest_code_evidence(),
            "cleanup_evidence_artifact": cleanup.scan_cleanup_evidence_artifact(),
        }
        readiness = cleanup.evaluate_mutation_readiness(
            findings,
            findings["ingest_code_evidence"],
            findings["cleanup_evidence_artifact"],
            {},
        )
        receipt = cleanup.build_phase_receipt(findings, readiness)
        path = cleanup.write_phase_receipt(receipt, "artifacts/cleanup/receipt.json")

        self.assert_true(path.exists(), "Receipt file should be written")
        stored = json.loads(path.read_text())
        for phase in (
            "local_dependency_analysis",
            "memory_indexing",
            "assessment",
            "mutation",
        ):
            self.assert_in(phase, stored["phases"], f"Receipt must record {phase}")
        self.assert_true(
            any("count_only" in limit for limit in stored["proof_limits"]),
            "Receipt must disclose that marker coverage is count-only",
        )
        self.assert_true(
            any("python_imports_only" in limit for limit in stored["proof_limits"]),
            "Receipt must disclose the Python-only edge scope",
        )

    def test_tracked_mutation_reasons_distinguish_verdict_classes(self):
        """Blocked candidate verdicts must not be mislabeled as missing evidence."""
        print("\nTesting tracked mutation verdict reason wording...")

        findings = {
            "dead_files": [{"path": "a.py"}, {"path": "b.py"}, {"path": "c.ts"}],
            "candidate_dependency_evidence": [
                {"path": "a.py", "verdict": "entry_root"},
                {"path": "b.py", "verdict": "no_inbound_references"},
                {"path": "c.ts", "verdict": "outside_analysis_scope"},
            ],
        }
        readiness = cleanup.evaluate_mutation_readiness(
            findings,
            {"status": "missing"},
            {"status": "complete", "proof_scope": {}},
            {},
        )
        tracked = readiness["mutation_classes"]["tracked_file_mutation"]
        reasons = " ".join(tracked["reasons"])
        self.assert_equal(
            tracked["verdict_counts"]["entry_root"],
            1,
            "Verdict counts should preserve why candidates are blocked",
        )
        self.assert_true(
            "lack per-candidate dependency evidence" not in reasons,
            "Candidates with explicit verdicts must not be mislabeled as lacking evidence",
        )
        self.assert_true(
            "dependency evidence that blocks mutation" in reasons,
            "Entry roots and references should be reported as evidence-based blockers",
        )
        self.assert_true(
            "out-of-scope dependency evidence" in reasons,
            "Out-of-scope candidates should be distinct from dependency blockers",
        )

    def test_log_cleanup(self):
        """Test logging cleanup actions"""
        print("\nTesting log_cleanup...")
        
        findings = {
            "uncommitted_changes": [],
            "untracked_files": ["junk.log"],
            "dead_files": [],
            "outdated_docs": []
        }
        
        actions_taken = ["Removed file: junk.log"]
        
        cleanup.log_cleanup(findings, actions_taken)
        
        log_file = Path("local/CLEANUP_LOG.md")
        self.assert_true(log_file.exists(), "Log file should be created")
        
        content = log_file.read_text()
        self.assert_in("Cleanup Log", content, "Log should have header")
        self.assert_in("junk.log", content, "Log should mention junk.log")
    
