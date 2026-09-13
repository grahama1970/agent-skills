"""Deterministic reference-policy tests. No production integration claims."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts/watchdog/single_tick_policy.py"
SPEC = importlib.util.spec_from_file_location("watchdog_single_tick_policy_reference", MODULE)
assert SPEC is not None and SPEC.loader is not None
policy = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = policy
SPEC.loader.exec_module(policy)
T = policy.TicketRef
S = policy.ProjectScan
A = policy.AttemptResult
AS = policy.AttemptState


def complete(project, *numbers, count=None):
    return S(project, tuple(T(f"owner/{project}", n) for n in numbers),
             len(numbers) if count is None else count, True)


class PolicyTests(unittest.TestCase):
    def run_policy(self, rows, max_tickets=1, dispositions=None, budget=lambda: True):
        calls = []
        dispositions = dispositions or {}

        def attempt(project, ticket):
            calls.append((project, ticket.number))
            return dispositions.get((project, ticket.number), A(AS.STARTED, "native_accepted"))

        result = policy.run_fleet_policy(
            tuple(rows), max_tickets=max_tickets, scan=rows.__getitem__,
            attempt=attempt, budget_available=budget,
        )
        return result, calls

    def test_empty_tau_falls_through_to_1620(self):
        r, calls = self.run_policy({"tau": complete("tau"),
                                   "agent-skills": complete("agent-skills", 1620)})
        self.assertEqual(calls, [("agent-skills", 1620)])
        self.assertEqual(r.last_served_project, "agent-skills")

    def test_blocked_project_does_not_end_fleet(self):
        r, calls = self.run_policy({"tau": complete("tau", count=2),
                                   "agent-skills": complete("agent-skills", 1620)})
        self.assertEqual(calls, [("agent-skills", 1620)])
        self.assertEqual(r.queue_observation, "OBSERVED_OPEN")

    def test_lease_race_does_not_consume_slot(self):
        r, calls = self.run_policy({"a": complete("a", 1, 2)}, dispositions={
            ("a", 1): A(AS.NOT_STARTED, "native_lease_conflict")})
        self.assertEqual(calls, [("a", 1), ("a", 2)])
        self.assertEqual(r.charged_slots, 1)

    def test_all_first_project_races_fall_through(self):
        r, calls = self.run_policy({"a": complete("a", 1), "b": complete("b", 2)},
                                  dispositions={("a", 1): A(AS.NOT_STARTED, "lane_busy")})
        self.assertEqual(calls[-1], ("b", 2))
        self.assertEqual(r.charged_slots, 1)

    def test_quota_park_does_not_block_unaffected_route(self):
        r, calls = self.run_policy({"a": complete("a", 1), "b": complete("b", 2)},
                                  dispositions={("a", 1): A(AS.NOT_STARTED, "quota_not_before")})
        self.assertEqual(calls, [("a", 1), ("b", 2)])
        self.assertEqual(r.last_served_project, "b")

    def test_max_three_serial_round_robin(self):
        r, calls = self.run_policy({"a": complete("a", 1, 2), "b": complete("b", 3, 4)}, 3)
        self.assertEqual(calls, [("a", 1), ("b", 3), ("a", 2)])
        self.assertEqual(r.stop_reason, "MAX_TICKETS")
        self.assertEqual(r.charged_slots, 3)

    def test_default_one_not_one_project_of_empty_work(self):
        r, calls = self.run_policy({"a": complete("a", 1, 2), "b": complete("b", 3)})
        self.assertEqual(calls, [("a", 1)])
        self.assertEqual(r.charged_slots, 1)

    def test_unknown_send_consumes_slot_and_stops(self):
        r, calls = self.run_policy({"a": complete("a", 1), "b": complete("b", 2)}, 3,
                                  {("a", 1): A(AS.INDETERMINATE, "ack_lost")})
        self.assertEqual(calls, [("a", 1)])
        self.assertEqual(r.charged_slots, 1)
        self.assertEqual(r.stop_reason, "RECONCILE_REQUIRED")

    def test_attempt_exception_never_assumes_not_started(self):
        calls = []
        def attempt(project, ticket):
            calls.append(ticket.key)
            raise TimeoutError("possibly sent")
        r = policy.run_fleet_policy(("a", "b"), max_tickets=3,
            scan=lambda p: complete(p, 1), attempt=attempt)
        self.assertEqual(len(calls), 1)
        self.assertEqual(r.stop_reason, "RECONCILE_REQUIRED")

    def test_scan_error_is_not_empty_and_does_not_stop_others(self):
        def scan(project):
            if project == "a":
                raise policy.ScanUnavailable("unavailable")
            return complete(project, 2)
        r = policy.run_fleet_policy(("a", "b"), max_tickets=1, scan=scan,
                                   attempt=lambda *args: A(AS.STARTED, "accepted"))
        self.assertEqual(r.attempts[0].project_id, "b")
        self.assertFalse(r.scan_complete)
        self.assertEqual(r.queue_observation, "NOT_FULLY_OBSERVED")

    def test_all_empty_requires_complete_observation(self):
        r, calls = self.run_policy({"a": complete("a"), "b": complete("b")})
        self.assertEqual(calls, [])
        self.assertEqual(r.queue_observation, "OBSERVED_EMPTY")
        self.assertTrue(r.scan_complete)

    def test_blocked_is_not_empty(self):
        r, _ = self.run_policy({"a": complete("a", count=1)})
        self.assertEqual(r.queue_observation, "OBSERVED_OPEN")
        self.assertEqual(r.charged_slots, 0)

    def test_paused_unobserved_scope_cannot_clear_fleet(self):
        r, _ = self.run_policy({"a": S("a", reason="PAUSED"), "b": complete("b")})
        self.assertEqual(r.queue_observation, "NOT_FULLY_OBSERVED")

    def test_expired_budget_no_first_dispatch_exception(self):
        r, calls = self.run_policy({"a": complete("a", 1)}, budget=lambda: False)
        self.assertEqual(calls, [])
        self.assertEqual(r.scans, ())
        self.assertEqual(r.stop_reason, "ADMISSION_DEADLINE")

    def test_budget_after_scan_does_not_start_first_ticket(self):
        values = iter([True, False])
        r, calls = self.run_policy({"a": complete("a", 1)}, budget=lambda: next(values))
        self.assertEqual(calls, [])
        self.assertEqual(r.stop_reason, "ADMISSION_DEADLINE")

    def test_partial_scan_cannot_claim_fleet_empty(self):
        r, _ = self.run_policy({"a": S("a", reason="PAGINATION_LIMIT")})
        self.assertEqual(r.queue_observation, "NOT_FULLY_OBSERVED")

    def test_partial_scan_can_offer_independently_validated_candidate(self):
        r, calls = self.run_policy({"a": S("a", (T("owner/a", 1),), 2, False,
                                             "PAGINATION_LIMIT")})
        self.assertEqual(calls, [("a", 1)])
        self.assertFalse(r.scan_complete)

    def test_same_issue_in_two_scopes_is_not_dispatched_twice(self):
        ticket = T("owner/shared", 1)
        r, calls = self.run_policy({"a": S("a", (ticket,), 1, True),
                                   "b": S("b", (ticket,), 1, True)}, 3)
        self.assertEqual(len(calls), 1)
        self.assertEqual(r.charged_slots, 1)

    def test_no_projects_is_not_queue_drained(self):
        r, _ = self.run_policy({})
        self.assertEqual(r.queue_observation, "NO_REGISTERED_PROJECTS")
        self.assertFalse(r.scan_complete)

    def test_rejects_invalid_max(self):
        for value in (0, -1, True, "3"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.run_policy({}, max_tickets=value)

    def test_rejects_invalid_identity(self):
        for repo, number in (("x", 1), ("a/b/c", 1), ("a/b", True), ("a/b", 0)):
            with self.subTest(repo=repo, number=number), self.assertRaises(ValueError):
                T(repo, number)

    def test_rejects_duplicate_project_and_scan_mismatch(self):
        for projects in (("a", "a"), ("a",)):
            with self.subTest(projects=projects), self.assertRaises(ValueError):
                policy.run_fleet_policy(projects, max_tickets=1,
                    scan=lambda p: complete("wrong"), attempt=lambda *a: A(AS.STARTED, "ok"))

    def test_rejects_invalid_scan_contract(self):
        with self.assertRaises(ValueError):
            S("a", complete=True)
        with self.assertRaises(ValueError):
            S("a", (T("owner/a", 1),), 0, True)
        with self.assertRaises(ValueError):
            S("a", complete=False)

    def test_started_failure_still_consumes_attempt_budget(self):
        r, calls = self.run_policy({"a": complete("a", 1, 2)}, dispositions={
            ("a", 1): A(AS.STARTED, "review_failed_retry_recorded")})
        self.assertEqual(calls, [("a", 1)])
        self.assertEqual(r.charged_slots, 1)


if __name__ == "__main__":
    unittest.main()
