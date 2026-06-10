"""Public syntax parsing and delegate envelope resolution."""

from __future__ import annotations

import re
from typing import Any

from .models import (
    ACTOR_KINDS,
    DELEGATE_SCHEMA,
    DelegateError,
    DelegateRegistry,
    ParsedDelegateInvocation,
    RegistryEntry,
    normalize_token,
)


REVIEW_TERMS = {"review", "critique", "assess", "check", "audit", "inspect"}
MUTATION_TERMS = {"fix", "patch", "implement", "refactor", "write", "modify", "repair"}


def parse_delegate_invocation(text_or_parts: str | list[str] | tuple[str, ...]) -> ParsedDelegateInvocation:
    """Parse `$ask <actor> to <task> [with <skill>] [on <target>]`.

    The parser intentionally accepts only the narrow explicit delegate shape.
    Broader natural-language compatibility remains in ask_routing.py.
    """

    text = _normalize_input(text_or_parts)
    lowered = text.lower()
    if lowered.startswith("$ask "):
        text = text[5:].strip()
    elif lowered.startswith("ask "):
        text = text[4:].strip()

    match = re.match(r"^(?P<actor>\$?[\w.-]+|[A-Z][\w.-]+)\s+to\s+(?P<body>.+)$", text)
    if not match:
        raise DelegateError(
            "not_delegate_syntax",
            "Delegate syntax must be '<actor> to <task> [with <skill>] [on <target>]'.",
            safe_default="use_existing_ask_routing",
        )

    actor = match.group("actor").strip()
    body = match.group("body").strip()
    skill_tokens: tuple[str, ...] = ()
    target: tuple[str, ...] = ()

    body, on_target = _split_last_keyword(body, " on ")
    if on_target:
        target = (on_target.strip(),)

    task, with_part = _split_last_keyword(body, " with ")
    if with_part:
        skill_tokens = tuple(
            token.strip(" ,")
            for token in re.split(r"\s*(?:,| and )\s*", with_part)
            if token.strip(" ,")
        )
    else:
        task = body

    task = task.strip()
    if not task:
        raise DelegateError("missing_delegate_task", "Delegate task is required.")
    return ParsedDelegateInvocation(actor_token=actor, task=task, skill_tokens=skill_tokens, target=target)


def resolve_delegate_invocation(
    text_or_parts: str | list[str] | tuple[str, ...],
    registry: DelegateRegistry,
    *,
    request_id: str = "",
    caller: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Resolve public delegate syntax into an `agent_skills.delegate.v1` envelope."""

    parsed = parse_delegate_invocation(text_or_parts)
    actor = registry.require_one(parsed.actor_token, kinds=ACTOR_KINDS, position="actor")
    skills = tuple(registry.require_one(token, kinds={"skill"}, position="skill") for token in parsed.skill_tokens)
    mode = _infer_mode(actor, parsed.task)
    runtime = _select_runtime(actor, mode)
    policy = _policy_for(actor, mode)
    _validate_actor_skill_compatibility(actor, skills, parsed.task)
    return _envelope(
        request_id=request_id,
        caller=_normalize_caller(caller),
        actor=actor,
        skills=skills,
        task=parsed.task,
        target=parsed.target,
        mode=mode,
        runtime=runtime,
        policy=policy,
    )


def _infer_mode(actor: RegistryEntry, task: str) -> str:
    task_terms = {part.lower().strip(".,:;!?") for part in task.split()}
    if actor.kind == "oracle":
        return actor.default_mode or "browser_review"
    if actor.kind == "persona":
        return "persona_review" if task_terms & REVIEW_TERMS else (actor.default_mode or "persona_review")
    if task_terms & MUTATION_TERMS:
        for candidate in ("workspace_write", "patch_plan", "patch"):
            if candidate in actor.allowed_modes:
                return candidate
        raise DelegateError(
            "mutation_mode_not_allowed",
            f"{actor.id} does not allow mutation for this delegate request.",
            details={"actor": actor.as_dict(), "task": task},
        )
    if task_terms & REVIEW_TERMS:
        return "read_only_review"
    return actor.default_mode or "read_only_review"


def _select_runtime(actor: RegistryEntry, mode: str) -> dict[str, str]:
    if actor.kind == "persona":
        return {"selected": "scillm_chat", "reason": "persona review uses a one-shot model turn"}
    if actor.kind == "oracle":
        selected = actor.default_runtime or f"{actor.id}_browser"
        return {"selected": selected, "reason": "explicit browser oracle target"}
    if actor.target_type == "repo_worker" and mode == "read_only_review":
        if "opencode_serve" in actor.eligible_runtimes:
            return {"selected": "opencode_serve", "reason": "repo-aware read-only review without transport-only features"}
        return {"selected": "opencode_serve", "reason": "repo-aware read-only review default"}
    selected = actor.default_runtime or "opencode_transport"
    return {"selected": selected, "reason": f"mode {mode} uses actor default runtime"}


def _policy_for(actor: RegistryEntry, mode: str) -> dict[str, Any]:
    mutation = "read_only"
    if mode in {"workspace_write", "patch", "patch_plan"}:
        mutation = "workspace_write" if mode == "workspace_write" else "patch_plan"
    proof = ["receipt", "review_artifact"]
    if mutation != "read_only":
        proof.extend(["diff", "tests"])
    return {
        "mutation": mutation,
        "network": "inherit_project_policy",
        "proof_required": proof,
    }


def _validate_actor_skill_compatibility(actor: RegistryEntry, skills: tuple[RegistryEntry, ...], task: str) -> None:
    if not skills:
        return
    actor_skill_ids = {normalize_token(skill_id) for skill_id in actor.composes}
    task_terms = {part.lower().strip(".,:;!?") for part in task.split()}
    for skill in skills:
        skill_id = normalize_token(skill.id)
        if actor.kind == "persona" and not (task_terms & REVIEW_TERMS):
            raise DelegateError(
                "persona_skill_not_compatible",
                f"Persona {actor.id} cannot use skill {skill.id} for this task without an explicit review/critique context.",
                details={"actor": actor.as_dict(), "skill": skill.as_dict()},
            )
        if actor.kind == "agent" and actor_skill_ids and skill_id not in actor_skill_ids:
            raise DelegateError(
                "actor_skill_not_compatible",
                f"Agent {actor.id} is not registered as composing skill {skill.id}.",
                details={
                    "actor": actor.as_dict(),
                    "skill": skill.as_dict(),
                    "override_policy": {
                        "allowed_by_prompt": False,
                        "required_authority": "privileged_registry_policy",
                        "safe_default": "do_not_delegate",
                    },
                },
            )


def _envelope(
    *,
    request_id: str,
    caller: dict[str, str],
    actor: RegistryEntry,
    skills: tuple[RegistryEntry, ...],
    task: str,
    target: tuple[str, ...],
    mode: str,
    runtime: dict[str, str],
    policy: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": DELEGATE_SCHEMA,
        "invocation_id": request_id,
        "request_id": request_id,
        "caller": caller,
        "actor": {
            "id": actor.id,
            "kind": actor.kind,
            "target_type": actor.target_type,
            **({"source_kind": actor.source_kind} if actor.source_kind else {}),
        },
        "skills": [
            {
                "id": skill.id,
                "kind": skill.kind,
                **({"version_or_digest": skill.version_or_digest} if skill.version_or_digest else {}),
            }
            for skill in skills
        ],
        "task": task,
        "target": list(target),
        "mode": mode,
        "runtime": runtime,
        "policy": policy,
        "override_policy": {
            "skill_composition": "strict",
            "prompt_level_override_allowed": False,
            "privileged_override_supported": False,
            "privileged_override_requires": [
                "registry_policy",
                "caller_authority",
                "envelope_record",
                "receipt_record",
            ],
        },
        "receipt_requirements": {
            "preserve_invocation_id": True,
            "preserve_caller": True,
            "preserve_actor_id": True,
            "preserve_skill_ids": True,
            "preserve_skill_versions_or_digests": True,
            "include_target": True,
            "include_mode": True,
            "include_runtime": True,
            "include_override_policy": True,
            "include_materialized_skill_bundle": True,
            "include_artifact_paths": True,
        },
    }


def _normalize_caller(caller: dict[str, str] | None) -> dict[str, str]:
    caller = caller or {}
    caller_type = str(caller.get("type") or "agent").strip() or "agent"
    caller_id = str(caller.get("id") or "ask-cli").strip() or "ask-cli"
    return {"type": caller_type, "id": caller_id}


def _normalize_input(text_or_parts: str | list[str] | tuple[str, ...]) -> str:
    if isinstance(text_or_parts, str):
        return text_or_parts.strip()
    return " ".join(str(part).strip() for part in text_or_parts if str(part).strip()).strip()


def _split_last_keyword(text: str, keyword: str) -> tuple[str, str]:
    index = text.lower().rfind(keyword)
    if index < 0:
        return text, ""
    return text[:index].strip(), text[index + len(keyword):].strip()
