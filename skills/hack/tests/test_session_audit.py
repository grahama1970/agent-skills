"""Tests for the plan-driven /hack session-audit workflow."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hack.session_audit import (  # noqa: E402
    CommandResult,
    ProbeRunConfig,
    SessionPaths,
    build_command_injection_probe_context,
    default_docker_tool_plan,
    has_command_injection_candidate,
    infer_compose_port,
    infer_target_port,
    load_docker_tool_plan,
    build_session_dockerfile,
    materialize_target_compose_env,
    normalize_target_url_for_port,
    resolve_target_launch_plan,
    safe_slug,
    write_command_injection_probe_task,
    write_memory_payload,
    write_report,
)
from hack.chaos_campaign import (  # noqa: E402
    StrategySeedContext,
    build_chaos_probe_script,
    build_loop_contract,
    build_strategy_catalog,
    is_local_or_private_target,
    sample_strategy,
)


class SessionAuditPlanTests(unittest.TestCase):
    def test_default_plan_installs_required_security_tools(self) -> None:
        plan = default_docker_tool_plan(nuclei_version="3.4.10", include_nuclei=True)
        dockerfile = build_session_dockerfile(plan)

        self.assertIn("LABEL org.agent-skills.plan-driven-docker=\"true\"", dockerfile)
        self.assertIn("nmap", dockerfile)
        self.assertIn("semgrep==1.161.0", dockerfile)
        self.assertIn("bandit", dockerfile)
        self.assertIn("pip-audit", dockerfile)
        self.assertIn("safety", dockerfile)
        self.assertIn("nuclei_${NUCLEI_VERSION}_linux_amd64.zip", dockerfile)
        self.assertIn("COPY plan.json /opt/hack-plan/plan.json", dockerfile)

    def test_plan_file_controls_docker_contents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "base_image": "python:3.12-slim",
                        "apt_packages": ["masscan"],
                        "pip_packages": ["detect-secrets"],
                        "include_nuclei": False,
                        "nmap_scan_types": ["service"],
                    }
                )
            )
            plan = load_docker_tool_plan(
                plan_file=plan_path,
                extra_apt_packages=("dnsutils",),
                extra_pip_packages=("httpx",),
                nuclei_version="3.4.10",
                include_nuclei=True,
            )
            dockerfile = build_session_dockerfile(plan)

        self.assertEqual(plan.base_image, "python:3.12-slim")
        self.assertIn("masscan", plan.apt_packages)
        self.assertIn("dnsutils", plan.apt_packages)
        self.assertIn("detect-secrets", plan.pip_packages)
        self.assertIn("httpx", plan.pip_packages)
        self.assertFalse(plan.include_nuclei)
        self.assertNotIn("nuclei_", dockerfile)
        self.assertEqual(plan.nmap_scan_types, ("service",))

    def test_safe_slug_uses_repo_path(self) -> None:
        self.assertEqual(
            safe_slug("https://github.com/SasanLabs/VulnerableApp.git"),
            "sasanlabs-vulnerableapp",
        )

    def test_report_states_exploit_status_separately_from_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = SessionPaths(
                session_dir=root,
                scanner_dir=root / "scanner",
                target_dir=root / "target",
                repo_dir=root / "target" / "repo",
                reports_dir=root / "reports",
                logs_dir=root / "logs",
                templates_dir=root / "nuclei-templates",
            )
            for directory in (
                paths.scanner_dir,
                paths.target_dir,
                paths.repo_dir,
                paths.reports_dir,
                paths.logs_dir,
                paths.templates_dir,
            ):
                directory.mkdir(parents=True)
            (paths.reports_dir / "semgrep.json").write_text(
                json.dumps(
                    {
                        "results": [
                            {
                                "check_id": "opt.hack-rules.java-runtime-exec",
                                "path": "/scan/src/CommandInjection.java",
                                "start": {"line": 45},
                                "extra": {
                                    "severity": "ERROR",
                                    "message": "Command execution sink detected.",
                                },
                            }
                        ]
                    }
                )
            )
            report = write_report(
                paths=paths,
                repo_url="https://github.com/SasanLabs/VulnerableApp.git",
                target_url="http://127.0.0.1",
                metadata={"origin": "origin", "head": "abc123"},
                semgrep_result=CommandResult((), 0, "", ""),
                compose_up_result=CommandResult((), 0, "", ""),
                service_scan_result=CommandResult((), 0, "", ""),
                vuln_scan_result=CommandResult((), 0, "", ""),
                nuclei_result=None,
                compose_down_result=CommandResult((), 0, "", ""),
                docker_plan=default_docker_tool_plan(
                    nuclei_version="3.4.10", include_nuclei=False
                ),
            )

            text = report.read_text()

        self.assertIn("## Answer", text)
        self.assertIn("- Proven exploit found: `false`", text)
        self.assertIn("- Exploit proof status: `not_attempted`", text)
        self.assertIn("Command execution candidate", text)
        self.assertIn("Treat this as a vulnerability assessment report.", text)

    def test_report_promotes_successful_proof(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = SessionPaths(
                session_dir=root,
                scanner_dir=root / "scanner",
                target_dir=root / "target",
                repo_dir=root / "target" / "repo",
                reports_dir=root / "reports",
                logs_dir=root / "logs",
                templates_dir=root / "nuclei-templates",
            )
            for directory in (
                paths.scanner_dir,
                paths.target_dir,
                paths.repo_dir,
                paths.reports_dir,
                paths.logs_dir,
                paths.templates_dir,
                paths.session_dir / "attacks",
            ):
                directory.mkdir(parents=True)
            (paths.reports_dir / "semgrep.json").write_text('{"results":[]}')
            (paths.session_dir / "attacks" / "proof.command-injection.json").write_text(
                json.dumps(
                    {
                        "status": "proved",
                        "indicator": "linux_id_output",
                        "url": "http://127.0.0.1/VulnerableApp/CommandInjection/LEVEL_1?ipaddress=127.0.0.1+%7C+id",
                        "evidence_excerpt": '{"content":"uid=0(root) gid=0(root) groups=0(root)\\n","isValid":true}',
                    }
                )
            )
            code_runner_dir = paths.session_dir / "code-runner"
            code_runner_dir.mkdir()
            (code_runner_dir / "probe-command-injection.result.json").write_text(
                json.dumps(
                    {
                        "task_id": "probe-command-injection",
                        "title": "Generate bounded command-injection proof probe",
                        "backend": "codex",
                        "status": "pass",
                        "dod_passed": True,
                        "rounds": 1,
                        "best_score": 1.0,
                    }
                )
            )
            (paths.logs_dir / "probe-command-injection.exit-code").write_text("0\n")
            (paths.logs_dir / "probe-command-injection.stderr.log").write_text(
                "proof found: linux_id_output\n"
            )
            report = write_report(
                paths=paths,
                repo_url="https://github.com/SasanLabs/VulnerableApp.git",
                target_url="http://127.0.0.1",
                metadata={"origin": "origin", "head": "abc123"},
                semgrep_result=CommandResult((), 0, "", ""),
                compose_up_result=CommandResult((), 0, "", ""),
                service_scan_result=CommandResult((), 0, "", ""),
                vuln_scan_result=CommandResult((), 0, "", ""),
                nuclei_result=None,
                compose_down_result=CommandResult((), 0, "", ""),
                docker_plan=default_docker_tool_plan(
                    nuclei_version="3.4.10", include_nuclei=False
                ),
            )

            text = report.read_text()

        self.assertIn("- Proven exploit found: `true`", text)
        self.assertIn("- Exploit proof status: `attempted_success`", text)
        self.assertIn("successful exploitation proof report", text)
        self.assertIn("## What Code-Runner Did", text)
        self.assertIn("- Task: `probe-command-injection`", text)
        self.assertIn("  - DoD passed: `true`", text)
        self.assertIn("## What Hack Executed", text)
        self.assertIn("- Did `$code-runner` run the exploit? `false`", text)
        self.assertIn("- Did `$hack` run the exploit in Docker? `true`", text)
        self.assertIn("- Probe executed: `true`", text)
        self.assertIn("- Exit code: `0`", text)
        self.assertIn("operating-system identity output", text)
        self.assertNotIn("uid=0(root)", text)

    def test_command_injection_probe_candidate_detection(self) -> None:
        self.assertTrue(
            has_command_injection_candidate(
                [{"check_id": "opt.hack-rules.java-runtime-exec"}]
            )
        )
        self.assertFalse(
            has_command_injection_candidate(
                [{"check_id": "opt.hack-rules.java-file-path-sink"}]
            )
        )

    def test_probe_task_is_bounded_and_code_runner_owned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = SessionPaths(
                session_dir=root,
                scanner_dir=root / "scanner",
                target_dir=root / "target",
                repo_dir=root / "target" / "repo",
                reports_dir=root / "reports",
                logs_dir=root / "logs",
                templates_dir=root / "nuclei-templates",
            )
            workspace = root / "attack-workspace"
            for directory in (
                paths.scanner_dir,
                paths.target_dir,
                paths.repo_dir,
                paths.reports_dir,
                paths.logs_dir,
                paths.templates_dir,
                workspace,
            ):
                directory.mkdir(parents=True)
            task_path = write_command_injection_probe_task(
                paths=paths,
                workspace=workspace,
                probe_config=ProbeRunConfig(
                    enabled=True,
                    code_runner_run=Path("/code-runner/run.sh"),
                    max_rounds=2,
                ),
            )

            task = json.loads(task_path.read_text())

        self.assertEqual(task["task_id"], "probe-command-injection")
        self.assertEqual(task["allowlist"], ["attacks/probe_command_injection.py"])
        self.assertEqual(task["dirty_worktree_policy"], "isolated_worktree")
        self.assertFalse(task["apply_to_source"])
        self.assertEqual(task["max_rounds"], 2)
        self.assertIn("py_compile", task["definition_of_done"]["command"])

    def test_probe_context_is_local_and_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = SessionPaths(
                session_dir=root,
                scanner_dir=root / "scanner",
                target_dir=root / "target",
                repo_dir=root / "target" / "repo",
                reports_dir=root / "reports",
                logs_dir=root / "logs",
                templates_dir=root / "nuclei-templates",
            )
            context = build_command_injection_probe_context(paths, "http://127.0.0.1")

        self.assertIn("loopback/local", context)
        self.assertIn("/VulnerableApp/CommandInjection/LEVEL_{level}", context)
        self.assertNotIn("| id", context)
        self.assertNotIn("/etc/passwd", context)

    def test_memory_payload_records_exploit_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = SessionPaths(
                session_dir=root,
                scanner_dir=root / "scanner",
                target_dir=root / "target",
                repo_dir=root / "target" / "repo",
                reports_dir=root / "reports",
                logs_dir=root / "logs",
                templates_dir=root / "nuclei-templates",
            )
            for directory in (
                paths.scanner_dir,
                paths.target_dir,
                paths.repo_dir,
                paths.reports_dir,
                paths.logs_dir,
                paths.templates_dir,
                paths.session_dir / "attacks",
            ):
                directory.mkdir(parents=True)
            (paths.session_dir / "attacks" / "proof.command-injection.json").write_text(
                '{"status":"proved"}'
            )
            report = paths.reports_dir / "HACK_REPORT.md"
            report.write_text("# report\n")

            write_memory_payload(paths, report)
            payload = json.loads((paths.reports_dir / "memory-payload.json").read_text())

        self.assertTrue(payload["exploit_proven"])
        self.assertEqual(payload["exploit_status"], "attempted_success")
        self.assertIn(str(paths.session_dir / "attacks"), payload["artifacts"])

    def test_openclaw_style_dockerfile_generates_launch_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = SessionPaths(
                session_dir=root,
                scanner_dir=root / "scanner",
                target_dir=root / "target",
                repo_dir=root / "target" / "repo",
                reports_dir=root / "reports",
                logs_dir=root / "logs",
                templates_dir=root / "nuclei-templates",
            )
            for directory in (
                paths.scanner_dir,
                paths.target_dir,
                paths.repo_dir,
                paths.reports_dir,
                paths.logs_dir,
                paths.templates_dir,
            ):
                directory.mkdir(parents=True)
            (paths.repo_dir / "Dockerfile").write_text(
                "HEALTHCHECK CMD node -e \"fetch('http://127.0.0.1:18789/healthz')\"\n"
                "CMD [\"node\", \"openclaw.mjs\", \"gateway\", \"--allow-unconfigured\"]\n"
            )

            launch_plan = resolve_target_launch_plan(
                paths=paths,
                requested_compose_file="docker-compose.without_llm.yml",
                requested_target_url="http://127.0.0.1",
                requested_port="80",
            )

            self.assertEqual(launch_plan.source, "generated-dockerfile-compose")
            self.assertEqual(launch_plan.port, "18789")
            self.assertEqual(launch_plan.target_url, "http://127.0.0.1:18789")
            self.assertTrue(launch_plan.compose_path.exists())

    def test_target_port_and_url_inference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "Dockerfile").write_text(
                "HEALTHCHECK CMD curl http://127.0.0.1:18789/healthz\n"
            )

            port = infer_target_port(repo, fallback="80")

        self.assertEqual(port, "18789")
        self.assertEqual(
            normalize_target_url_for_port("http://127.0.0.1", port),
            "http://127.0.0.1:18789",
        )
        self.assertEqual(
            normalize_target_url_for_port("http://127.0.0.1:3000", port),
            "http://127.0.0.1:3000",
        )

    def test_compose_port_inference_prefers_openclaw_gateway(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            compose = Path(tmp) / "docker-compose.yml"
            compose.write_text(
                "services:\n"
                "  openclaw-gateway:\n"
                "    ports:\n"
                "      - \"${OPENCLAW_GATEWAY_PORT:-18789}:18789\"\n"
            )

            port = infer_compose_port(compose, fallback="80")

        self.assertEqual(port, "18789")

    def test_target_compose_env_isolates_openclaw_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = SessionPaths(
                session_dir=root,
                scanner_dir=root / "scanner",
                target_dir=root / "target",
                repo_dir=root / "target" / "repo",
                reports_dir=root / "reports",
                logs_dir=root / "logs",
                templates_dir=root / "nuclei-templates",
            )
            for directory in (
                paths.scanner_dir,
                paths.target_dir,
                paths.repo_dir,
                paths.reports_dir,
                paths.logs_dir,
                paths.templates_dir,
            ):
                directory.mkdir(parents=True)
            launch_plan = resolve_target_launch_plan(
                paths=paths,
                requested_compose_file="missing.yml",
                requested_target_url="http://127.0.0.1",
                requested_port="18789",
            )

            env = materialize_target_compose_env(
                paths=paths,
                launch_plan=launch_plan,
            )
            report = json.loads((paths.reports_dir / "target-compose-env.json").read_text())
            self.assertEqual(env["OPENCLAW_GATEWAY_PORT"], "18789")
            self.assertTrue(env["HOME"].startswith(str(root / "target-state")))
            self.assertTrue(env["OPENCLAW_CONFIG_DIR"].startswith(str(root / "target-state")))
            self.assertTrue(env["OPENCLAW_WORKSPACE_DIR"].startswith(str(root / "target-state")))
            self.assertTrue((root / "target-state" / "home").is_dir())
            self.assertTrue((root / "target-state" / "config").is_dir())
            self.assertTrue((root / "target-state" / "workspace").is_dir())
            seeded_config = json.loads(
                (root / "target-state" / "config" / "openclaw.json").read_text()
            )
            self.assertEqual(seeded_config["gateway"]["mode"], "local")
            self.assertEqual(seeded_config["gateway"]["port"], 18789)
            self.assertEqual(
                report["environment"]["OPENCLAW_CONFIG_DIR"],
                str(root / "target-state" / "config"),
            )

    def test_chaos_campaign_catalog_combines_uncommon_axes(self) -> None:
        catalog = build_strategy_catalog()

        self.assertIn("websocket-handshake", catalog["transports"])
        self.assertIn("spoof-loopback-forwarded-for", catalog["header_variants"])
        self.assertIn("json-command-tokens", catalog["body_variants"])
        self.assertIn("/tools/invoke", catalog["paths"])
        self.assertIn("dotdot", catalog["mutations"])
        self.assertIn("attempts.jsonl", build_chaos_probe_script())
        self.assertIn("classification", build_chaos_probe_script())
        self.assertIn("score_attempt", build_chaos_probe_script())

    def test_chaos_campaign_loop_contract_is_generation_zero_evolve_stage(self) -> None:
        contract = build_loop_contract(
            StrategySeedContext(
                target_url="http://127.0.0.1:18789",
                last_plan_summary="prior report",
                dogpile_summary="fresh research",
                scanner_findings_summary="scanner evidence",
            )
        )

        self.assertEqual(contract["lifecycle_stage"], "generation_zero_broad_exploration")
        self.assertEqual(contract["parent_lifecycle"], "adaptive_evolve_campaign")
        self.assertIn("proof_candidate", contract["scoring_classes"])

    def test_chaos_campaign_target_guard_defaults_to_local_private(self) -> None:
        self.assertTrue(is_local_or_private_target("http://127.0.0.1:18789"))
        self.assertTrue(is_local_or_private_target("http://192.168.1.4:8080"))
        self.assertTrue(is_local_or_private_target("http://10.2.3.4"))
        self.assertFalse(is_local_or_private_target("https://example.com"))

    def test_chaos_campaign_strategy_sampling_is_seed_replayable(self) -> None:
        import random

        left = sample_strategy(random.Random(1234))
        right = sample_strategy(random.Random(1234))

        self.assertEqual(left, right)


if __name__ == "__main__":
    unittest.main()
