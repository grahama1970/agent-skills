#!/usr/bin/env python3
"""Directly runnable tests for skills/hack/self_improve_loop.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
import sys
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "self_improve_loop.py"
SPEC = importlib.util.spec_from_file_location("self_improve_loop", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
loop = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = loop
SPEC.loader.exec_module(loop)


ROOT = loop.ARTIFACT_ROOT
EVIDENCE = f"{ROOT}/session-unit/evidence/stdout.log"
FINDINGS = f"{ROOT}/session-unit/evidence/findings.json"


class DecideNextActionTests(unittest.TestCase):
    def test_success_stops_successfully(self) -> None:
        config = loop.LoopConfig(session_id="unit")
        attempts = [loop.AttemptRecord("a1", "plan-1", loop.AttemptStatus.SUCCESS, (EVIDENCE,))]

        decision = loop.decide_next_action(config, attempts)

        self.assertEqual(decision.outcome, loop.DecisionOutcome.SUCCESS)
        self.assertTrue(decision.stop)
        self.assertFalse(decision.retry_same_plan)

    def test_transient_retries_same_plan_with_separate_budget(self) -> None:
        config = loop.LoopConfig(session_id="unit", max_plan_revisions=0, max_transient_retries_per_plan=2)
        attempts = [
            loop.AttemptRecord("a1", "plan-1", loop.AttemptStatus.TRANSIENT_INFRA_FAILURE, (EVIDENCE,)),
            loop.AttemptRecord("a2", "plan-1", loop.AttemptStatus.TRANSIENT_INFRA_FAILURE, (FINDINGS,)),
        ]

        decision = loop.decide_next_action(config, attempts)

        self.assertEqual(decision.outcome, loop.DecisionOutcome.SAME_PLAN_RETRY_FOR_TRANSIENT)
        self.assertFalse(decision.stop)
        self.assertTrue(decision.retry_same_plan)
        self.assertFalse(decision.requires_plan_revision)
        self.assertEqual(decision.next_plan_id_hint, "plan-1")

    def test_transient_budget_exhaustion_stops_infra_unreachable(self) -> None:
        config = loop.LoopConfig(session_id="unit", max_transient_retries_per_plan=1)
        attempts = [
            loop.AttemptRecord("a1", "plan-1", loop.AttemptStatus.TRANSIENT_INFRA_FAILURE, (EVIDENCE,)),
            loop.AttemptRecord("a2", "plan-1", loop.AttemptStatus.TRANSIENT_INFRA_FAILURE, (FINDINGS,)),
        ]

        decision = loop.decide_next_action(config, attempts)

        self.assertEqual(decision.outcome, loop.DecisionOutcome.STOP_INFRA_UNREACHABLE)
        self.assertTrue(decision.stop)

    def test_strategy_failure_requires_complete_plan_revision_context(self) -> None:
        config = loop.LoopConfig(
            session_id="unit",
            max_plan_revisions=2,
            dogpile_context=("prior dogpile synthesis pointer",),
            memory_context=("prior memory summary",),
        )
        attempts = [
            loop.AttemptRecord(
                attempt_id="a1",
                plan_id="plan-1",
                status=loop.AttemptStatus.STRATEGY_FAILURE,
                evidence_paths=(EVIDENCE, FINDINGS),
                summary="Exploit path did not match target version.",
                learning_delta="Target version rejects the planned probe.",
                dogpile_context=("attempt dogpile context",),
                memory_context=("attempt memory context",),
            )
        ]

        decision = loop.decide_next_action(config, attempts)

        self.assertEqual(decision.outcome, loop.DecisionOutcome.REGENERATE_PLAN_FOR_STRATEGY_FAILURE)
        self.assertFalse(decision.stop)
        self.assertTrue(decision.requires_plan_revision)
        context = decision.plan_revision_context
        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(context.prior_failure_evidence, (EVIDENCE, FINDINGS))
        self.assertEqual(context.previous_plan_id, "plan-1")
        self.assertEqual(context.learning_delta, "Target version rejects the planned probe.")
        self.assertIn("prior dogpile synthesis pointer", context.dogpile_context)
        self.assertIn("attempt memory context", context.memory_context)
        self.assertTrue(context.strategy_change.strip())

    def test_strategy_failure_without_evidence_is_ambiguous(self) -> None:
        config = loop.LoopConfig(session_id="unit")
        attempts = [loop.AttemptRecord("a1", "plan-1", loop.AttemptStatus.STRATEGY_FAILURE)]

        decision = loop.decide_next_action(config, attempts)

        self.assertEqual(decision.outcome, loop.DecisionOutcome.STOP_AMBIGUOUS)
        self.assertTrue(decision.stop)

    def test_strategy_revision_budget_stops_max_retries(self) -> None:
        config = loop.LoopConfig(session_id="unit", max_plan_revisions=1)
        attempts = [
            loop.AttemptRecord("a1", "plan-1", loop.AttemptStatus.STRATEGY_FAILURE, (EVIDENCE,)),
            loop.AttemptRecord("a2", "plan-2", loop.AttemptStatus.SECURITY_FAILURE, (FINDINGS,)),
        ]

        decision = loop.decide_next_action(config, attempts)

        self.assertEqual(decision.outcome, loop.DecisionOutcome.STOP_MAX_RETRIES)
        self.assertTrue(decision.stop)

    def test_safety_and_infra_preflight_stop_conditions(self) -> None:
        self.assertEqual(
            loop.decide_next_action(loop.LoopConfig(session_id="unit", authorized_scope_confirmed=False), []).outcome,
            loop.DecisionOutcome.STOP_UNSAFE_SCOPE,
        )
        self.assertEqual(
            loop.decide_next_action(loop.LoopConfig(session_id="unit", ambiguous_scope=True), []).outcome,
            loop.DecisionOutcome.STOP_AMBIGUOUS,
        )
        self.assertEqual(
            loop.decide_next_action(loop.LoopConfig(session_id="unit", infrastructure_reachable=False), []).outcome,
            loop.DecisionOutcome.STOP_INFRA_UNREACHABLE,
        )
        self.assertEqual(
            loop.decide_next_action(
                loop.LoopConfig(session_id="unit", require_test_lab_preflight=True, test_lab_reachable=False),
                [],
            ).outcome,
            loop.DecisionOutcome.STOP_INFRA_UNREACHABLE,
        )


class BuilderTests(unittest.TestCase):
    def test_docker_launch_spec_materializes_session_files_policy_mounts_and_evidence(self) -> None:
        config = loop.LoopConfig(
            session_id="unit",
            docker_network_policy=loop.NetworkPolicy.NONE,
            environment={"SAFE_MODE": "1"},
            target_mounts=(loop.MountSpec("/authorized/target", "/target", loop.MountMode.READ_ONLY),),
        )

        spec = loop.build_docker_launch_spec(config, "plan-1")

        self.assertEqual(spec.session_dir, f"{ROOT}/session-unit")
        self.assertEqual(spec.dockerfile_path, f"{ROOT}/session-unit/Dockerfile")
        self.assertEqual(spec.compose_path, f"{ROOT}/session-unit/docker-compose.yml")
        self.assertIn("FROM python:3.12-slim", spec.dockerfile_content)
        self.assertIn('network_mode: "none"', spec.compose_content)
        self.assertIn("SAFE_MODE", spec.compose_content)
        self.assertIn("/authorized/target:/target:ro", spec.compose_content)
        self.assertIn(f"{ROOT}/session-unit:/evidence:rw", spec.compose_content)
        self.assertTrue(all(path.startswith(f"{ROOT}/session-unit/evidence/") for path in spec.evidence_paths.values()))

    def test_memory_and_project_knowledge_records_use_artifact_pointers_only(self) -> None:
        config = loop.LoopConfig(session_id="unit")
        attempts = [loop.AttemptRecord("a1", "plan-1", loop.AttemptStatus.SUCCESS, (EVIDENCE,))]
        decision = loop.decide_next_action(config, attempts)

        memory = loop.build_memory_record(config, attempts, decision)
        knowledge = loop.build_project_knowledge_update(config, attempts, decision)

        self.assertEqual(memory.artifact_pointers, (EVIDENCE,))
        self.assertIn("success", memory.distilled_lesson)
        self.assertEqual(knowledge.artifact_pointers, (EVIDENCE,))
        self.assertIn("attempt a1", knowledge.facts[0])
        with self.assertRaises(ValueError):
            loop.MemoryRecord("unit", "bad", "raw log inline", ("hack",), ("inline raw log text",))

    def test_research_requirement_covers_all_required_sources_and_synthesizes_next_plan(self) -> None:
        config = loop.LoopConfig(session_id="unit", include_books_sites_research=True)
        context = loop.PlanRevisionContext(
            prior_failure_evidence=(EVIDENCE,),
            previous_plan_id="plan-1",
            learning_delta="Need version-specific verification.",
            dogpile_context=("old synthesis",),
            memory_context=("old lesson",),
            strategy_change="Switch to version-specific defensive validation.",
        )

        requirement = loop.build_research_requirement(config, context, topic="authorized web audit")

        expected_sources = {
            loop.ResearchSource.BRAVE_WEB,
            loop.ResearchSource.GITHUB_REPOS,
            loop.ResearchSource.GITHUB_ISSUES,
            loop.ResearchSource.GITHUB_CODE,
            loop.ResearchSource.ARXIV,
            loop.ResearchSource.FEEDS_ADVISORIES,
            loop.ResearchSource.BOOKS_SITES,
        }
        self.assertEqual(set(requirement.required_sources), expected_sources)
        self.assertIn("next plan", requirement.synthesis_prompt.lower())
        for source in expected_sources:
            self.assertTrue(requirement.source_queries[source].strip())


if __name__ == "__main__":
    unittest.main()
