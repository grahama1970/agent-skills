from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "analyze_transcript.py"
SPEC = importlib.util.spec_from_file_location("analyze_transcript", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AnalyzeTranscriptTests(unittest.TestCase):
    def analyze(self, text: str, answers: dict[str, str] | None = None):
        return MODULE.analyze(text, answers or {}, "Python 3")

    def test_two_sum_stops_before_code_and_asks_blocking_questions(self):
        raw = (
            "Interviewer: Given an array of integers and a target, write a function "
            "that finds two numbers that add up to the target.\n"
            "Candidate: I would probably use a hash map.\n"
        )
        result = self.analyze(raw)

        self.assertEqual(result["status"], "needs_clarification")
        self.assertFalse(result["solution_allowed"])
        self.assertIsNone(result["solver_prompt"])
        self.assertEqual(result["candidates"][0]["title"], "Two Sum")
        self.assertEqual(result["candidates"][0]["match_kind"], "likely_exact")
        self.assertEqual(
            [question["id"] for question in result["clarifying_questions"]],
            ["return-contract", "element-reuse", "multiple-solutions"],
        )
        self.assertNotIn("hash map", result["selected_span"]["text"].casefold())

    def test_answer_round_trip_authorizes_solution(self):
        raw = (
            "Interviewer: Given an array of integers and a target, write a function "
            "that finds two numbers that add up to the target."
        )
        answers = {
            "return-contract": "Return the two indices.",
            "element-reuse": "The indices must be distinct.",
            "multiple-solutions": "Exactly one solution exists.",
        }
        result = self.analyze(raw, answers)

        self.assertEqual(result["status"], "ready_for_solution")
        self.assertTrue(result["solution_allowed"])
        self.assertEqual(result["clarifying_questions"], [])
        self.assertIn("Solve this interview coding problem", result["solver_prompt"])
        self.assertIn("Return the two indices", result["solver_prompt"])

    def test_fully_specified_two_sum_is_ready_without_assumed_defaults(self):
        raw = (
            "Interviewer: Given an unsorted array of integers and a target, return "
            "the two distinct indices whose values sum to the target. Exactly one "
            "solution exists, and you may not use the same element twice."
        )
        result = self.analyze(raw)

        self.assertEqual(result["status"], "ready_for_solution")
        self.assertEqual(result["facts"]["return_contract"], "indices")
        self.assertEqual(result["clarifying_questions"], [])

    def test_live_evidence_jsonl_ignores_interim_and_reads_final_turns(self):
        rows = [
            {
                "schema": "live_evidence.transcript_event.v1",
                "event_id": "event0000",
                "speaker": "interviewer",
                "kind": "interim",
                "text": "Tell me about yourself",
                "sequence": 0,
            },
            {
                "schema": "live_evidence.transcript_event.v1",
                "event_id": "event0001",
                "speaker": "interviewer",
                "kind": "stabilized",
                "text": "Given a string containing lowercase letters and parentheses,",
                "sequence": 1,
            },
            {
                "schema": "live_evidence.transcript_event.v1",
                "event_id": "event0002",
                "speaker": "interviewer",
                "kind": "final",
                "text": (
                    "remove the minimum number of parentheses so the result is valid "
                    "and return any valid string."
                ),
                "sequence": 2,
            },
        ]
        result = self.analyze("\n".join(json.dumps(row) for row in rows))

        self.assertEqual(result["input_format"], "jsonl")
        self.assertEqual(result["status"], "ready_for_solution")
        self.assertEqual(
            result["candidates"][0]["title"],
            "Minimum Remove to Make Valid Parentheses",
        )
        self.assertEqual(result["candidates"][0]["match_kind"], "likely_exact")
        self.assertEqual(
            [source["event_id"] for source in result["selected_span"]["sources"]],
            ["event0001", "event0002"],
        )

    def test_live_evidence_journal_envelope_is_supported(self):
        rows = [
            {"kind": "evidence_card", "payload": {"text": "ignore this"}},
            {
                "kind": "transcript",
                "payload": {
                    "schema": "live_evidence.transcript_event.v1",
                    "event_id": "event1001",
                    "speaker": "interviewer",
                    "kind": "final",
                    "text": "Given a sorted array, use binary search to find a target and return its index.",
                    "sequence": 7,
                },
            },
        ]
        result = self.analyze("\n".join(json.dumps(row) for row in rows))

        self.assertEqual(result["turn_count"], 1)
        self.assertEqual(result["candidates"][0]["title"], "Binary Search")
        self.assertEqual(result["selected_span"]["sources"][0]["event_id"], "event1001")

    def test_question_candidate_json_is_accepted_directly(self):
        raw = json.dumps(
            {
                "schema": "live_evidence.question_candidate.v1",
                "question_id": "question-12345",
                "normalized_question": (
                    "Given a linked list, reverse the existing nodes in-place and return the new head."
                ),
                "start_sequence": 4,
            }
        )
        result = self.analyze(raw)

        self.assertEqual(result["input_format"], "json")
        self.assertEqual(result["candidates"][0]["title"], "Reverse Linked List")
        self.assertEqual(result["selected_span"]["sources"][0]["event_id"], "question-12345")

    def test_generic_smalltalk_is_not_a_coding_question(self):
        raw = (
            "Interviewer: How are you today?\n"
            "Candidate: Great, thanks.\n"
            "Interviewer: Walk me through your resume.\n"
        )
        result = self.analyze(raw)

        self.assertEqual(result["status"], "no_coding_question")
        self.assertFalse(result["solution_allowed"])
        self.assertEqual(result["candidates"], [])

    def test_merge_intervals_asks_endpoint_semantics(self):
        raw = (
            "Interviewer: Given a list of intervals, merge all overlapping intervals "
            "and return the merged list."
        )
        result = self.analyze(raw)

        self.assertEqual(result["candidates"][0]["title"], "Merge Intervals")
        self.assertIn(
            "touching-intervals",
            [question["id"] for question in result["clarifying_questions"]],
        )
        self.assertFalse(result["solution_allowed"])

    def test_number_of_islands_asks_connectivity_and_mutation(self):
        raw = (
            "Interviewer: Given a grid of land and water, count the number of islands "
            "and return the count."
        )
        result = self.analyze(raw)

        self.assertEqual(result["candidates"][0]["title"], "Number of Islands")
        ids = [question["id"] for question in result["clarifying_questions"]]
        self.assertIn("grid-adjacency", ids)
        self.assertIn("grid-mutation", ids)

    def test_output_is_deterministic_and_hash_bound(self):
        raw = "Interviewer: Given a sorted array, use binary search to find a target and return its index."
        first = self.analyze(raw)
        second = self.analyze(raw)

        self.assertEqual(first, second)
        self.assertEqual(first["transcript_sha256"], hashlib.sha256(raw.encode()).hexdigest())

    def test_cli_rejects_non_object_answers(self):
        with tempfile.TemporaryDirectory() as directory:
            transcript = Path(directory) / "transcript.txt"
            transcript.write_text(
                "Interviewer: Given an array, find two numbers that sum to a target.",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), str(transcript), "--answers", "[]"],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 2)
        error = json.loads(completed.stderr)
        self.assertIn("JSON object", error["error"])

    def test_cli_reads_stdin_and_emits_json(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "-", "--compact"],
            input=(
                "Interviewer: Given a sorted array, use binary search to find a target "
                "and return its index."
            ),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["schema"], "transcript_to_leetcode.analysis.v1")
        self.assertEqual(result["candidates"][0]["title"], "Binary Search")


if __name__ == "__main__":
    unittest.main()
