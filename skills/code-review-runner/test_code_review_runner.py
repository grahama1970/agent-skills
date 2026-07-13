from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import code_review_runner as runner
from models import ReviewSpec


class CodeReviewRunnerAuthTests(unittest.TestCase):
    def test_review_diff_contains_changes_after_base_ref(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "sample.py"
            with patch.object(runner.subprocess, "run") as run:
                run.return_value = Mock(returncode=0, stdout="+changed = True\n", stderr="")
                spec = ReviewSpec(
                    task_id="diff",
                    files=["sample.py"],
                    cwd=str(root),
                    base_ref="origin/main",
                )
                self.assertIn("+changed = True", runner._build_review_diff(spec))
            self.assertEqual(run.call_args.args[0][-1], "sample.py")

    def test_review_prompt_accepts_base_ref_without_prior_findings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spec = ReviewSpec(
                task_id="prompt",
                files=["sample.py"],
                cwd=temp_dir,
                base_ref="origin/main",
            )
            with patch.object(runner, "_build_review_diff", return_value="+changed = True"):
                prompt = runner._build_review_prompt(
                    spec,
                    {"sample.py": "changed = True\n"},
                    [],
                    None,
                )
        self.assertIn("Authoritative Change Set", prompt)
        self.assertIn("+changed = True", prompt)

    def test_scillm_call_sends_active_auth_and_caller_headers(self) -> None:
        response = Mock(status_code=200)
        response.raise_for_status.return_value = None
        response.json.return_value = {"choices": [{"message": {"content": "[]"}}]}

        with (
            patch.object(runner, "_resolve_scillm_api_key", return_value=("active-key", "test")),
            patch.object(runner.httpx, "post", return_value=response) as post,
        ):
            self.assertEqual(runner._call_scillm("review", "codex"), "[]")

        headers = post.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer active-key")
        self.assertEqual(headers["X-Caller-Skill"], "code-review-runner")
        request = post.call_args.kwargs["json"]
        self.assertEqual(request["model"], "gpt-5.5")
        self.assertNotIn("temperature", request)
        self.assertNotIn("max_tokens", request)

    def test_scillm_call_recovers_stale_environment_key_once(self) -> None:
        unauthorized = Mock(status_code=401)
        success = Mock(status_code=200)
        success.raise_for_status.return_value = None
        success.json.return_value = {"choices": [{"message": {"content": "[]"}}]}

        with (
            patch.object(
                runner,
                "_resolve_scillm_api_key",
                return_value=("stale-key", "env:SCILLM_PROXY_KEY"),
            ),
            patch.object(
                runner,
                "_resolve_scillm_api_key_from_docker",
                return_value=("active-key", "docker:proxy:SCILLM_MASTER_KEY"),
            ),
            patch.object(runner.httpx, "post", side_effect=[unauthorized, success]) as post,
        ):
            self.assertEqual(runner._call_scillm("review", "codex"), "[]")

        self.assertEqual(post.call_count, 2)
        self.assertEqual(
            post.call_args_list[1].kwargs["headers"]["Authorization"],
            "Bearer active-key",
        )

    def test_provider_failure_cannot_become_passing_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "sample.py"
            source.write_text("value = 1\n", encoding="utf-8")
            spec = ReviewSpec(
                task_id="provider-failure",
                files=["sample.py"],
                cwd=str(root),
                output_dir=str(root / "out"),
                max_rounds=1,
            )
            with (
                patch.object(runner, "_call_scillm", side_effect=runner.ScillmReviewError("401")),
                patch.object(runner, "run_all_validators", return_value=[]),
                patch.object(runner, "_recall_prior_reviews", return_value=""),
                patch.object(runner, "_learn_review", return_value=None),
            ):
                result = runner.run_review(spec)

            self.assertEqual(result.status, "error")
            self.assertEqual(result.score, 0.0)
            self.assertEqual(result.round_details[0]["error"], "401")
            persisted = json.loads(
                (root / "out" / "provider-failure.review-result.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(persisted["status"], "error")

    def test_malformed_provider_response_is_review_error(self) -> None:
        with self.assertRaisesRegex(runner.ScillmReviewError, "no JSON findings array"):
            runner._parse_findings("not structured review output")

    def test_suggested_fix_is_not_claimed_valid_without_application(self) -> None:
        finding = runner.Finding(
            severity="major",
            file="sample.py",
            line=1,
            description="example",
            suggested_fix="value = 2",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "sample.py").write_text("value = 1\n", encoding="utf-8")
            runner._validate_finding(finding, temp_dir, "true")
        self.assertFalse(finding.validated)
        self.assertIn("not applied", finding.validation_error)


if __name__ == "__main__":
    unittest.main()
