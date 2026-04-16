"""Tier 3: Integration Smoke Tests (detect + dispatch).

P20 persona-smoke-test — Run memory.recall() per persona to verify
    end-to-end pipeline returns recent content.

Inputs: memory-agent CLI, persona scopes.
Outputs: ProbeResult. On failure, dispatches bug via agent-inbox.
"""
from __future__ import annotations
import os

import json
import subprocess

from loguru import logger

import config
from probes import ProbeResult, ProbeStatus, register_probe

# Scope mapping for personas
_PERSONA_SCOPES = {
    "horus": "horus_persona",
    "embry": "embry_persona",
    "brandon_bailey": "brandon_bailey",
    "margaret_chen": "margaret_chen",
    "jennifer_cheung": "jennifer_cheung",
}


@register_probe("P20", "persona-smoke-test", tier=3)
def probe_persona_smoke_test(autofix: bool = False) -> ProbeResult:
    """Run memory.recall() per persona, check recent content exists."""
    results = {}
    failures = []

    for persona in config.PERSONAS_ALL:
        scope = _PERSONA_SCOPES.get(persona, persona)
        try:
            proc = subprocess.run(
                [
                    "memory-agent", "recall",
                    "--q", "what did I learn today",
                    "--scope", scope,
                    "--k", "3",
                ],
                capture_output=True, text=True, timeout=30,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            if proc.returncode == 0 and proc.stdout.strip():
                results[persona] = "ok"
            else:
                results[persona] = "empty"
                failures.append(persona)
        except FileNotFoundError:
            return ProbeResult(
                probe_id="P20", name="persona-smoke-test", tier=3,
                status=ProbeStatus.SKIP,
                message="memory-agent not found in PATH",
                details={},
            )
        except subprocess.TimeoutExpired:
            results[persona] = "timeout"
            failures.append(persona)
        except OSError as e:
            results[persona] = f"error: {e}"
            failures.append(persona)

    if failures:
        _dispatch_bug_report(failures)

    status = ProbeStatus.PASS if not failures else ProbeStatus.FAIL

    return ProbeResult(
        probe_id="P20", name="persona-smoke-test", tier=3,
        status=status,
        message=f"{len(results) - len(failures)}/{len(results)} personas responded"
              + (f", failed: {', '.join(failures)}" if failures else ""),
        details={"results": results, "failures": failures},
    )


def _dispatch_bug_report(failed_personas: list[str]) -> None:
    """Send bug report via agent-inbox for failed personas."""
    inbox_sh = config.PROJECT_ROOT / ".pi/skills/agent-inbox/run.sh"
    if not inbox_sh.exists():
        logger.warning("agent-inbox not found, cannot dispatch bug report")
        return

    body = (
        f"Persona smoke test failed for: {', '.join(failed_personas)}. "
        "memory.recall() returned empty or timed out. "
        "Check memory pipeline, embedding service, and ArangoDB health."
    )

    try:
        subprocess.run(
            [
                str(inbox_sh), "send",
                "--type", "bug",
                "--from", "monitor-memory",
                "--subject", f"Smoke test failure: {', '.join(failed_personas)}",
                "--body", body,
            ],
            capture_output=True, text=True, timeout=15,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.error("Failed to dispatch bug report: {}", e)
