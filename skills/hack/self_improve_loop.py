"""Pure contract objects for the /hack self-improving plan loop.

This module intentionally performs no I/O at import time.  It does not call the
network, Docker, /plan, /dogpile, /memory, /project-knowledge, or /orchestrate.
Every function below is deterministic and returns data for a caller to execute
elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import posixpath
import re
from typing import Mapping, Sequence


ARTIFACT_ROOT = "/mnt/storage12tb/artifacts/agent-skills/hack"


class AttemptStatus(str, Enum):
    """Normalized terminal status for one isolated /hack attempt."""

    SUCCESS = "success"
    TRANSIENT_INFRA_FAILURE = "transient_infra_failure"
    STRATEGY_FAILURE = "strategy_failure"
    SECURITY_FAILURE = "security_failure"
    UNSAFE_SCOPE = "unsafe_scope"
    AMBIGUOUS = "ambiguous"
    INFRA_UNREACHABLE = "infra_unreachable"


class DecisionOutcome(str, Enum):
    """All deterministic decisions the loop may return."""

    SUCCESS = "success"
    SAME_PLAN_RETRY_FOR_TRANSIENT = "same_plan_retry_for_transient"
    REGENERATE_PLAN_FOR_STRATEGY_FAILURE = "regenerate_plan_for_strategy_failure"
    STOP_MAX_RETRIES = "stop_max_retries"
    STOP_UNSAFE_SCOPE = "stop_unsafe_scope"
    STOP_AMBIGUOUS = "stop_ambiguous"
    STOP_INFRA_UNREACHABLE = "stop_infra_unreachable"


class NetworkPolicy(str, Enum):
    """Network posture requested for the later Docker execution."""

    NONE = "none"
    BRIDGE = "bridge"
    HOST = "host"


class MountMode(str, Enum):
    """Docker mount mutability."""

    READ_ONLY = "ro"
    READ_WRITE = "rw"


class ResearchSource(str, Enum):
    """Dogpile source classes required by the loop contract."""

    BRAVE_WEB = "brave_web_search"
    GITHUB_REPOS = "github_repos"
    GITHUB_ISSUES = "github_issues"
    GITHUB_CODE = "github_code"
    ARXIV = "arxiv_papers"
    FEEDS_ADVISORIES = "feeds_advisories"
    BOOKS_SITES = "books_sites"


@dataclass(frozen=True)
class EvidencePath:
    """Artifact pointer produced by a session, never raw log content."""

    kind: str
    path: str

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise ValueError("evidence kind must be non-empty")
        _require_artifact_pointer(self.path)


@dataclass(frozen=True)
class MountSpec:
    """A Docker mount declaration for the pure launch spec."""

    source: str
    target: str
    mode: MountMode = MountMode.READ_ONLY

    def __post_init__(self) -> None:
        if not self.source.startswith("/") or not self.target.startswith("/"):
            raise ValueError("mount source and target must be absolute paths")


@dataclass(frozen=True)
class AttemptRecord:
    """One observed execution attempt.

    The record stores summaries and artifact pointers only.  Raw stdout/stderr,
    packet captures, exploit output, or scan logs belong in artifact files under
    the session directory and should be referenced via ``evidence_paths``.
    """

    attempt_id: str
    plan_id: str
    status: AttemptStatus
    evidence_paths: tuple[str, ...] = ()
    summary: str = ""
    learning_delta: str = ""
    strategy_change: str = ""
    dogpile_context: tuple[str, ...] = ()
    memory_context: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.attempt_id.strip():
            raise ValueError("attempt_id must be non-empty")
        if not self.plan_id.strip():
            raise ValueError("plan_id must be non-empty")
        for path in self.evidence_paths:
            _require_artifact_pointer(path)


@dataclass(frozen=True)
class LoopConfig:
    """Configuration for deterministic loop decisions and pure builders."""

    session_id: str
    max_plan_revisions: int = 3
    max_transient_retries_per_plan: int = 2
    artifact_root: str = ARTIFACT_ROOT
    authorized_scope_confirmed: bool = True
    ambiguous_scope: bool = False
    infrastructure_reachable: bool = True
    docker_network_policy: NetworkPolicy = NetworkPolicy.NONE
    target_mounts: tuple[MountSpec, ...] = ()
    environment: Mapping[str, str] = field(default_factory=dict)
    dogpile_context: tuple[str, ...] = ()
    memory_context: tuple[str, ...] = ()
    include_books_sites_research: bool = False
    require_test_lab_preflight: bool = False
    test_lab_reachable: bool = False

    def __post_init__(self) -> None:
        if self.max_plan_revisions < 0:
            raise ValueError("max_plan_revisions must be >= 0")
        if self.max_transient_retries_per_plan < 0:
            raise ValueError("max_transient_retries_per_plan must be >= 0")
        if not self.artifact_root.startswith("/"):
            raise ValueError("artifact_root must be an absolute path")
        _session_dir(self)


@dataclass(frozen=True)
class PlanRevisionContext:
    """Required context supplied to the next /plan invocation by the caller."""

    prior_failure_evidence: tuple[str, ...]
    previous_plan_id: str
    learning_delta: str
    dogpile_context: tuple[str, ...]
    memory_context: tuple[str, ...]
    strategy_change: str

    def __post_init__(self) -> None:
        if not self.prior_failure_evidence:
            raise ValueError("prior_failure_evidence must be non-empty")
        for path in self.prior_failure_evidence:
            _require_artifact_pointer(path)
        if not self.previous_plan_id.strip():
            raise ValueError("previous_plan_id must be non-empty")
        if not self.learning_delta.strip():
            raise ValueError("learning_delta must be non-empty")
        if not self.strategy_change.strip():
            raise ValueError("strategy_change must be non-empty")


@dataclass(frozen=True)
class LoopDecision:
    """Deterministic next action for the self-improving loop."""

    outcome: DecisionOutcome
    reason: str
    stop: bool
    retry_same_plan: bool = False
    requires_plan_revision: bool = False
    previous_plan_id: str | None = None
    next_plan_id_hint: str | None = None
    plan_revision_context: PlanRevisionContext | None = None


@dataclass(frozen=True)
class DockerLaunchSpec:
    """Pure description of files and options a caller may materialize/run."""

    session_id: str
    session_dir: str
    dockerfile_path: str
    compose_path: str
    dockerfile_content: str
    compose_content: str
    environment: Mapping[str, str]
    mounts: tuple[MountSpec, ...]
    network_policy: NetworkPolicy
    evidence_paths: Mapping[str, str]


@dataclass(frozen=True)
class MemoryRecord:
    """Distilled memory payload; raw logs are represented by artifact pointers."""

    session_id: str
    title: str
    distilled_lesson: str
    tags: tuple[str, ...]
    artifact_pointers: tuple[str, ...]
    previous_plan_id: str | None = None
    decision_outcome: DecisionOutcome | None = None

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("memory title must be non-empty")
        if not self.distilled_lesson.strip():
            raise ValueError("distilled_lesson must be non-empty")
        for path in self.artifact_pointers:
            _require_artifact_pointer(path)


@dataclass(frozen=True)
class ProjectKnowledgeUpdate:
    """Append-only project knowledge update payload."""

    session_id: str
    summary: str
    facts: tuple[str, ...]
    next_steps: tuple[str, ...]
    artifact_pointers: tuple[str, ...]
    decision_outcome: DecisionOutcome

    def __post_init__(self) -> None:
        if not self.summary.strip():
            raise ValueError("summary must be non-empty")
        for path in self.artifact_pointers:
            _require_artifact_pointer(path)


@dataclass(frozen=True)
class ResearchRequirement:
    """Pure /dogpile research request for regenerating the next plan."""

    query: str
    required_sources: tuple[ResearchSource, ...]
    source_queries: Mapping[ResearchSource, str]
    synthesis_prompt: str
    feed_advisory_topics: tuple[str, ...]
    include_books_sites: bool = False

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("query must be non-empty")
        if ResearchSource.FEEDS_ADVISORIES not in self.required_sources:
            raise ValueError("feeds/advisories research is mandatory")
        if ResearchSource.ARXIV not in self.required_sources:
            raise ValueError("ArXiv research is mandatory")
        for source in self.required_sources:
            if source not in self.source_queries or not self.source_queries[source].strip():
                raise ValueError(f"missing query for research source {source.value}")
        if "next plan" not in self.synthesis_prompt.lower():
            raise ValueError("synthesis_prompt must require synthesis into the next plan")


def decide_next_action(config: LoopConfig, attempts: Sequence[AttemptRecord]) -> LoopDecision:
    """Return the deterministic next loop action from config and attempts.

    The function is pure: it examines only its arguments and does not perform
    preflight checks, Docker calls, network research, memory writes, or plan
    generation.  Transient infrastructure retries are counted separately from
    strategy/security plan revisions.
    """

    if not config.authorized_scope_confirmed:
        return _stop(DecisionOutcome.STOP_UNSAFE_SCOPE, "authorized scope was not confirmed")
    if config.ambiguous_scope:
        return _stop(DecisionOutcome.STOP_AMBIGUOUS, "scope is ambiguous")
    if not config.infrastructure_reachable:
        return _stop(DecisionOutcome.STOP_INFRA_UNREACHABLE, "infrastructure preflight is unreachable")
    if config.require_test_lab_preflight and not config.test_lab_reachable:
        return _stop(DecisionOutcome.STOP_INFRA_UNREACHABLE, "required test-lab preflight is unreachable")
    if not attempts:
        return _stop(DecisionOutcome.STOP_AMBIGUOUS, "no attempts supplied")

    latest = attempts[-1]
    if latest.status is AttemptStatus.SUCCESS:
        return LoopDecision(
            outcome=DecisionOutcome.SUCCESS,
            reason="latest attempt succeeded",
            stop=True,
            previous_plan_id=latest.plan_id,
        )
    if latest.status is AttemptStatus.UNSAFE_SCOPE:
        return _stop(DecisionOutcome.STOP_UNSAFE_SCOPE, "latest attempt reported unsafe scope", latest.plan_id)
    if latest.status is AttemptStatus.AMBIGUOUS:
        return _stop(DecisionOutcome.STOP_AMBIGUOUS, "latest attempt reported ambiguous evidence", latest.plan_id)
    if latest.status is AttemptStatus.INFRA_UNREACHABLE:
        return _stop(DecisionOutcome.STOP_INFRA_UNREACHABLE, "latest attempt reported unreachable infrastructure", latest.plan_id)

    if latest.status is AttemptStatus.TRANSIENT_INFRA_FAILURE:
        retries_for_plan = _consecutive_status_for_plan(
            attempts, latest.plan_id, AttemptStatus.TRANSIENT_INFRA_FAILURE
        )
        if retries_for_plan <= config.max_transient_retries_per_plan:
            return LoopDecision(
                outcome=DecisionOutcome.SAME_PLAN_RETRY_FOR_TRANSIENT,
                reason=(
                    "transient infrastructure failure; retrying same plan "
                    f"{retries_for_plan}/{config.max_transient_retries_per_plan}"
                ),
                stop=False,
                retry_same_plan=True,
                requires_plan_revision=False,
                previous_plan_id=latest.plan_id,
                next_plan_id_hint=latest.plan_id,
            )
        return _stop(
            DecisionOutcome.STOP_INFRA_UNREACHABLE,
            "transient infrastructure retry budget exhausted",
            latest.plan_id,
        )

    if latest.status in (AttemptStatus.STRATEGY_FAILURE, AttemptStatus.SECURITY_FAILURE):
        prior_revision_failures = sum(
            1
            for attempt in attempts[:-1]
            if attempt.status in (AttemptStatus.STRATEGY_FAILURE, AttemptStatus.SECURITY_FAILURE)
        )
        if prior_revision_failures >= config.max_plan_revisions:
            return _stop(DecisionOutcome.STOP_MAX_RETRIES, "plan revision budget exhausted", latest.plan_id)
        if not latest.evidence_paths:
            return _stop(
                DecisionOutcome.STOP_AMBIGUOUS,
                "strategy/security failure lacks artifact evidence for plan revision",
                latest.plan_id,
            )
        context = _plan_revision_context(config, latest)
        return LoopDecision(
            outcome=DecisionOutcome.REGENERATE_PLAN_FOR_STRATEGY_FAILURE,
            reason="strategy/security failure requires a revised plan",
            stop=False,
            retry_same_plan=False,
            requires_plan_revision=True,
            previous_plan_id=latest.plan_id,
            next_plan_id_hint=f"{latest.plan_id}-revision-{prior_revision_failures + 1}",
            plan_revision_context=context,
        )

    return _stop(DecisionOutcome.STOP_AMBIGUOUS, "unrecognized latest attempt status", latest.plan_id)


def build_docker_launch_spec(
    config: LoopConfig,
    plan_id: str,
    *,
    image_name: str = "hack-self-improve:session",
) -> DockerLaunchSpec:
    """Build a pure per-session Docker launch specification.

    The returned paths and file contents are data only; this function does not
    create files, build images, run containers, or validate Docker availability.
    """

    if not plan_id.strip():
        raise ValueError("plan_id must be non-empty")
    session_dir = _session_dir(config)
    dockerfile_path = posixpath.join(session_dir, "Dockerfile")
    compose_path = posixpath.join(session_dir, "docker-compose.yml")
    evidence_dir = posixpath.join(session_dir, "evidence")
    evidence_paths = {
        "stdout": posixpath.join(evidence_dir, "stdout.log"),
        "stderr": posixpath.join(evidence_dir, "stderr.log"),
        "exit_code": posixpath.join(evidence_dir, "exit_code.txt"),
        "findings": posixpath.join(evidence_dir, "findings.json"),
        "plan": posixpath.join(evidence_dir, "plan.json"),
    }
    env = {
        "HACK_SESSION_ID": config.session_id,
        "HACK_PLAN_ID": plan_id,
        "HACK_EVIDENCE_DIR": "/evidence",
        "HACK_NETWORK_POLICY": config.docker_network_policy.value,
    }
    env.update({str(k): str(v) for k, v in sorted(config.environment.items())})
    artifact_mount = MountSpec(session_dir, "/evidence", MountMode.READ_WRITE)
    mounts = tuple(config.target_mounts) + (artifact_mount,)
    dockerfile_content = "\n".join(
        (
            "FROM python:3.12-slim",
            "LABEL org.agent-skills.skill=\"hack\"",
            "LABEL org.agent-skills.contract=\"self-improve-loop\"",
            "WORKDIR /workspace",
            "RUN useradd --create-home --shell /usr/sbin/nologin hackrunner",
            "USER hackrunner",
            "CMD [\"python3\", \"-c\", \"print('hack self-improve container placeholder')\"]",
            "",
        )
    )
    compose_content = _compose_content(image_name, dockerfile_path, env, mounts, config.docker_network_policy)
    return DockerLaunchSpec(
        session_id=config.session_id,
        session_dir=session_dir,
        dockerfile_path=dockerfile_path,
        compose_path=compose_path,
        dockerfile_content=dockerfile_content,
        compose_content=compose_content,
        environment=env,
        mounts=mounts,
        network_policy=config.docker_network_policy,
        evidence_paths=evidence_paths,
    )


def build_memory_record(
    config: LoopConfig,
    attempts: Sequence[AttemptRecord],
    decision: LoopDecision,
) -> MemoryRecord:
    """Build a distilled memory record without raw logs."""

    artifact_pointers = _unique_paths(path for attempt in attempts for path in attempt.evidence_paths)
    latest = attempts[-1] if attempts else None
    summary = latest.summary if latest and latest.summary.strip() else decision.reason
    lesson = f"/hack loop outcome {decision.outcome.value}: {summary}"
    if decision.plan_revision_context is not None:
        lesson += f"; strategy change: {decision.plan_revision_context.strategy_change}"
    return MemoryRecord(
        session_id=config.session_id,
        title=f"hack self-improve {config.session_id} {decision.outcome.value}",
        distilled_lesson=lesson,
        tags=("hack", "self-improve-loop", decision.outcome.value),
        artifact_pointers=artifact_pointers,
        previous_plan_id=decision.previous_plan_id,
        decision_outcome=decision.outcome,
    )


def build_project_knowledge_update(
    config: LoopConfig,
    attempts: Sequence[AttemptRecord],
    decision: LoopDecision,
) -> ProjectKnowledgeUpdate:
    """Build an append-only project knowledge update payload."""

    artifact_pointers = _unique_paths(path for attempt in attempts for path in attempt.evidence_paths)
    facts = tuple(
        f"attempt {attempt.attempt_id} using plan {attempt.plan_id} ended as {attempt.status.value}"
        for attempt in attempts
    )
    next_steps = _next_steps_for(decision)
    return ProjectKnowledgeUpdate(
        session_id=config.session_id,
        summary=f"/hack self-improve loop produced {decision.outcome.value}: {decision.reason}",
        facts=facts,
        next_steps=next_steps,
        artifact_pointers=artifact_pointers,
        decision_outcome=decision.outcome,
    )


def build_research_requirement(
    config: LoopConfig,
    revision_context: PlanRevisionContext,
    *,
    topic: str = "authorized security assessment strategy failure",
) -> ResearchRequirement:
    """Build a pure dogpile requirement for research before the next plan."""

    base_query = (
        f"{topic}; previous plan {revision_context.previous_plan_id}; "
        f"learning delta {revision_context.learning_delta}; "
        f"strategy change {revision_context.strategy_change}"
    )
    sources: list[ResearchSource] = [
        ResearchSource.BRAVE_WEB,
        ResearchSource.GITHUB_REPOS,
        ResearchSource.GITHUB_ISSUES,
        ResearchSource.GITHUB_CODE,
        ResearchSource.ARXIV,
        ResearchSource.FEEDS_ADVISORIES,
    ]
    if config.include_books_sites_research:
        sources.append(ResearchSource.BOOKS_SITES)
    source_queries = {
        ResearchSource.BRAVE_WEB: base_query + " web writeups mitigations",
        ResearchSource.GITHUB_REPOS: base_query + " GitHub repositories proof of concept defensive tooling",
        ResearchSource.GITHUB_ISSUES: base_query + " GitHub issues failures edge cases",
        ResearchSource.GITHUB_CODE: base_query + " GitHub code examples detection bypass fixes",
        ResearchSource.ARXIV: base_query + " ArXiv papers security testing methodology",
        ResearchSource.FEEDS_ADVISORIES: base_query + " CVE advisories vendor feeds exploit notes",
    }
    if config.include_books_sites_research:
        source_queries[ResearchSource.BOOKS_SITES] = base_query + " books authoritative sites references"
    synthesis_prompt = (
        "Synthesize Brave/web, GitHub repository/issue/code, ArXiv, feed/advisory"
        " findings"
        + (", and book/site findings" if config.include_books_sites_research else "")
        + " into the next plan. Explicitly map each finding to the prior failure evidence, "
        "learning delta, and required strategy_change; omit raw logs and cite artifact pointers."
    )
    return ResearchRequirement(
        query=base_query,
        required_sources=tuple(sources),
        source_queries=source_queries,
        synthesis_prompt=synthesis_prompt,
        feed_advisory_topics=("CVE", "vendor advisories", "exploit feeds", "defensive mitigations"),
        include_books_sites=config.include_books_sites_research,
    )


def _plan_revision_context(config: LoopConfig, latest: AttemptRecord) -> PlanRevisionContext:
    learning_delta = latest.learning_delta.strip() or latest.summary.strip() or f"Observed {latest.status.value}"
    strategy_change = latest.strategy_change.strip() or (
        f"Replace previous {latest.status.value.replace('_', ' ')} approach with a researched alternative "
        "that addresses the recorded failure evidence."
    )
    return PlanRevisionContext(
        prior_failure_evidence=tuple(latest.evidence_paths),
        previous_plan_id=latest.plan_id,
        learning_delta=learning_delta,
        dogpile_context=tuple(config.dogpile_context) + tuple(latest.dogpile_context),
        memory_context=tuple(config.memory_context) + tuple(latest.memory_context),
        strategy_change=strategy_change,
    )


def _stop(outcome: DecisionOutcome, reason: str, previous_plan_id: str | None = None) -> LoopDecision:
    return LoopDecision(outcome=outcome, reason=reason, stop=True, previous_plan_id=previous_plan_id)


def _consecutive_status_for_plan(
    attempts: Sequence[AttemptRecord], plan_id: str, status: AttemptStatus) -> int:
    count = 0
    for attempt in reversed(attempts):
        if attempt.plan_id != plan_id or attempt.status is not status:
            break
        count += 1
    return count


def _session_dir(config: LoopConfig) -> str:
    session_name = _safe_session_name(config.session_id)
    if not session_name.startswith("session-"):
        session_name = "session-" + session_name
    session_dir = posixpath.normpath(posixpath.join(config.artifact_root, session_name))
    root = posixpath.normpath(config.artifact_root)
    if not session_dir.startswith(root + "/session-"):
        raise ValueError("session_dir must remain under artifact_root/session-*")
    return session_dir


def _safe_session_name(session_id: str) -> str:
    value = session_id.strip()
    if not value:
        raise ValueError("session_id must be non-empty")
    return re.sub(r"[^A-Za-z0-9_.-]", "-", value)


def _require_artifact_pointer(path: str) -> None:
    if not path.startswith(ARTIFACT_ROOT + "/session-"):
        raise ValueError(f"raw logs are not accepted; expected artifact pointer under {ARTIFACT_ROOT}/session-*: {path!r}")


def _compose_content(
    image_name: str,
    dockerfile_path: str,
    env: Mapping[str, str],
    mounts: Sequence[MountSpec],
    network_policy: NetworkPolicy,
) -> str:
    lines = [
        "services:",
        "  hack-self-improve:",
        f"    image: {image_name}",
        "    build:",
        f"      dockerfile: {dockerfile_path}",
        "      context: .",
        "    environment:",
    ]
    for key in sorted(env):
        lines.append(f"      {key}: {env[key]!r}")
    lines.append("    volumes:")
    for mount in mounts:
        lines.append(f"      - {mount.source}:{mount.target}:{mount.mode.value}")
    if network_policy is NetworkPolicy.NONE:
        lines.append('    network_mode: "none"')
    elif network_policy is NetworkPolicy.HOST:
        lines.append('    network_mode: "host"')
    else:
        lines.extend(["    networks:", "      - hack_session_net", "networks:", "  hack_session_net:", "    driver: bridge"])
    lines.append("")
    return "\n".join(lines)


def _unique_paths(paths: Sequence[str] | object) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for path in paths:  # type: ignore[operator]
        if path not in seen:
            _require_artifact_pointer(path)
            seen.add(path)
            unique.append(path)
    return tuple(unique)


def _next_steps_for(decision: LoopDecision) -> tuple[str, ...]:
    if decision.outcome is DecisionOutcome.SUCCESS:
        return ("Persist distilled evidence and close the authorized session.",)
    if decision.outcome is DecisionOutcome.SAME_PLAN_RETRY_FOR_TRANSIENT:
        return ("Retry the same plan within the transient infrastructure budget.",)
    if decision.outcome is DecisionOutcome.REGENERATE_PLAN_FOR_STRATEGY_FAILURE:
        return ("Run configured dogpile research and generate a revised plan with an explicit strategy change.",)
    return ("Stop the loop and request human clarification or infrastructure repair before continuing.",)


__all__ = [
    "ARTIFACT_ROOT",
    "AttemptRecord",
    "AttemptStatus",
    "DecisionOutcome",
    "DockerLaunchSpec",
    "EvidencePath",
    "LoopConfig",
    "LoopDecision",
    "MemoryRecord",
    "MountMode",
    "MountSpec",
    "NetworkPolicy",
    "PlanRevisionContext",
    "ProjectKnowledgeUpdate",
    "ResearchRequirement",
    "ResearchSource",
    "build_docker_launch_spec",
    "build_memory_record",
    "build_project_knowledge_update",
    "build_research_requirement",
    "decide_next_action",
]
