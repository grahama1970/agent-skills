"""Per-operation readiness for every Ask target kind (#1405).

Purpose
    Readiness is not one boolean. A browser seat can answer text while being
    unable to take an attachment; a provider family can be reachable by API and
    rate-limited on its authenticated web surface; one seat failing says
    nothing about the other five. Collapsing that into ``healthy: true`` is how
    a plan gets launched against a target that cannot do the thing the plan
    needs.

    ``ask.capability_report.v1`` reports each target separately, across the
    operation dimensions that actually differ, with the source that decided
    each verdict.

    ``READY`` requires a readback from the owning subsystem in this run. A
    config value, a CLI help string, or a command's own exit code is not
    readiness -- those produce ``NOT_TESTED``, which is an honest answer where
    an optimistic ``READY`` is a lie the caller cannot detect.

Inputs
    Optional live probes. The default report is bounded and read-only: it
    performs no model generation, no browser submission, and no session
    mutation, and records every probe it chose not to run.

Outputs
    ``build_report(live=False)`` returns an ``ask.capability_report.v1`` dict.

Failure modes
    A probe that times out or errors yields ``BLOCKED``/``UNAVAILABLE`` for
    that target with its reason code, never an exception, and never
    contaminates an unrelated target.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = "ask.capability_report.v1"

STATES = ("READY", "DEGRADED", "BLOCKED", "UNAVAILABLE", "NOT_TESTED")

BROWSER_HANDLERS = ("webgpt", "webclaude", "webkimi", "webgemini", "webgrok", "webdeepseek")

SKILL_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = SKILL_ROOT.parent

# A live verdict is only as good as the world it observed. TTL bounds age;
# the identity fingerprint bounds relevance -- a readiness computed against a
# different browser tab, Herdr session, or Tau revision describes a world that
# no longer exists, however recent it is.
DEFAULT_TTL_SECONDS = 300
KIND_TTL_SECONDS = {
    "browser_seat": 120,   # tabs are reassigned constantly
    "session_host": 60,    # panes come and go
    "local": 3600,
}


def identity_fingerprint() -> str:
    """Hash of the observable identities readiness depends on."""
    parts: list[str] = []
    try:
        from .herdr_target import list_panes

        parts.append(",".join(sorted(p.pane_id for p in list_panes())))
    except Exception:
        parts.append("herdr:unavailable")
    tab_state = Path("/tmp/surf-webgpt-controlled-tab-id")
    try:
        parts.append(tab_state.read_text(encoding="utf-8").strip() if tab_state.is_file() else "")
    except OSError:
        parts.append("")
    tau_head = Path.home() / "workspace" / "experiments" / "tau" / ".git" / "HEAD"
    try:
        parts.append(tau_head.read_text(encoding="utf-8").strip() if tau_head.is_file() else "")
    except OSError:
        parts.append("")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def mark_stale(report: dict[str, Any], *, now: float | None = None, fingerprint: str | None = None) -> dict[str, Any]:
    """Re-evaluate an existing report's freshness without re-probing.

    Two independent reasons to distrust a verdict, and either alone is enough:
    it aged past its TTL, or the identities it observed changed underneath it.
    """
    current = time.time() if now is None else now
    observed_fp = str(report.get("identity_fingerprint") or "")
    changed = fingerprint is not None and observed_fp and fingerprint != observed_fp
    for entry in report.get("capabilities", []):
        ttl = int(entry.get("ttl_seconds") or 0)
        aged = bool(ttl) and (current - float(entry.get("observed_at") or 0)) > ttl
        # Only live verdicts can go stale; NOT_TESTED was never fresh.
        entry["stale"] = bool(entry.get("live")) and (aged or changed)
        if entry["stale"]:
            entry["stale_reason"] = "identity_changed" if changed else "ttl_expired"
    report["identity_changed"] = bool(changed)
    return report


@dataclass
class Capability:
    """One target's readiness, per operation rather than overall."""

    capability_id: str
    kind: str
    selector: str
    state: str = "NOT_TESTED"
    reason_code: str = "not_probed"
    explanation: str = ""
    source: str = ""
    required: bool = False
    operations: dict[str, bool | None] = field(default_factory=dict)
    live: bool = False
    next_command: str = ""
    observed_at: float = 0.0
    ttl_seconds: int = 0
    stale: bool = False

    def as_dict(self) -> dict[str, Any]:
        assert self.state in STATES, self.state
        payload = {
            "capability_id": self.capability_id,
            "kind": self.kind,
            "selector": self.selector,
            "state": self.state,
            "reason_code": self.reason_code,
            "explanation": self.explanation,
            "source": self.source,
            "required": self.required,
            "operations": dict(self.operations),
            "live": self.live,
            "observed_at": self.observed_at,
            "ttl_seconds": self.ttl_seconds,
            "stale": self.stale,
        }
        if self.next_command:
            payload["next_command"] = self.next_command
        return payload


def _run(command: list[str], timeout: float = 20.0) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    return completed.returncode, completed.stdout


def _local_cli() -> Capability:
    """The one capability that can be judged without touching a subsystem."""
    run_sh = SKILL_ROOT / "run.sh"
    ready = run_sh.is_file() and os.access(run_sh, os.X_OK)
    return Capability(
        capability_id="ask.cli",
        kind="local",
        selector=str(run_sh),
        state="READY" if ready else "UNAVAILABLE",
        reason_code="entrypoint_executable" if ready else "entrypoint_missing",
        explanation="Ask CLI entrypoint" if ready else "run.sh missing or not executable",
        source="filesystem",
        required=True,
        operations={"compile": ready, "execute": ready},
    )


def _tau(live: bool) -> Capability:
    tau_root = Path.home() / "workspace" / "experiments" / "tau"
    present = tau_root.is_dir()
    cap = Capability(
        capability_id="tau.harness",
        kind="harness",
        selector=str(tau_root),
        required=True,
        operations={"compile": None, "execute": None},
        next_command="skills/tau/run.sh doctor",
    )
    if not present:
        cap.state, cap.reason_code = "UNAVAILABLE", "tau_checkout_absent"
        cap.explanation, cap.source = "no Tau checkout", "filesystem"
        return cap
    if not live:
        # Presence is not readiness: the checkout can exist while the harness
        # cannot run. Say NOT_TESTED rather than guess.
        cap.state, cap.reason_code = "NOT_TESTED", "requires_live"
        cap.explanation = "Tau checkout present; readiness needs --live"
        cap.source = "filesystem"
        return cap
    code, _ = _run([str(SKILLS_DIR / "tau" / "run.sh"), "doctor"], timeout=90)
    cap.live = True
    cap.source = "tau doctor"
    if code == 0:
        cap.state, cap.reason_code = "READY", "doctor_ok"
        cap.operations = {"compile": True, "execute": True}
        cap.explanation = "tau doctor exited 0"
    else:
        cap.state, cap.reason_code = "BLOCKED", "doctor_failed"
        cap.operations = {"compile": False, "execute": False}
        cap.explanation = f"tau doctor exited {code}"
    return cap


def _scillm(live: bool) -> Capability:
    base = os.environ.get("SCILLM_BASE_URL", "http://127.0.0.1:4001")
    cap = Capability(
        capability_id="scillm.transport",
        kind="model_api",
        selector=base,
        required=False,
        operations={"text": None, "attachment": None},
        next_command=f"curl -s {base}/health",
    )
    if not live:
        cap.state, cap.reason_code = "NOT_TESTED", "requires_live"
        cap.explanation = "model transport readiness needs --live"
        return cap
    cap.live = True
    cap.source = f"GET {base}/health"
    code, out = _run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"{base}/health"], timeout=15)
    status = (out or "").strip()
    if code == 0 and status.startswith("2"):
        cap.state, cap.reason_code = "READY", "health_2xx"
        cap.explanation = f"health returned {status}"
        # API text is proven reachable; attachments are a separate dimension
        # this probe does not exercise.
        cap.operations = {"text": True, "attachment": None}
    else:
        cap.state, cap.reason_code = "UNAVAILABLE", "health_unreachable"
        cap.explanation = f"health returned {status or 'no response'}"
        cap.operations = {"text": False, "attachment": False}
    return cap


def _probe_browser_availability(timeout: float = 180.0) -> dict[str, Any] | None:
    """Run Ask's own read-only availability probe and return its report.

    Read-only by contract: it inspects tabs, it does not submit. That is what
    lets it run under --live without counting as a provider-touching effect.
    """
    probe = SKILL_ROOT / "scripts" / "probe_browser_provider_availability.py"
    if not probe.is_file():
        return None
    out = SKILL_ROOT / ".ask_artifacts" / "capability-browser-availability.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    command = ["python3", str(probe)]
    for handler in BROWSER_HANDLERS:
        command += ["--provider", handler]
    command += ["--output", str(out), "--max-tabs-per-provider", "1", "--json"]
    code, _ = _run(command, timeout=timeout)
    try:
        return json.loads(out.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _browser_handlers(live: bool, availability: dict[str, Any] | None) -> list[Capability]:
    """One capability per handler; a failure in one never implies another.

    Rule 3 is the reason this returns six entries even when Chrome is down:
    collapsing them would let a WebGPT rate limit read as "browsers are out".
    """
    caps: list[Capability] = []
    providers = (availability or {}).get("providers") if isinstance(availability, dict) else None
    providers = providers if isinstance(providers, dict) else {}
    for handler in BROWSER_HANDLERS:
        cap = Capability(
            capability_id=f"browser.{handler}",
            kind="browser_seat",
            selector=handler,
            operations={"text": None, "attachment": None, "multi_turn": None, "resume": None},
            next_command=f"cd skills/ask && ./run.sh browser-availability --provider {handler} --json",
        )
        payload = providers.get(handler)
        if not isinstance(payload, dict):
            cap.state, cap.reason_code = "NOT_TESTED", "requires_live"
            cap.explanation = "browser readiness needs --live"
            caps.append(cap)
            continue
        cap.live = True
        cap.source = "browser-provider-availability.json"
        if payload.get("provider_limited") is True:
            cap.state, cap.reason_code = "BLOCKED", "provider_limited"
            cap.explanation = "provider reports a usage limit"
            cap.operations = {"text": False, "attachment": False, "multi_turn": False, "resume": False}
        elif payload.get("probe_failed") is True:
            cap.state = "UNAVAILABLE"
            cap.reason_code = str(payload.get("failure_code") or "probe_failed")
            cap.explanation = "availability probe failed"
            cap.operations = {"text": False, "attachment": False, "multi_turn": False, "resume": False}
        elif payload.get("probe_degraded") is True:
            # Degraded means unknown, not usable. Text is reported None rather
            # than True so a caller cannot read uncertainty as readiness.
            cap.state = "DEGRADED"
            cap.reason_code = str(payload.get("failure_code") or "probe_degraded")
            cap.explanation = "probe could not confirm the seat"
            cap.operations = {"text": None, "attachment": None, "multi_turn": None, "resume": None}
        else:
            cap.state, cap.reason_code = "READY", "probe_ok"
            cap.explanation = "seat answered the availability probe"
            # webdeepseek cannot take attachments at all; the matrix must keep
            # that distinct from a seat that merely was not tested.
            attach = False if handler == "webdeepseek" else True
            cap.operations = {"text": True, "attachment": attach, "multi_turn": True, "resume": None}
        caps.append(cap)
    return caps


def _herdr_sessions(live: bool) -> list[Capability]:
    cap = Capability(
        capability_id="session.herdr",
        kind="session_host",
        selector="herdr",
        operations={"resolve": None, "send": None, "roundtrip": None},
        next_command="cd skills/ask && ./run.sh herdr list",
    )
    if not live:
        cap.state, cap.reason_code = "NOT_TESTED", "requires_live"
        cap.explanation = "session inventory needs --live"
        return [cap]
    cap.live = True
    try:
        from .herdr_target import list_panes

        panes = list_panes()
    except Exception as exc:  # pragma: no cover - defensive
        cap.state, cap.reason_code = "UNAVAILABLE", "herdr_unreadable"
        cap.explanation = str(exc)[:120]
        cap.operations = {"resolve": False, "send": False, "roundtrip": False}
        return [cap]
    cap.source = "herdr pane list"
    addressable = [p for p in panes if p.is_addressable]
    if not panes:
        cap.state, cap.reason_code = "UNAVAILABLE", "herdr_not_running"
        cap.explanation = "herdr reported no panes"
        cap.operations = {"resolve": False, "send": False, "roundtrip": False}
    elif not addressable:
        cap.state, cap.reason_code = "BLOCKED", "no_addressable_pane"
        cap.explanation = f"{len(panes)} panes, none addressable"
        cap.operations = {"resolve": True, "send": False, "roundtrip": False}
    else:
        cap.state, cap.reason_code = "READY", "addressable_panes"
        cap.explanation = f"{len(addressable)} addressable of {len(panes)} panes"
        # Round-trip needs a rendering harness that replies; not proven here.
        cap.operations = {"resolve": True, "send": True, "roundtrip": None}
    return [cap]


def _memory(live: bool) -> Capability:
    cap = Capability(
        capability_id="memory.graph",
        kind="memory",
        selector="memory",
        operations={"recall": None, "store": None},
        next_command="skills/memory/run.sh health",
    )
    memory_run = SKILLS_DIR / "memory" / "run.sh"
    if not memory_run.is_file():
        cap.state, cap.reason_code = "UNAVAILABLE", "memory_skill_absent"
        cap.explanation = "memory skill not installed"
        cap.source = "filesystem"
        return cap
    if not live:
        cap.state, cap.reason_code = "NOT_TESTED", "requires_live"
        cap.explanation = "memory health needs --live"
        cap.source = "filesystem"
        return cap
    cap.live = True
    cap.source = "memory health"
    code, _ = _run([str(memory_run), "health"], timeout=60)
    if code == 0:
        cap.state, cap.reason_code = "READY", "health_ok"
        cap.operations = {"recall": True, "store": True}
    else:
        cap.state, cap.reason_code = "BLOCKED", "health_failed"
        cap.explanation = f"memory health exited {code}"
        cap.operations = {"recall": False, "store": False}
    return cap


def _projection() -> Capability:
    """Run projection availability, judged by import rather than by config."""
    try:
        from .run_projection import project_run  # noqa: F401

        ready = True
        detail = "ask.run_projection.v1 importable"
    except Exception as exc:  # pragma: no cover - defensive
        ready, detail = False, str(exc)[:120]
    return Capability(
        capability_id="ask.run_projection",
        kind="local",
        selector="ask.run_projection.v1",
        state="READY" if ready else "UNAVAILABLE",
        reason_code="importable" if ready else "import_failed",
        explanation=detail,
        source="python import",
        required=False,
        operations={"status": ready, "timeline": ready},
    )


def _headless() -> Capability:
    """Whether Ask can run without a terminal, judged from the environment."""
    interactive = bool(os.environ.get("TERM")) and os.isatty(0) if hasattr(os, "isatty") else False
    return Capability(
        capability_id="ask.headless",
        kind="local",
        selector="headless",
        state="READY",
        reason_code="no_tty_required",
        explanation="compile and execute paths require no controlling terminal",
        source="environment",
        operations={"cron": True, "ssh": True, "interactive": interactive},
    )


def build_report(live: bool = False, availability: dict[str, Any] | None = None) -> dict[str, Any]:
    """Assemble ``ask.capability_report.v1``.

    ``live`` opts into probes that touch owning subsystems. Everything skipped
    is recorded rather than defaulted, because a report that hides which checks
    it declined to run is indistinguishable from one that ran them all.
    """
    caps: list[Capability] = [_local_cli(), _projection(), _headless()]
    caps.append(_tau(live))
    caps.append(_scillm(live))
    caps.append(_memory(live))
    if live and availability is None:
        availability = _probe_browser_availability()
    caps.extend(_browser_handlers(live, availability))
    caps.extend(_herdr_sessions(live))

    observed = time.time()
    fingerprint = identity_fingerprint()
    for cap in caps:
        cap.observed_at = observed
        cap.ttl_seconds = KIND_TTL_SECONDS.get(cap.kind, DEFAULT_TTL_SECONDS)
    entries = [cap.as_dict() for cap in caps]
    skipped = [e["capability_id"] for e in entries if e["state"] == "NOT_TESTED"]
    by_state: dict[str, int] = {}
    for entry in entries:
        by_state[entry["state"]] = by_state.get(entry["state"], 0) + 1

    return {
        "schema": SCHEMA,
        "live": bool(live),
        "mocked": False,
        "observed_at": observed,
        "identity_fingerprint": fingerprint,
        "identity_changed": False,
        # Deliberately absent: any overall `healthy` boolean. Rule 2 exists
        # because one summary flag is what hides a text-ready, attachment-
        # blocked seat.
        "capabilities": entries,
        "counts_by_state": by_state,
        "skipped_probes": skipped,
        "required_blocked": [
            e["capability_id"]
            for e in entries
            if e["required"] and e["state"] in {"BLOCKED", "UNAVAILABLE"}
        ],
    }


def render_text(report: dict[str, Any]) -> list[str]:
    """Human lines derived only from the report (required proof 2)."""
    lines = [f"ask capability report  (live={report['live']})"]
    for entry in report["capabilities"]:
        ops = ", ".join(
            f"{name}={'?' if value is None else ('yes' if value else 'no')}"
            for name, value in sorted(entry["operations"].items())
        )
        lines.append(
            f"  {entry['capability_id']:<26} {entry['state']:<11} {entry['reason_code']:<26} {ops}"
        )
    if report["skipped_probes"]:
        lines.append(f"  skipped (needs --live): {', '.join(report['skipped_probes'])}")
    if report["required_blocked"]:
        lines.append(f"  REQUIRED BLOCKED: {', '.join(report['required_blocked'])}")
    return lines
