"""Evidence-class vocabulary and the real-E2E qualification contract.

This module is the shared floor under claim readiness (#1445), the real-E2E
policy (#1446), and seam-coverage sufficiency (#1448). It answers one question
mechanically: *what does a given case actually prove?*

Deterministic tests prove mechanisms. Real E2Es prove capabilities. The whole
point of separating evidence classes is that a pile of deterministic cases can
never be counted as the live proof a critical operational claim requires. The
runner must not infer `live_e2e` from a command that merely contains `run.sh`
or `curl`: a case is live evidence only when it *declares* a live class AND
structurally satisfies the real-E2E contract below. A case that declares live
but fails the contract is reclassified down, never rejected silently -- the
report says exactly why it did not count as live.
"""

from __future__ import annotations

from typing import Any

# Canonical evidence classes (issue #1445). Ordered weakest -> strongest live.
DETERMINISTIC = "deterministic"
PROPERTY_OR_FUZZ = "property_or_fuzz"
FAULT_INJECTED_DETERMINISTIC = "fault_injected_deterministic"
LIVE_E2E = "live_e2e"
ADVERSARIAL_LIVE_E2E = "adversarial_live_e2e"
HUMAN_EVALUATION = "human_evaluation"

EVIDENCE_CLASSES = frozenset(
    {
        DETERMINISTIC,
        PROPERTY_OR_FUZZ,
        FAULT_INJECTED_DETERMINISTIC,
        LIVE_E2E,
        ADVERSARIAL_LIVE_E2E,
        HUMAN_EVALUATION,
    }
)

#: Classes that require traversing a real load-bearing boundary. These are the
#: only classes that can satisfy a required *live capability* slot; a
#: deterministic or fault-injected-deterministic case never can, no matter how
#: many of them pass.
LIVE_CLASSES = frozenset({LIVE_E2E, ADVERSARIAL_LIVE_E2E})

#: Deterministic classes remain first-class evidence for mechanisms; they are
#: simply not substitutes for live capability proof.
DETERMINISTIC_CLASSES = frozenset(
    {DETERMINISTIC, PROPERTY_OR_FUZZ, FAULT_INJECTED_DETERMINISTIC}
)

#: Markers that show a command reaches a substantive entrypoint rather than a
#: constant. Reused from the anti-slop heuristic, but here they are a *necessary*
#: not a *sufficient* condition for live classification.
_ENTRYPOINT_MARKERS = ("run.sh", ".py", ".sh", "curl", "http://", "https://", "pytest", "nightly", "e2e")
_BROWSER_HANDLERS = ("webgpt", "webclaude", "webkimi", "webgemini", "webgrok", "webperplexity")
_ASK_BROWSER_ARTIFACT_MARKERS = (
    "browser-tab-lifecycle",
    "compete-scorecard",
    "dag-progress",
    "execution-status",
    "node-receipt",
    "response.md",
    "response.meta",
    "roundtable-summary",
)


def command_text(command: list[str]) -> str:
    """Effective command text, unwrapping bash/sh -c so checks see the real work."""
    if len(command) >= 3 and command[0] in {"bash", "sh"} and command[1] == "-c":
        return command[2]
    return " ".join(command)


def declared_class(case: dict[str, Any]) -> str:
    """The case's declared evidence class, defaulting to live E2E.

    Agentic evals should fail closed toward real-world proof. A mechanism-only
    case must say so explicitly with a deterministic evidence_class; silence is
    treated as a live capability claim and then qualified/downgraded by the
    real-E2E contract below if it uses stubs or lacks independent readback.
    """
    value = case.get("evidence_class")
    if value in EVIDENCE_CLASSES:
        return value
    if value is None:
        return LIVE_E2E
    return DETERMINISTIC


def has_independent_readback(case: dict[str, Any]) -> bool:
    """True when the case reads back a produced effect, not just an exit code.

    Real-E2E point 4: the oracle must be able to fail even when the production
    command exits 0. An `expected.artifacts` block reads a file the run
    produced; an explicit `readback: true` marks an out-of-band check the case
    author asserts. Exit-code plus the command's own success prose is *not* an
    independent readback -- that is trusting the thing under test to grade
    itself.
    """
    expected = case.get("expected") or {}
    if expected.get("artifacts"):
        return True
    if case.get("readback") is True:
        return True
    # stdout_excludes is a genuine negative oracle (it can fail on success
    # output); a bare stdout_contains of a success word is not, so it does not
    # count here.
    return bool(expected.get("stdout_excludes"))


def uses_stub_authority(case: dict[str, Any]) -> bool:
    """True when the case feeds itself fixture/stub inputs as the boundary authority.

    Monkeypatching or replaying a canned fixture proves plumbing, not the live
    boundary (real-E2E point 3).
    """
    if case.get("mocked") is True or case.get("uses_stub") is True:
        return True
    text = command_text(case.get("command", []))
    return "fixtures/" in text or "/fixtures/" in text


def reaches_entrypoint(case: dict[str, Any]) -> bool:
    """True when the command invokes a substantive entrypoint (necessary for live)."""
    text = command_text(case.get("command", []))
    return any(marker in text for marker in _ENTRYPOINT_MARKERS)


def _declares_browser_handler(text: str) -> bool:
    return any(f"--handler {handler}" in text or f"--handler={handler}" in text for handler in _BROWSER_HANDLERS)


def _is_ask_browser_workflow(case: dict[str, Any]) -> bool:
    text = command_text(case.get("command", []))
    invokes_ask = "skills/ask/run.sh" in text or "/ask/run.sh" in text or " ask/run.sh" in text
    invokes_workflow = " tau-dag" in text or " compete" in text
    return invokes_ask and invokes_workflow and _declares_browser_handler(text)


def _reads_browser_run_artifact(case: dict[str, Any]) -> bool:
    artifacts = (case.get("expected") or {}).get("artifacts") or []
    for spec in artifacts:
        path = str(spec.get("path", ""))
        if any(marker in path for marker in _ASK_BROWSER_ARTIFACT_MARKERS):
            return True
    return False


def ask_browser_workflow_reasons(case: dict[str, Any]) -> list[str]:
    """Ask browser roundtable/compete is live only when it submits and reads provider artifacts."""
    if not _is_ask_browser_workflow(case):
        return []
    text = command_text(case.get("command", []))
    reasons: list[str] = []
    if "--compile-only" in text or "--execute" not in text:
        reasons.append("ask browser workflow lacks --execute; compile/preflight is not live_e2e")
    if not _reads_browser_run_artifact(case):
        reasons.append("ask browser live_e2e must read browser/provider run artifacts")
    return reasons


def qualify(case: dict[str, Any]) -> dict[str, Any]:
    """Decide the *effective* evidence class for a case and record why.

    Returns ``{declared, effective, live_qualified, reasons}``. A case that
    declares a live class but fails any real-E2E requirement is downgraded to
    ``fault_injected_deterministic`` when it injects a fault into a real path,
    else ``deterministic`` -- and the reasons name every failed requirement so
    a reader can see the framework did not silently accept pseudo-live evidence.
    """
    declared = declared_class(case)
    reasons: list[str] = []

    if declared not in LIVE_CLASSES:
        return {
            "declared": declared,
            "effective": declared,
            "live_qualified": False,
            "reasons": [],
        }

    if uses_stub_authority(case):
        reasons.append("uses fixture/stub/mock as boundary authority")
    if not reaches_entrypoint(case):
        reasons.append("command does not reach a substantive production entrypoint")
    if not has_independent_readback(case):
        reasons.append("no independent readback oracle (exit code / self-reported success only)")
    reasons.extend(ask_browser_workflow_reasons(case))

    if not reasons:
        return {
            "declared": declared,
            "effective": declared,
            "live_qualified": True,
            "reasons": [],
        }

    # Downgrade. A fault injected into a real path is still useful deterministic
    # evidence; a stubbed happy path is plain deterministic.
    downgraded = (
        FAULT_INJECTED_DETERMINISTIC
        if reaches_entrypoint(case) and not uses_stub_authority(case)
        else DETERMINISTIC
    )
    return {
        "declared": declared,
        "effective": downgraded,
        "live_qualified": False,
        "reasons": reasons,
    }


def validate_evidence_class(case: dict[str, Any]) -> list[str]:
    """Reject an unknown evidence_class at load time."""
    value = case.get("evidence_class")
    if value is not None and value not in EVIDENCE_CLASSES:
        return [
            f"case {case.get('name')!r} has unknown evidence_class {value!r}; "
            f"valid: {sorted(EVIDENCE_CLASSES)}"
        ]
    return []
