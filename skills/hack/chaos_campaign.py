"""Compatibility entrypoint for evolve-campaign generation-zero exploration."""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import typer
from rich.console import Console

from hack.self_improve_loop import ARTIFACT_ROOT
from hack.session_audit import safe_slug

console = Console()


@dataclass(frozen=True)
class ChaosStrategy:
    """One bounded chaos hardening probe strategy."""

    method: str
    path: str
    header_variant: str
    body_variant: str
    transport: str
    mutation: str


@dataclass(frozen=True)
class StrategySeedContext:
    """Grounding inputs that seed an uncommon-combination campaign."""

    target_url: str
    last_plan_summary: str
    dogpile_summary: str
    scanner_findings_summary: str


def create_chaos_campaign_command() -> Callable[..., None]:
    """Create the hidden compatibility command for broad evolve exploration."""

    def chaos_campaign(
        target_url: str = typer.Argument(..., help="Authorized local/private target base URL"),
        output_root: str = typer.Option(
            ARTIFACT_ROOT,
            help="Artifact root for chaos-campaign-* directories",
        ),
        duration_minutes: int = typer.Option(
            480,
            "--duration-minutes",
            help="Maximum campaign duration. Defaults to 8 hours for overnight runs.",
        ),
        max_attempts: int = typer.Option(
            10_000,
            "--max-attempts",
            help="Maximum bounded probe attempts before stopping.",
        ),
        seed: int | None = typer.Option(
            None,
            "--seed",
            help="Optional deterministic random seed for replaying a campaign.",
        ),
        docker_image: str = typer.Option(
            "python:3.11-slim",
            "--docker-image",
            help="Docker image used to execute the generated probe harness.",
        ),
        last_plan: str | None = typer.Option(
            None,
            "--last-plan",
            help="Path to prior /hack plan/report JSON/Markdown used as campaign seed material.",
        ),
        dogpile_report: str | None = typer.Option(
            None,
            "--dogpile-report",
            help="Path to /dogpile Markdown/HTML research synthesis used as campaign seed material.",
        ),
        scanner_findings: str | None = typer.Option(
            None,
            "--scanner-findings",
            help="Path to scanner findings JSON/Markdown used as campaign seed material.",
        ),
        allow_nonlocal: bool = typer.Option(
            False,
            "--allow-nonlocal",
            help="Allow non-loopback/non-private targets. Requires explicit authorization.",
        ),
    ) -> None:
        """Run generation-zero broad exploration for the evolve lifecycle."""

        console.print(
            "[yellow]chaos-campaign is a compatibility entrypoint for evolve-campaign "
            "generation-zero exploration; the three top-level /hack modes are "
            "session-audit, evolve-campaign, and battle.[/yellow]"
        )
        campaign = run_chaos_campaign(
            target_url=target_url,
            output_root=Path(output_root),
            duration_minutes=duration_minutes,
            max_attempts=max_attempts,
            seed=seed,
            docker_image=docker_image,
            last_plan=Path(last_plan) if last_plan else None,
            dogpile_report=Path(dogpile_report) if dogpile_report else None,
            scanner_findings=Path(scanner_findings) if scanner_findings else None,
            allow_nonlocal=allow_nonlocal,
        )
        console.print(f"[green]Chaos campaign artifacts:[/green] {campaign}")

    return chaos_campaign


def run_chaos_campaign(
    *,
    target_url: str,
    output_root: Path,
    duration_minutes: int,
    max_attempts: int,
    seed: int | None,
    docker_image: str,
    last_plan: Path | None = None,
    dogpile_report: Path | None = None,
    scanner_findings: Path | None = None,
    allow_nonlocal: bool,
) -> Path:
    """Materialize and run broad exploration for the evolve lifecycle."""

    if not shutil.which("docker"):
        raise RuntimeError("Docker is required for /hack evolve generation-zero exploration")
    if duration_minutes <= 0:
        raise ValueError("duration_minutes must be positive")
    if max_attempts <= 0:
        raise ValueError("max_attempts must be positive")
    if not allow_nonlocal and not is_local_or_private_target(target_url):
        raise ValueError(
            "evolve generation-zero exploration only targets loopback/private hosts by default; pass "
            "--allow-nonlocal only for explicitly authorized nonlocal systems"
        )

    campaign_id = "chaos-campaign-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    campaign_id += "-" + safe_slug(target_url)
    campaign_dir = output_root / campaign_id
    campaign_dir.mkdir(parents=True, exist_ok=True)
    seed_context = load_strategy_seed_context(
        target_url=target_url,
        last_plan=last_plan,
        dogpile_report=dogpile_report,
        scanner_findings=scanner_findings,
    )
    (campaign_dir / "strategies.seed.json").write_text(
        json.dumps(
            {
                "target_url": target_url,
                "lifecycle_stage": "generation_zero_broad_exploration",
                "parent_lifecycle": "adaptive_evolve_campaign",
                "scoring_model": "dead_end|false_positive|partial_signal|promising_parent|proof_candidate|blocked",
                "duration_minutes": duration_minutes,
                "max_attempts": max_attempts,
                "seed": seed,
                "docker_image": docker_image,
                "safety_boundary": "Docker-contained probes against authorized target only",
                "mutation_axes": build_strategy_catalog(),
                "next_evolve_seed_guidance": "Use scored generation-zero attempts as adaptive/evolve evidence; prune false positives, mutate promising parents, and reseed Dogpile from retained anomalies.",
                "last_plan_path": str(last_plan) if last_plan else None,
                "dogpile_report_path": str(dogpile_report) if dogpile_report else None,
                "scanner_findings_path": str(scanner_findings) if scanner_findings else None,
                "strategy_seed_context": {
                    "last_plan_summary": seed_context.last_plan_summary,
                    "dogpile_summary": seed_context.dogpile_summary,
                    "scanner_findings_summary": seed_context.scanner_findings_summary,
                },
            },
            indent=2,
        )
        + "\n"
    )
    (campaign_dir / "dogpile-hardening-research-prompt.md").write_text(
        build_dogpile_research_prompt(seed_context)
    )
    (campaign_dir / "loop-contract.json").write_text(
        json.dumps(build_loop_contract(seed_context), indent=2) + "\n"
    )
    probe_path = campaign_dir / "chaos_probe.py"
    probe_path.write_text(build_chaos_probe_script())
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network=host",
            "-v",
            f"{campaign_dir}:/campaign:rw",
            "-e",
            f"HACK_CHAOS_TARGET_URL={target_url}",
            "-e",
            f"HACK_CHAOS_DURATION_SECONDS={duration_minutes * 60}",
            "-e",
            f"HACK_CHAOS_MAX_ATTEMPTS={max_attempts}",
            "-e",
            f"HACK_CHAOS_SEED={seed if seed is not None else random.randrange(1, 2**31)}",
            docker_image,
            "python",
            "/campaign/chaos_probe.py",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    (campaign_dir / "chaos-docker.stdout.log").write_text(result.stdout)
    (campaign_dir / "chaos-docker.stderr.log").write_text(result.stderr)
    (campaign_dir / "chaos-docker.exit-code").write_text(f"{result.returncode}\n")
    if result.returncode not in {0, 2}:
        raise RuntimeError(f"chaos campaign failed; see {campaign_dir}")
    return campaign_dir


def is_local_or_private_target(target_url: str) -> bool:
    """Return whether target_url points at a loopback/private hostname."""

    host = urlparse(target_url).hostname or target_url
    host = host.strip("[]").lower()
    if host in {"localhost", "host.docker.internal"}:
        return True
    if host.startswith("127.") or host == "::1":
        return True
    private_patterns = (
        r"^10\.",
        r"^192\.168\.",
        r"^172\.(1[6-9]|2[0-9]|3[0-1])\.",
    )
    return any(re.match(pattern, host) for pattern in private_patterns)


def load_strategy_seed_context(
    *,
    target_url: str,
    last_plan: Path | None,
    dogpile_report: Path | None,
    scanner_findings: Path | None,
) -> StrategySeedContext:
    """Load bounded seed material from prior plan, dogpile, and scanner artifacts."""

    return StrategySeedContext(
        target_url=target_url,
        last_plan_summary=summarize_seed_file(last_plan),
        dogpile_summary=summarize_seed_file(dogpile_report),
        scanner_findings_summary=summarize_seed_file(scanner_findings),
    )


def summarize_seed_file(path: Path | None, *, max_chars: int = 8_000) -> str:
    """Return a compact seed summary from an optional artifact path."""

    if path is None:
        return "not provided"
    if not path.exists():
        return f"missing: {path}"
    text = path.read_text(errors="replace")
    if path.suffix.lower() == ".json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            if "results" in parsed and isinstance(parsed["results"], list):
                rows = []
                for item in parsed["results"][:80]:
                    if isinstance(item, dict):
                        rows.append(
                            " | ".join(
                                str(value)
                                for value in (
                                    item.get("check_id"),
                                    item.get("path"),
                                    item.get("start", {}).get("line")
                                    if isinstance(item.get("start"), dict)
                                    else None,
                                    item.get("extra", {}).get("message")
                                    if isinstance(item.get("extra"), dict)
                                    else None,
                                )
                                if value
                            )
                        )
                return "\n".join(rows)[:max_chars] or "json findings empty"
            return json.dumps(parsed, indent=2)[:max_chars]
    return text[:max_chars]


def build_dogpile_research_prompt(context: StrategySeedContext) -> str:
    """Build a best-practices-prompt-compliant dogpile query for campaign seeding."""

    return f"""# Purpose
Find hardening tactics that can seed `/hack evolve-campaign` generation-zero broad exploration against one authorized OpenClaw gateway instance.

# Consumer
The consumer is `/hack evolve-campaign`; the legacy `chaos-campaign` entrypoint only runs its broad generation-zero exploration phase.

# Why This Matters
The campaign intentionally tries many unlikely high-level and low-level combinations. One anomaly in thousands of attempts should be promoted into a focused proof probe and a blue-team patch task.

# Task
Research OpenClaw-like local AI gateway attack surfaces and return a hardening seed plan.

# Target
- Authorized target URL: `{context.target_url}`
- Execution boundary: Docker-contained probes against a local or private target only

# Grounding Inputs
## Last Plan Summary
```text
{context.last_plan_summary}
```

## Scanner Findings Summary
```text
{context.scanner_findings_summary}
```

## Prior Dogpile Summary
```text
{context.dogpile_summary}
```

# Required Research Coverage
Search current web, GitHub issues, GitHub code, advisories, and papers for tactics relevant to:
- High-level protocol flows: HTTP auth, WebSocket upgrade auth, OpenAI-compatible APIs, plugin routes, hook routes, session history/kill routes, local readiness and metrics routes.
- Low-level parser cases: percent-encoding, path traversal, malformed JSON, oversized bodies, oversized headers, method confusion, CORS/Origin variants, forwarded-header spoofing, connection resets, and slow-response triggers.
- Agent-specific risks: tool invocation authorization, node-host execution, PATH hijacking, secret reference resolution, workspace escape, plugin lifecycle, channel pairing, model-provider request forwarding, SSRF-like URL handling.
- Blue-team patch patterns: route allowlists, central auth gates, per-scope rate limits, body/header size limits, canonical path normalization, structured audit logs, crash-resilient error handling, regression tests.

# Output Requirements
Return Markdown with exactly these sections:
1. `## Campaign Genome` — 12-20 concrete mutation axes with why each axis is relevant.
2. `## High-Level Flow Strategies` — 8-12 protocol/auth combinations to randomize.
3. `## Low-Level Mutation Strategies` — 12-20 parser/header/body/path combinations to randomize.
4. `## Promotion Rules` — exact observable signals that convert a failed/random attempt into a focused proof probe.
5. `## Blue-Team Patch Queue` — prioritized patch tasks with affected route/function/file patterns.
6. `## Source Notes` — bullet list of source URLs or GitHub paths used.

# Rejection Criteria
Do not include generic advice without a concrete route, file pattern, header/body mutation, or promotion signal.
Do not include instructions for persistence, credential theft, external targeting, botnet behavior, or host escape.
If evidence is weak, mark it as `hypothesis` and state the exact Docker-contained observation needed to promote it.
"""


def build_loop_contract(context: StrategySeedContext) -> dict[str, object]:
    """Return the report→dogpile→campaign→promotion loop contract."""

    return {
        "purpose": "evolve-campaign generation-zero uncommon-combination exploration loop",
        "lifecycle_stage": "generation_zero_broad_exploration",
        "parent_lifecycle": "adaptive_evolve_campaign",
        "scoring_classes": ["dead_end", "false_positive", "partial_signal", "promising_parent", "proof_candidate", "blocked"],
        "rule": "chaos-campaign is a compatibility entrypoint into evolve-campaign generation zero, not a third top-level /hack mode",
        "target_url": context.target_url,
        "phases": [
            {
                "name": "report_previous_plan",
                "input_artifacts": [
                    "reports/HACK_REPORT.md",
                    "reports/semgrep.json",
                    "logs/nmap-service.log",
                    "logs/nmap-vuln.log",
                    "attacks/*.result.json",
                    "chaos-campaign-*/anomalies.jsonl",
                ],
                "output": "distilled finding and anomaly summary",
            },
            {
                "name": "dogpile_new_approaches",
                "input_artifacts": [
                    "distilled finding and anomaly summary",
                    "dogpile-hardening-research-prompt.md",
                ],
                "required_coverage": [
                    "current web",
                    "github code",
                    "github issues",
                    "advisories",
                    "papers",
                    "prior memory",
                ],
                "output": "research-backed campaign genome",
            },
            {
                "name": "run_randomized_campaign",
                "strategy": "combine high-level protocol/auth flows with low-level parser/header/body/path mutations",
                "output_artifacts": [
                    "attempts.jsonl",
                    "anomalies.jsonl",
                    "summary.json",
                ],
                "scoring": "every attempt records score, classification, and gate_decision",
            },
            {
                "name": "promote_anomalies",
                "promotion_signals": [
                    "HTTP 5xx",
                    "connection reset",
                    "unexpected unauthenticated 200",
                    "unauthenticated websocket 101",
                    "HTTP 429 absence after bounded auth failures",
                    "sensitive readiness or metrics disclosure",
                    "slow response above threshold",
                    "new container crash/restart",
                ],
                "output": "focused proof probe and blue-team patch task",
            },
            {
                "name": "iterate",
                "rule": "feed promoted anomaly summaries into the next dogpile query and campaign seed",
                "output": "next adaptive/evolve seed material",
            },
        ],
        "provided_seed_material": {
            "last_plan_summary_chars": len(context.last_plan_summary),
            "dogpile_summary_chars": len(context.dogpile_summary),
            "scanner_findings_summary_chars": len(context.scanner_findings_summary),
        },
    }


def build_strategy_catalog() -> dict[str, list[str]]:
    """Return the mutation axes used by the Docker probe harness."""

    return {
        "methods": ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        "paths": [
            "/",
            "/healthz",
            "/readyz",
            "/v1/models",
            "/v1/chat/completions",
            "/v1/responses",
            "/v1/embeddings",
            "/tools/invoke",
            "/sessions/main/history",
            "/sessions/main/kill",
            "/api/diagnostics/prometheus",
            "/__openclaw/control-ui-config.json",
            "/__openclaw/media/%2e%2e/%2e%2e/etc/passwd",
            "/%2e%2e/%2e%2e/etc/passwd",
            "/hooks/wake",
            "/hooks/agent",
        ],
        "header_variants": [
            "none",
            "invalid-bearer",
            "query-token",
            "spoof-loopback-forwarded-for",
            "spoof-private-forwarded-for",
            "json-content-type",
            "oversized-header",
            "evil-origin",
            "null-origin",
        ],
        "body_variants": [
            "empty",
            "json-empty",
            "json-tool",
            "json-path-traversal",
            "json-command-tokens",
            "oversized-json",
            "malformed-json",
        ],
        "transports": ["http", "websocket-handshake"],
        "mutations": [
            "plain",
            "double-slash",
            "encoded-slash",
            "dotdot",
            "case-flip",
            "query-cache-bust",
            "query-token",
        ],
    }


def sample_strategy(rng: random.Random) -> ChaosStrategy:
    """Sample one uncommon strategy combination."""

    catalog = build_strategy_catalog()
    return ChaosStrategy(
        method=rng.choice(catalog["methods"]),
        path=rng.choice(catalog["paths"]),
        header_variant=rng.choice(catalog["header_variants"]),
        body_variant=rng.choice(catalog["body_variants"]),
        transport=rng.choice(catalog["transports"]),
        mutation=rng.choice(catalog["mutations"]),
    )


def build_chaos_probe_script() -> str:
    """Return the Docker-executed randomized probe script."""

    return textwrap.dedent(
        r'''
        from __future__ import annotations

        import json
        import os
        import random
        import socket
        import time
        import urllib.error
        import urllib.parse
        import urllib.request
        from pathlib import Path

        TARGET = os.environ["HACK_CHAOS_TARGET_URL"].rstrip("/")
        DURATION_SECONDS = int(os.environ["HACK_CHAOS_DURATION_SECONDS"])
        MAX_ATTEMPTS = int(os.environ["HACK_CHAOS_MAX_ATTEMPTS"])
        SEED = int(os.environ["HACK_CHAOS_SEED"])
        OUT = Path("/campaign")
        RNG = random.Random(SEED)
        CATALOG = {
            "methods": ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            "paths": ["/", "/healthz", "/readyz", "/v1/models", "/v1/chat/completions", "/v1/responses", "/v1/embeddings", "/tools/invoke", "/sessions/main/history", "/sessions/main/kill", "/api/diagnostics/prometheus", "/__openclaw/control-ui-config.json", "/__openclaw/media/%2e%2e/%2e%2e/etc/passwd", "/%2e%2e/%2e%2e/etc/passwd", "/hooks/wake", "/hooks/agent"],
            "header_variants": ["none", "invalid-bearer", "query-token", "spoof-loopback-forwarded-for", "spoof-private-forwarded-for", "json-content-type", "oversized-header", "evil-origin", "null-origin"],
            "body_variants": ["empty", "json-empty", "json-tool", "json-path-traversal", "json-command-tokens", "oversized-json", "malformed-json"],
            "transports": ["http", "websocket-handshake"],
            "mutations": ["plain", "double-slash", "encoded-slash", "dotdot", "case-flip", "query-cache-bust", "query-token"],
        }

        def mutate_path(path, mutation):
            if mutation == "double-slash":
                return "//" + path.lstrip("/")
            if mutation == "encoded-slash":
                return path.replace("/", "%2f", 1) if path != "/" else "/%2f"
            if mutation == "dotdot":
                return "/safe/../.." + path
            if mutation == "case-flip":
                return "".join(ch.upper() if idx % 2 else ch.lower() for idx, ch in enumerate(path))
            if mutation == "query-cache-bust":
                return path + ("&" if "?" in path else "?") + f"cb={RNG.randrange(1_000_000)}"
            if mutation == "query-token":
                return path + ("&" if "?" in path else "?") + "token=invalid"
            return path

        def headers_for(variant, attempt):
            headers = {}
            if variant == "invalid-bearer":
                headers["Authorization"] = f"Bearer chaos-{attempt}"
            elif variant == "query-token":
                headers["X-OpenClaw-Token"] = f"chaos-{attempt}"
            elif variant == "spoof-loopback-forwarded-for":
                headers["X-Forwarded-For"] = "127.0.0.1"
                headers["X-Real-IP"] = "127.0.0.1"
            elif variant == "spoof-private-forwarded-for":
                headers["X-Forwarded-For"] = "10.0.0.9"
            elif variant == "json-content-type":
                headers["Content-Type"] = "application/json"
            elif variant == "oversized-header":
                headers["X-Chaos"] = "A" * 8192
            elif variant == "evil-origin":
                headers["Origin"] = "http://evil.invalid"
            elif variant == "null-origin":
                headers["Origin"] = "null"
            return headers

        def body_for(variant):
            if variant == "json-empty":
                return b"{}"
            if variant == "json-tool":
                return json.dumps({"tool": "gateway.status", "arguments": {}}).encode()
            if variant == "json-path-traversal":
                return json.dumps({"path": "../../etc/passwd", "sessionId": "../main"}).encode()
            if variant == "json-command-tokens":
                return json.dumps({"command": "id; uname -a", "args": [";id", "$(id)"]}).encode()
            if variant == "oversized-json":
                return json.dumps({"data": "A" * 250000}).encode()
            if variant == "malformed-json":
                return b'{"unterminated":'
            return None

        def content_type(result):
            headers = result.get("headers") or {}
            for key, value in headers.items():
                if str(key).lower() == "content-type":
                    return str(value).lower()
            return ""

        def is_spa_shell_fallback(result):
            body = str(result.get("body", "")).lstrip().lower()
            return "text/html" in content_type(result) and (
                body.startswith("<!doctype html")
                or body.startswith("<html")
                or "<title>openclaw control</title>" in body
            )

        def score_attempt(strategy, result):
            method, path, header_variant, body_variant, transport, mutation = strategy
            status = result.get("status")
            status_line = result.get("status_line", "")
            score = 0.0
            if isinstance(status, int) and status >= 500:
                score += 10.0
            if status == 200 and path not in {"/", "/healthz", "/readyz", "/__openclaw/control-ui-config.json"} and not is_spa_shell_fallback(result):
                score += 7.0
            if "101" in status_line:
                score += 9.0
            if result.get("error") in {"ConnectionResetError", "RemoteDisconnected", "ConnectionAbortedError"}:
                score += 6.0
            if result.get("elapsed_ms", 0) > 3000:
                score += 3.0
            if any(token in str(result.get("body", "")).lower() for token in ("secret", "token", "traceback", "exception", "stack")):
                score += 5.0
            return round(score, 3)

        def classify_attempt(strategy, result, reason):
            if is_spa_shell_fallback(result):
                return "false_positive"
            if reason is None:
                return "dead_end"
            if reason in {"server-error", "connection-reset", "slow-response"}:
                return "partial_signal"
            if reason in {"unexpected-unauthenticated-200", "unauthenticated-websocket-upgrade"}:
                return "proof_candidate" if result.get("reproduced") else "promising_parent"
            return "promising_parent"

        def http_probe(strategy, attempt):
            method, path, header_variant, body_variant, _transport, mutation = strategy
            path = mutate_path(path, mutation)
            body = body_for(body_variant)
            headers = headers_for(header_variant, attempt)
            if body is not None and "Content-Type" not in headers:
                headers["Content-Type"] = "application/json"
            req = urllib.request.Request(TARGET + path, data=body, method=method, headers=headers)
            started = time.time()
            try:
                with urllib.request.urlopen(req, timeout=4) as res:
                    raw = res.read(2048)
                    return {"status": res.status, "headers": dict(res.headers), "body": raw.decode("utf-8", "replace")[:300], "elapsed_ms": round((time.time() - started) * 1000, 2)}
            except urllib.error.HTTPError as exc:
                raw = exc.read(2048)
                return {"status": exc.code, "headers": dict(exc.headers), "body": raw.decode("utf-8", "replace")[:300], "elapsed_ms": round((time.time() - started) * 1000, 2)}
            except Exception as exc:
                return {"error": type(exc).__name__, "message": str(exc)[:300], "elapsed_ms": round((time.time() - started) * 1000, 2)}

        def websocket_probe(strategy, attempt):
            _method, path, header_variant, _body_variant, _transport, mutation = strategy
            url = urllib.parse.urlparse(TARGET)
            host = url.hostname or "127.0.0.1"
            port = url.port or (443 if url.scheme == "https" else 80)
            path = mutate_path(path, mutation)
            extra = headers_for(header_variant, attempt)
            started = time.time()
            try:
                with socket.create_connection((host, port), timeout=4) as sock:
                    sock.settimeout(4)
                    lines = [
                        f"GET {path} HTTP/1.1",
                        f"Host: {host}:{port}",
                        "Upgrade: websocket",
                        "Connection: Upgrade",
                        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==",
                        "Sec-WebSocket-Version: 13",
                    ]
                    lines.extend(f"{k}: {v}" for k, v in extra.items())
                    sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("ascii", "ignore"))
                    raw = sock.recv(2048)
                text = raw.decode("utf-8", "replace")
                return {"status_line": text.splitlines()[0] if text else "", "body": text[:300], "elapsed_ms": round((time.time() - started) * 1000, 2)}
            except Exception as exc:
                return {"error": type(exc).__name__, "message": str(exc)[:300], "elapsed_ms": round((time.time() - started) * 1000, 2)}

        def is_anomaly(strategy, result):
            method, path, header_variant, body_variant, transport, mutation = strategy
            status = result.get("status")
            status_line = result.get("status_line", "")
            if status is not None and status >= 500:
                return "server-error"
            if status == 200 and path not in {"/", "/healthz", "/readyz", "/__openclaw/control-ui-config.json"} and not is_spa_shell_fallback(result):
                return "unexpected-unauthenticated-200"
            if "101" in status_line:
                return "unauthenticated-websocket-upgrade"
            if result.get("error") in {"ConnectionResetError", "RemoteDisconnected"}:
                return "connection-reset"
            if result.get("elapsed_ms", 0) > 3000:
                return "slow-response"
            return None

        attempts_path = OUT / "attempts.jsonl"
        anomalies_path = OUT / "anomalies.jsonl"
        started = time.time()
        attempts = 0
        anomalies = 0
        with attempts_path.open("a") as attempts_file, anomalies_path.open("a") as anomalies_file:
            while attempts < MAX_ATTEMPTS and time.time() - started < DURATION_SECONDS:
                strategy = (
                    RNG.choice(CATALOG["methods"]),
                    RNG.choice(CATALOG["paths"]),
                    RNG.choice(CATALOG["header_variants"]),
                    RNG.choice(CATALOG["body_variants"]),
                    RNG.choice(CATALOG["transports"]),
                    RNG.choice(CATALOG["mutations"]),
                )
                result = websocket_probe(strategy, attempts) if strategy[4] == "websocket-handshake" else http_probe(strategy, attempts)
                reason = is_anomaly(strategy, result)
                score = score_attempt(strategy, result)
                classification = classify_attempt(strategy, result, reason)
                record = {
                    "attempt": attempts,
                    "lifecycle_stage": "generation_zero_broad_exploration",
                    "parent_lifecycle": "adaptive_evolve_campaign",
                    "strategy": strategy,
                    "result": result,
                    "score": score,
                    "classification": classification,
                    "gate_decision": "promote" if classification == "proof_candidate" and result.get("reproduced") else "retain" if reason else "record",
                    "anomaly": reason,
                }
                attempts_file.write(json.dumps(record, sort_keys=True) + "\n")
                attempts_file.flush()
                if reason:
                    anomalies += 1
                    anomalies_file.write(json.dumps(record, sort_keys=True) + "\n")
                    anomalies_file.flush()
                attempts += 1
        summary = {
            "target": TARGET,
            "seed": SEED,
            "lifecycle_stage": "generation_zero_broad_exploration",
            "parent_lifecycle": "adaptive_evolve_campaign",
            "attempts": attempts,
            "anomalies": anomalies,
            "duration_seconds": round(time.time() - started, 2),
            "next_step": "Use scored generation-zero attempts as adaptive/evolve seed evidence, then promote repeatable proof candidates into focused probes and blue-team patch tasks.",
        }
        (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary, indent=2))
        raise SystemExit(2 if anomalies else 0)
        '''
    ).lstrip()


__all__ = [
    "ChaosStrategy",
    "build_chaos_probe_script",
    "build_strategy_catalog",
    "create_chaos_campaign_command",
    "is_local_or_private_target",
    "run_chaos_campaign",
    "sample_strategy",
]
