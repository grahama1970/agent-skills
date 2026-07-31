"""Validated DAG execution for /ask project-agent inputs."""

from __future__ import annotations

import json
import subprocess
import tempfile
import re
import time
import base64
import mimetypes
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .ask_config import DEFAULT_ORACLE_MODEL, DEFAULT_ORACLE_REASONING, DEFAULT_ORACLE_TIMEOUT, SCILLM_API_KEY, SCILLM_BASE_URL
from .run_state import AskRunState
from .scillm_agents import (
    CODING_INTENT_RE,
    ScillmAgentsError,
    default_coding_worker_id,
    memory_context_from_dag_dependencies,
    run_agent_turn,
)
from .scillm_runtime import build_scillm_metadata
from .skills_exec import AGENT_SKILLS_DIR, SKILLS_DIR, parse_json_output, parse_memory_output, run_memory_recall, run_skill
from .dag_repair import apply_dag_repairs, resolve_node_timeout

try:
    import networkx as nx
except ImportError:  # pragma: no cover
    nx = None  # type: ignore[assignment]

try:
    from phart import ASCIIRenderer
except ImportError:  # pragma: no cover
    ASCIIRenderer = None  # type: ignore[assignment,misc]


ASK_DAG_SCHEMA_VERSION = "ask.dag.v1"
SCILLM_EXEC_GRAPH_VERSION = "scillm.exec.graph.v1"
NODE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
ALLOWED_NODE_TYPES = {
    "memory.recall",
    "dogpile.search",
    "ask.oracle",
    "ask.report",
    "skill.run",
    "scillm.agent_turn",
}
COMMON_SKILL_RUN_SKILLS = {
    "code-runner",
    "memory",
    "dogpile",
    "fetcher",
    "extractor",
    "project-knowledge",
    "extract-entities",
    "review-code",
    "subagent-runner",
    "debugger",
}
INTERNAL_SKILL_MENTION_TYPES = {"ask", "memory", "dogpile", "scillm", "interview"}


def _temperature_for_model(model: str) -> float:
    lowered = model.strip().lower()
    if lowered == "moonshot-text":
        return 1.0
    if "moonshot" in lowered or "kimi" in lowered:
        return 0.6
    return 0.0


class AskDagError(ValueError):
    """Raised when an ask DAG is malformed or cannot be executed safely."""


def available_skill_run_skills() -> set[str]:
    """Return sibling skills that can be invoked through their documented run.sh.

    The DAG validator should not encode a product-specific subset of skills.
    It only enforces that a skill name is safe and has a sibling runtime entrypoint.
    Individual skills still own their arguments and internal behavior.
    """
    skills: set[str] = set()
    for root in (SKILLS_DIR, AGENT_SKILLS_DIR):
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir():
                continue
            if not NODE_ID_RE.fullmatch(child.name):
                continue
            if (child / "run.sh").is_file() and (child / "SKILL.md").is_file():
                skills.add(child.name)
    return skills


def should_orchestrate_from_text(text: str) -> bool:
    lowered = text.lower()
    if re.search(r"\b(dag|orchestrat(?:e|ion)|workflow|skill graph|pipeline)\b", lowered):
        return True
    if CODING_INTENT_RE.search(text):
        return True
    mentions = set(_extract_skill_mentions_from_text(text))
    return len(mentions - {"ask"}) >= 2




def _infer_persona_from_text(text: str) -> str:
    lowered = text.lower()
    for name in ("Brandon", "Margaret", "Jennifer", "Nico", "Embry"):
        if name.lower() in lowered:
            return name
    return "Brandon"


def draft_ask_dag_from_question(
    question: str,
    *,
    scope: str = "ask",
    mentioned_skills: list[str] | None = None,
    max_concurrency: int = 4,
    agent_worker_id: str | None = None,
    default_oracle_model: str | None = None,
    prefer_agent_coding: bool = True,
) -> dict[str, Any]:
    """Draft a conservative executable DAG from natural language.

    This is deliberately a compiler for clear, common orchestration shapes, not
    a hidden planning model. If the request cannot be safely mapped, callers
    should ask a concise /interview question instead of guessing.
    """
    text = question.strip()
    if not text:
        raise AskDagError("Cannot orchestrate an empty question.")
    mentions = sorted(set(mentioned_skills or _extract_skill_mentions_from_text(text)))
    available = available_skill_run_skills()
    unknown = sorted(
        skill
        for skill in mentions
        if skill not in INTERNAL_SKILL_MENTION_TYPES and skill != "create-report" and skill not in available
    )
    if unknown:
        raise AskDagError(
            "Natural-language DAG mentions skills without runnable sibling skill contracts: "
            + ", ".join(unknown)
            + ". Use /interview to choose a different skill or create/install the missing skill."
        )

    lowered = text.lower()
    needs_freshness = bool(
        {"dogpile", "research"} & set(mentions)
        or re.search(r"\b(latest|current|today|recent|fresh|research|web|sources?)\b", lowered)
    )
    wants_report = "create-report" in mentions or bool(re.search(r"\b(report|write[- ]?up|briefing|summary document)\b", lowered))
    wants_oracle = "scillm" in mentions or bool(re.search(r"\b(analy[sz]e|review|critique|compare|decide|answer|synthesi[sz]e)\b", lowered))
    explicit_skill_mentions = [skill for skill in mentions if skill not in INTERNAL_SKILL_MENTION_TYPES]
    if "review-design" in explicit_skill_mentions:
        raise AskDagError(
            "$ask + $review-design requires the bounded review-design loop with "
            "persona, screenshots, and verdict artifacts; refusing to invoke "
            "review-design with empty generic DAG args."
        )

    wants_coding = bool(CODING_INTENT_RE.search(lowered)) or bool(
        {"code-runner", "subagent-runner"} & set(explicit_skill_mentions)
    )
    coding_skills = {"code-runner", "subagent-runner"}
    non_coding_skill_mentions = [skill for skill in explicit_skill_mentions if skill not in coding_skills]
    wants_review_implement_loop = bool(
        "review-code" in mentions and wants_coding
    ) or bool(re.search(r"\breview\b.*\b(implement|fix|patch)\b", lowered))
    persona_name = _infer_persona_from_text(text)

    if wants_review_implement_loop:
        return build_persona_review_implement_dag(
            text,
            scope=scope,
            persona=persona_name,
            agent_worker_id=agent_worker_id,
            include_dogpile="dogpile" in mentions or needs_freshness or bool(
                re.search(r"\b(blocked|dogpile|research|consult)\b", lowered)
            ),
            include_debugger_escalation="debugger" in mentions or bool(
                re.search(r"\b(stuck|breakpoint|debugger|variable state|runtime error)\b", lowered)
            ),
            max_concurrency=max_concurrency,
        )

    if not any([needs_freshness, wants_report, wants_oracle, wants_coding, non_coding_skill_mentions]):
        raise AskDagError(
            "Natural-language DAG request is ambiguous. Use /interview to clarify the target skill, output artifact, or acceptance criteria."
        )

    nodes: list[dict[str, Any]] = [
        {
            "id": "memory_first",
            "type": "memory.recall",
            "allow_failure": True,
            "input": {"query": text, "scope": scope, "k": 5},
        }
    ]
    dependency_tail = ["memory_first"]
    if needs_freshness:
        nodes.append(
            {
                "id": "research",
                "type": "dogpile.search",
                "depends_on": dependency_tail,
                "input": {"query": text, "auto_preset": True},
            }
        )
        dependency_tail = ["research"]

    if wants_oracle:
        nodes.append(
            {
                "id": "analysis",
                "type": "ask.oracle",
                "depends_on": dependency_tail,
                "input": {
                    "prompt": text,
                    "model": default_oracle_model or DEFAULT_ORACLE_MODEL,
                    "reasoning_effort": DEFAULT_ORACLE_REASONING,
                },
            }
        )
        dependency_tail = ["analysis"]

    if wants_coding and prefer_agent_coding:
        worker_id = (agent_worker_id or "").strip() or default_coding_worker_id()
        nodes.append(
            {
                "id": "implement",
                "type": "scillm.agent_turn",
                "depends_on": dependency_tail,
                "input": {
                    "worker_id": worker_id,
                    "operation": "launch",
                    "goal": text,
                    "sandbox": "workspace-write",
                    "phase_id": "ask-dag-implement",
                },
            }
        )
        dependency_tail = ["implement"]
    else:
        skill_nodes = [skill for skill in non_coding_skill_mentions if skill != "create-report"]
        for skill in skill_nodes:
            node_id = _safe_node_id(skill)
            nodes.append(
                {
                    "id": node_id,
                    "type": "skill.run",
                    "depends_on": dependency_tail,
                    "input": {"skill": skill, "args": []},
                }
            )
            dependency_tail = [node_id]

    if wants_report:
        nodes.append(
            {
                "id": "final_report",
                "type": "ask.report",
                "depends_on": dependency_tail,
                "input": {
                    "title": "Ask DAG Report",
                    "timeout": 120,
                },
            }
        )

    return validate_ask_dag(
        {
            "schema_version": ASK_DAG_SCHEMA_VERSION,
            "graph_id": "ask-natural-language-orchestration",
            "description": "Drafted by /ask from a natural-language orchestration request.",
            "max_concurrency": max_concurrency,
            "nodes": nodes,
        }
    )




def build_persona_review_implement_dag(
    question: str,
    *,
    scope: str = "ask",
    persona: str = "Brandon",
    review_files: list[str] | None = None,
    agent_worker_id: str | None = None,
    include_dogpile: bool = True,
    include_debugger_escalation: bool = False,
    max_concurrency: int = 4,
) -> dict[str, Any]:
    """Canonical persona → review-code → consult → scillm.agent_turn workflow."""
    from .skills_exec import SKILL_ROOT

    text = question.strip()
    if not text:
        raise AskDagError("Cannot build persona-review-implement DAG for an empty question.")
    target_files = list(review_files or [str((SKILL_ROOT / "examples" / "sample_target.py").resolve())])
    worker_id = (agent_worker_id or "").strip() or default_coding_worker_id(persona=persona)
    review_context = (
        f"Persona: {persona}. Review before bounded implementation. "
        f"Question: {text}"
    )
    implement_goal = (
        f"{persona} implementation turn for /ask DAG example.\n\n"
        f"Task: {text}\n\n"
        "Upstream artifacts: persona brief, /review-code findings, memory recall, optional dogpile.\n\n"
        "When blocked (missing API docs, unknown library behavior, or conflicting prior art):\n"
        "1. Consult /memory recall --brief for prior lessons and skill chains.\n"
        "2. If still blocked, run /dogpile search with persona, rationale, and problem context.\n"
        "3. Only then continue implementation inside the worker declared_write_set.\n\n"
        "When stuck on a runtime error and the next patch depends on actual variable state:\n"
        "use /debugger before guessing. Set breakpoints at the failing transition, run the real repro,\n"
        "inspect paused locals/watches, report breakpoint file:line and observed values, then patch.\n"
        "Do not replace debugger proof with log skims or static inference alone.\n\n"
        "Do not use /v1/chat/completions for coding; you are on a standing scillm agent worker."
    )
    nodes: list[dict[str, Any]] = [
        {
            "id": "memory_first",
            "type": "memory.recall",
            "allow_failure": True,
            "input": {"query": text, "scope": scope, "k": 8},
        },
        {
            "id": "persona_brief",
            "type": "ask.oracle",
            "depends_on": ["memory_first"],
            "input": {
                "persona": persona,
                "prompt": (
                    f"As {persona}, state review priorities and acceptance criteria for:\n{text}\n\n"
                    "Use memory context only as background, not as sole evidence."
                ),
                "model": DEFAULT_ORACLE_MODEL,
                "reasoning_effort": DEFAULT_ORACLE_REASONING,
            },
        },
        {
            "id": "code_review",
            "type": "skill.run",
            "depends_on": ["persona_brief"],
            "input": {
                "skill": "review-code",
                "args": [
                    "one-shot",
                    "--context",
                    review_context,
                    "--persona",
                    persona.lower(),
                    "--model",
                    DEFAULT_ORACLE_MODEL,
                    "--single",
                    *[item for path in target_files for item in ("--file", path)],
                ],
                "timeout": 600,
            },
        },
        {
            "id": "memory_consult",
            "type": "memory.recall",
            "depends_on": ["code_review"],
            "allow_failure": True,
            "input": {
                "query": f"When blocked on: {text}. Prior fixes, skill chains, and lessons.",
                "scope": scope,
                "k": 5,
            },
        },
    ]
    dependency_tail = ["memory_consult"]
    if include_dogpile:
        nodes.append(
            {
                "id": "dogpile_consult",
                "type": "dogpile.search",
                "depends_on": ["memory_consult"],
                "allow_failure": True,
                "input": {
                    "query": text,
                    "persona": persona.lower(),
                    "rationale": f"Consult when blocked during implementation: {text[:200]}",
                    "context": review_context,
                    "auto_preset": True,
                    "timeout": 420,
                },
            }
        )
        dependency_tail = ["dogpile_consult"]
    if include_debugger_escalation:
        sample_path = target_files[0]
        proof_path = str((SKILL_ROOT / "examples" / "debugger-proof.json").resolve())
        nodes.append(
            {
                "id": "debugger_stuck",
                "type": "skill.run",
                "depends_on": ["code_review"],
                "allow_failure": True,
                "input": {
                    "skill": "debugger",
                    "args": [
                        "--break",
                        f"{sample_path}:7",
                        "--local",
                        "raw",
                        "--local",
                        "candidate",
                        "--out",
                        proof_path,
                        "--",
                        "python3",
                        str((SKILL_ROOT / "examples" / "debug_repro.py").resolve()),
                    ],
                    "timeout": 120,
                },
            }
        )
        dependency_tail = [*(["dogpile_consult"] if include_dogpile else ["memory_consult"]), "debugger_stuck"]
    nodes.append(
        {
            "id": "implement",
            "type": "scillm.agent_turn",
            "depends_on": dependency_tail,
            "input": {
                "worker_id": worker_id,
                "operation": "launch",
                "goal": implement_goal,
                "sandbox": "workspace-write",
                "phase_id": "ask-persona-review-implement",
                "result_timeout_seconds": 900,
            },
        }
    )
    return validate_ask_dag(
        {
            "schema_version": ASK_DAG_SCHEMA_VERSION,
            "graph_id": "ask-persona-review-implement",
            "description": "Persona brief, review-code, memory/dogpile consult, scillm agent implementation.",
            "max_concurrency": max_concurrency,
            "nodes": nodes,
        }
    )


def natural_language_dag_attention(error: Exception) -> dict[str, Any]:
    return {
        "reason": "dag_orchestration_ambiguous",
        "question": str(error),
        "safe_default": "clarify_before_dag_execution",
        "resume_hint": "Run /interview to identify the target skills, required outputs, and acceptance criteria, then rerun /ask with --orchestrate.",
        "suggested_skills": ["/interview"],
        "clarification_options": [
            "Name the target skill or skills to orchestrate.",
            "Name the expected output artifact.",
            "Provide acceptance criteria for the generated DAG.",
        ],
    }


def _extract_skill_mentions_from_text(text: str) -> list[str]:
    return sorted({
        dollar or slash
        for dollar, slash in re.findall(
            r"(?<![\w/])(?:\$([A-Za-z][A-Za-z0-9_-]{1,80})|/(?!home/|tmp/|mnt/|var/|usr/|etc/|opt/|run/)([A-Za-z][A-Za-z0-9_-]{1,80})\b(?!/))",
            text,
        )
        if dollar or slash
    })


def _safe_node_id(skill: str) -> str:
    node_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", skill.strip()).strip("-._")
    if not node_id:
        raise AskDagError(f"Unable to derive a safe node id from skill {skill!r}.")
    return node_id[:80]


def _normalize_scillm_exec_graph(dag: dict[str, Any], *, base_dir: Path | None = None) -> dict[str, Any]:
    """Normalize the scillm DAG mockup/runtime shape into ask.dag.v1."""
    nodes = dag.get("nodes")
    if not isinstance(nodes, list):
        raise AskDagError("scillm exec graph requires a nodes list.")
    normalized_nodes: list[dict[str, Any]] = []
    for index, raw_node in enumerate(nodes, 1):
        if not isinstance(raw_node, dict):
            raise AskDagError(f"scillm exec graph node {index} must be an object.")
        execution = raw_node.get("execution") or {}
        if not isinstance(execution, dict):
            raise AskDagError(f"scillm exec graph node {index} execution must be an object.")
        call_type = str(execution.get("call_type") or raw_node.get("call_type") or "one-shot").strip().lower()
        node_type = str(raw_node.get("type") or "").strip()
        node_input = raw_node.get("input") if isinstance(raw_node.get("input"), dict) else {}

        if not node_type:
            if call_type in {"one-shot", "oneshot", "llm", "oracle", "ask.oracle"}:
                node_type = "ask.oracle"
            elif call_type in {"memory.recall", "memory", "recall"}:
                node_type = "memory.recall"
            elif call_type in {"dogpile.search", "dogpile", "research"}:
                node_type = "dogpile.search"
            elif call_type in {"report", "ask.report", "create-report"}:
                node_type = "ask.report"
            elif call_type in {"skill.run", "skill", "subagent", "subagent-runner"}:
                node_type = "skill.run"
            elif call_type in {"scillm.agent_turn", "agent_turn", "agent-turn", "implementation", "implement"}:
                node_type = "scillm.agent_turn"
            else:
                raise AskDagError(f"scillm exec graph node {raw_node.get('id', index)!r} has unsupported call_type {call_type!r}.")

        if node_type == "ask.oracle":
            model, reasoning = _parse_scillm_model_spec(str(execution.get("model") or node_input.get("model") or ""))
            prompt = _prompt_from_scillm_node(raw_node, base_dir=base_dir)
            node_input = {
                **node_input,
                "prompt": prompt,
                **({"model": model} if model else {}),
                **({"reasoning_effort": reasoning} if reasoning else {}),
            }
        elif node_type == "skill.run":
            skill = str(node_input.get("skill") or execution.get("skill") or "").strip()
            args = node_input.get("args", execution.get("args", []))
            if call_type in {"subagent", "subagent-runner"} and not skill:
                skill = "subagent-runner"
            if isinstance(args, str):
                args = [args]
            node_input = {**node_input, "skill": skill, "args": args}
        elif node_type == "scillm.agent_turn":
            goal = _prompt_from_scillm_node(raw_node, base_dir=base_dir)
            node_input = {
                **node_input,
                "goal": str(node_input.get("goal") or node_input.get("prompt") or goal),
                "worker_id": str(node_input.get("worker_id") or execution.get("worker_id") or ""),
                "operation": str(node_input.get("operation") or execution.get("operation") or "launch"),
                "sandbox": str(node_input.get("sandbox") or execution.get("sandbox") or "workspace-write"),
                "phase_id": str(node_input.get("phase_id") or execution.get("phase_id") or "ask-dag-implement"),
            }
        elif node_type == "ask.report":
            node_input = {
                **node_input,
                "title": str(node_input.get("title") or execution.get("title") or raw_node.get("title") or "Ask DAG Report"),
            }
        elif node_type in {"memory.recall", "dogpile.search"}:
            query = raw_node.get("query", execution.get("query", node_input.get("query", node_input.get("q", ""))))
            if query:
                node_input = {**node_input, "query": str(query)}

        normalized_nodes.append({
            **raw_node,
            "type": node_type,
            "depends_on": raw_node.get("depends_on", []),
            "input": node_input,
        })
    return {
        "schema_version": ASK_DAG_SCHEMA_VERSION,
        "source_graph_version": SCILLM_EXEC_GRAPH_VERSION,
        "graph_id": str(dag.get("graph_id") or ""),
        "description": str(dag.get("description") or dag.get("graph_goal") or ""),
        "max_concurrency": dag.get("max_concurrency", 8),
        "nodes": normalized_nodes,
    }


def _parse_scillm_model_spec(model_spec: str) -> tuple[str, str]:
    spec = model_spec.strip()
    if not spec:
        return "", ""
    parts = spec.split()
    reasoning = ""
    lowered = {part.lower() for part in parts[1:]}
    if "xhigh" in lowered:
        reasoning = "xhigh"
    elif "high" in lowered:
        reasoning = "high"
    elif "medium" in lowered:
        reasoning = "medium"
    elif "low" in lowered:
        reasoning = "low"
    if len(parts) >= 2 and parts[0].lower() == "gpt" and re.fullmatch(r"\d+(?:\.\d+)?", parts[1]):
        model = f"gpt-{parts[1]}"
    else:
        model = parts[0]
    return model, reasoning


def _prompt_from_scillm_node(raw_node: dict[str, Any], *, base_dir: Path | None) -> str:
    prompt = raw_node.get("prompt")
    if isinstance(prompt, str) and prompt.strip():
        return prompt
    prompt_payload = raw_node.get("prompt_payload")
    if isinstance(prompt_payload, dict):
        payload_prompt = prompt_payload.get("prompt") or prompt_payload.get("user_prompt") or prompt_payload.get("content")
        if isinstance(payload_prompt, str) and payload_prompt.strip():
            return payload_prompt
        return json.dumps(prompt_payload, indent=2, sort_keys=True)
    if isinstance(prompt_payload, list):
        return json.dumps(prompt_payload, indent=2, sort_keys=True)
    if isinstance(prompt_payload, str) and prompt_payload.strip():
        payload_text = _read_prompt_payload_if_file(prompt_payload, base_dir=base_dir)
        if payload_text:
            return payload_text
        return prompt_payload
    title = str(raw_node.get("title") or raw_node.get("id") or "").strip()
    return title


def _read_prompt_payload_if_file(value: str, *, base_dir: Path | None) -> str:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute() and base_dir is not None:
        candidate = base_dir / candidate
    try:
        if candidate.is_file() and candidate.stat().st_size <= 256_000:
            return candidate.read_text(encoding="utf-8")
    except OSError:
        return ""
    return ""


def load_ask_dag(*, dag_json: str = "", dag_file: str = "") -> dict[str, Any] | None:
    """Load DAG JSON from an inline string or a file path."""
    if dag_json and dag_file:
        raise AskDagError("Use either --dag-json or --dag-file, not both.")
    if not dag_json and not dag_file:
        return None
    try:
        base_dir = Path.cwd()
        if dag_file:
            dag_path = Path(dag_file).expanduser()
            raw = dag_path.read_text(encoding="utf-8")
            base_dir = dag_path.resolve().parent
        else:
            raw = dag_json
        payload = json.loads(raw)
    except OSError as exc:
        raise AskDagError(f"Unable to read DAG file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise AskDagError(f"DAG JSON is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise AskDagError("DAG JSON must be an object.")
    return validate_ask_dag(payload, base_dir=base_dir)


def validate_ask_dag(dag: dict[str, Any], *, base_dir: Path | None = None) -> dict[str, Any]:
    """Validate and normalize an ask DAG without executing it."""
    if dag.get("exec_graph_version") == SCILLM_EXEC_GRAPH_VERSION:
        dag = _normalize_scillm_exec_graph(dag, base_dir=base_dir)
    version = str(dag.get("schema_version") or ASK_DAG_SCHEMA_VERSION)
    if version != ASK_DAG_SCHEMA_VERSION:
        raise AskDagError(f"Unsupported DAG schema_version {version!r}; expected {ASK_DAG_SCHEMA_VERSION}.")
    nodes = dag.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise AskDagError("DAG requires a non-empty nodes list.")
    seen: set[str] = set()
    normalized_nodes: list[dict[str, Any]] = []
    for index, raw_node in enumerate(nodes, 1):
        if not isinstance(raw_node, dict):
            raise AskDagError(f"DAG node {index} must be an object.")
        node_id = str(raw_node.get("id") or "").strip()
        node_type = str(raw_node.get("type") or "").strip()
        if not NODE_ID_RE.fullmatch(node_id) or node_id in {".", ".."}:
            raise AskDagError(f"DAG node {index} has an unsafe id {node_id!r}.")
        if node_id in seen:
            raise AskDagError(f"DAG node id {node_id!r} is duplicated.")
        if node_type not in ALLOWED_NODE_TYPES:
            raise AskDagError(f"DAG node {node_id!r} has unsupported type {node_type!r}.")
        depends_on = raw_node.get("depends_on", [])
        if depends_on is None:
            depends_on = []
        if isinstance(depends_on, str):
            depends_on = [depends_on]
        if not isinstance(depends_on, list) or not all(isinstance(item, str) for item in depends_on):
            raise AskDagError(f"DAG node {node_id!r} depends_on must be a string list.")
        node_input = raw_node.get("input", {})
        if not isinstance(node_input, dict):
            raise AskDagError(f"DAG node {node_id!r} input must be an object.")
        max_attempts = raw_node.get("max_attempts", 1)
        if not isinstance(max_attempts, int) or max_attempts < 1 or max_attempts > 10:
            raise AskDagError(f"DAG node {node_id!r} max_attempts must be an integer from 1 to 10.")
        allow_failure = raw_node.get("allow_failure", False)
        if not isinstance(allow_failure, bool):
            raise AskDagError(f"DAG node {node_id!r} allow_failure must be a boolean.")
        if node_type == "skill.run":
            skill = str(node_input.get("skill") or "").strip()
            allowed_skills = available_skill_run_skills()
            if skill not in allowed_skills:
                allowed = ", ".join(sorted(COMMON_SKILL_RUN_SKILLS & allowed_skills))
                raise AskDagError(
                    f"DAG node {node_id!r} skill.run skill {skill!r} does not have a runnable sibling skill contract. "
                    f"Common allowed skills include: {allowed}."
                )
            args = node_input.get("args", [])
            if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
                raise AskDagError(f"DAG node {node_id!r} skill.run args must be a string list.")
        elif node_type == "scillm.agent_turn":
            operation = str(node_input.get("operation") or "launch").strip().lower()
            if operation not in {"launch", "steer"}:
                raise AskDagError(f"DAG node {node_id!r} scillm.agent_turn operation must be launch or steer.")
            goal = str(node_input.get("goal") or node_input.get("prompt") or "").strip()
            if operation == "launch" and not goal:
                raise AskDagError(f"DAG node {node_id!r} scillm.agent_turn requires goal or prompt for launch.")
            sandbox = str(node_input.get("sandbox") or "workspace-write").strip()
            if sandbox not in {"read-only", "workspace-write"}:
                raise AskDagError(f"DAG node {node_id!r} scillm.agent_turn sandbox must be read-only or workspace-write.")
            worker_id = str(node_input.get("worker_id") or "").strip()
            if worker_id:
                try:
                    from .scillm_agents import validate_agent_identifier

                    validate_agent_identifier("worker_id", worker_id, "dag")
                except ValueError as exc:
                    raise AskDagError(str(exc)) from exc
            timeout = node_input.get("timeout", node_input.get("result_timeout_seconds", 900))
            if not isinstance(timeout, (int, float)) or timeout <= 0 or timeout > 7200:
                raise AskDagError(f"DAG node {node_id!r} scillm.agent_turn timeout must be between 1 and 7200 seconds.")
        elif node_type == "ask.report":
            title = str(node_input.get("title") or "Ask DAG Report").strip()
            if not title:
                raise AskDagError(f"DAG node {node_id!r} ask.report title must be non-empty.")
        normalized_nodes.append({
            **raw_node,
            "id": node_id,
            "type": node_type,
            "depends_on": depends_on,
            "input": node_input,
            "max_attempts": max_attempts,
            "allow_failure": allow_failure,
        })
        seen.add(node_id)
    missing = {
        dependency
        for node in normalized_nodes
        for dependency in node["depends_on"]
        if dependency not in seen
    }
    if missing:
        raise AskDagError(f"DAG has unknown dependencies: {sorted(missing)}.")
    _topological_order(normalized_nodes)
    max_concurrency = dag.get("max_concurrency", 8)
    if not isinstance(max_concurrency, int) or max_concurrency < 1 or max_concurrency > 32:
        raise AskDagError("DAG max_concurrency must be an integer from 1 to 32.")
    return {
        "schema_version": ASK_DAG_SCHEMA_VERSION,
        "description": str(dag.get("description") or ""),
        "source_graph_version": str(dag.get("source_graph_version") or ""),
        "graph_id": str(dag.get("graph_id") or ""),
        "max_concurrency": max_concurrency,
        "nodes": normalized_nodes,
    }


def dag_execution_layers(dag: dict[str, Any]) -> list[dict[str, Any]]:
    """Summarize topological layers for dry-run charts and telemetry."""
    layers = _topological_layers(dag["nodes"])
    return [
        {
            "layer_index": index,
            "concurrent": len(layer) > 1,
            "node_ids": [node["id"] for node in layer],
            "nodes": [
                {
                    "id": node["id"],
                    "type": node["type"],
                    "depends_on": node.get("depends_on", []),
                    "allow_failure": bool(node.get("allow_failure")),
                }
                for node in layer
            ],
        }
        for index, layer in enumerate(layers, 1)
    ]


def _node_box_lines(node: dict[str, Any], width: int) -> list[str]:
    """Render one mockup-style decision-tree node box."""
    width = max(width, 16)
    title = str(node["id"])[: width - 2]
    kind = str(node["type"])[: width - 2]
    marker = "opt" if node.get("allow_failure") else "req"
    inner_w = width - 2
    return [
        f"┌{'─' * inner_w}┐",
        f"│ {title.ljust(inner_w - 1)}│",
        f"│ {kind.ljust(inner_w - 1)}│",
        f"│ [{marker}]".ljust(width - 1) + "│",
        f"└{'─' * inner_w}┘",
    ]


def _place_boxes_side_by_side(boxes: list[list[str]], gap: int = 3) -> tuple[list[str], list[int], int]:
    if not boxes:
        return [], [], 0
    height = max(len(box) for box in boxes)
    widths = [max(len(line) for line in box) for box in boxes]
    padded: list[list[str]] = []
    for box, w in zip(boxes, widths):
        rows = [line.ljust(w) for line in box]
        padded.append(rows + ["".ljust(w)] * (height - len(rows)))
    segment_widths = widths[:-1] + [widths[-1]]
    for idx in range(len(segment_widths) - 1):
        segment_widths[idx] += gap
    total_width = sum(segment_widths)
    lines = ["".ljust(total_width) for _ in range(height)]
    centers: list[int] = []
    offset = 0
    for idx, box in enumerate(padded):
        w = widths[idx]
        for row_idx, row in enumerate(box):
            lines[row_idx] = lines[row_idx][:offset] + row + lines[row_idx][offset + w :]
        centers.append(offset + w // 2)
        offset += segment_widths[idx]
    return lines, centers, total_width


def _blank_row(width: int) -> list[str]:
    return [" "] * width


def _connect_layers(parent_cols: list[int], child_cols: list[int], width: int) -> list[str]:
    """Draw decision-tree connectors between two topological layers."""
    rows: list[list[str]] = []
    if not parent_cols or not child_cols:
        return []

    if len(parent_cols) == 1 and len(child_cols) == 1:
        parent_col, child_col = parent_cols[0], child_cols[0]
        if parent_col == child_col:
            row = _blank_row(width)
            row[parent_col] = "│"
            rows.append(row)
            rows.append(list(row))
            return ["".join(r) for r in rows]
        left = min(parent_col, child_col)
        right = max(parent_col, child_col)
        top = _blank_row(width)
        top[parent_col] = "│"
        bridge = _blank_row(width)
        for col in range(left, right + 1):
            bridge[col] = "─"
        bridge[child_col] = "┬"
        bottom = _blank_row(width)
        bottom[child_col] = "│"
        return ["".join(top), "".join(bridge), "".join(bottom)]

    if len(parent_cols) == 1 and len(child_cols) > 1:
        parent_col = parent_cols[0]
        top = _blank_row(width)
        top[parent_col] = "│"
        bridge = _blank_row(width)
        left = min(child_cols)
        right = max(child_cols)
        for col in range(left, right + 1):
            bridge[col] = "─"
        for col in child_cols:
            bridge[col] = "┬"
        stems = _blank_row(width)
        for col in child_cols:
            stems[col] = "│"
        return ["".join(top), "".join(bridge), "".join(stems)]

    # fan-in (many parents → one child)
    stems = _blank_row(width)
    for col in parent_cols:
        stems[col] = "│"
    rows.append(stems)
    bridge = _blank_row(width)
    merge_cols = parent_cols + child_cols
    left = min(merge_cols)
    right = max(merge_cols)
    for col in range(left, right + 1):
        bridge[col] = "─"
    bridge[child_cols[0]] = "┴"
    bottom = _blank_row(width)
    bottom[child_cols[0]] = "│"
    rows.extend([bridge, bottom])
    return ["".join(r) for r in rows]


def _format_dag_ascii_chart_fallback(dag: dict[str, Any]) -> str:
    """Fallback renderer when PHART is unavailable."""
    graph_id = str(dag.get("graph_id") or dag.get("source_graph_id") or "ask-dag")
    schema = str(dag.get("schema_version") or dag.get("source_graph_version") or ASK_DAG_SCHEMA_VERSION)
    goal = str(dag.get("graph_goal") or "").strip()
    max_concurrency = int(dag.get("max_concurrency", 8))
    layers = dag_execution_layers(dag)

    header = [
        "```text",
        f"DAG decision tree · {graph_id}",
        f"schema={schema} · max_concurrency={max_concurrency}",
    ]
    if goal:
        header.append(f"goal: {goal}")
    header.append("req=required (fail-closed) · opt=allow_failure")
    header.append("")

    if not layers:
        header.append("(empty graph)")
        header.append("```")
        return "\n".join(header)

    rendered_layers: list[tuple[list[str], list[int], int]] = []
    for layer in layers:
        boxes = [
            _node_box_lines(node, max(16, len(node["id"]) + 6, len(node["type"]) + 4))
            for node in layer["nodes"]
        ]
        rendered_layers.append(_place_boxes_side_by_side(boxes))

    canvas_width = max(width for _, _, width in rendered_layers)

    canvas: list[str] = []
    prev_centers: list[int] = []

    for layer_index, (row_lines, centers, row_width) in enumerate(rendered_layers):
        left_pad = (canvas_width - row_width) // 2
        abs_centers = [center + left_pad for center in centers]
        if prev_centers:
            canvas.extend(_connect_layers(prev_centers, abs_centers, canvas_width))
        canvas.extend(" " * left_pad + line for line in row_lines)
        prev_centers = abs_centers

    footer = [
        "",
        "flow: top → bottom · siblings on one row = concurrent lane (see DAG-ux-mockup.html)",
    ]
    return "\n".join(header + canvas + footer + ["```"])


def _phart_display_name(node: dict[str, Any]) -> str:
    """Compact node label for PHART boxes (id + short type + optional marker)."""
    short_type = str(node["type"]).split(".")[-1]
    suffix = "?" if node.get("allow_failure") else ""
    name = f"{node['id']}:{short_type}{suffix}"
    return name[:32]


def _dag_to_networkx(dag: dict[str, Any]):
    """Build a NetworkX DiGraph from an ask DAG for PHART rendering."""
    if nx is None:
        return None
    graph = nx.DiGraph()
    for node in dag["nodes"]:
        graph.add_node(_phart_display_name(node), ask_id=node["id"], node_type=node["type"])
    for node in dag["nodes"]:
        child = _phart_display_name(node)
        for parent_id in node.get("depends_on", []):
            parent = next(
                (n for n in dag["nodes"] if n["id"] == parent_id),
                None,
            )
            if parent is None:
                continue
            graph.add_edge(_phart_display_name(parent), child)
    return graph


PHART_GIT_REPO = "https://github.com/scottvr/phart.git"
PHART_DAG_CHART_DIR = Path(__file__).resolve().parents[2].parent / "phart-dag-chart"
# Legacy nested renderer; prefer phart-dag-chart skill
PHART_RENDERER_DIR = PHART_DAG_CHART_DIR


def _format_dag_ascii_chart_phart_git(dag: dict[str, Any]) -> str | None:
    """Render via $phart-dag-chart skill (PHART 1.5 git, Python 3.14)."""
    uv_bin = "uv"
    project_dir = PHART_DAG_CHART_DIR
    if not (project_dir / "pyproject.toml").is_file():
        return None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".dag.json", delete=False, encoding="utf-8") as handle:
            json.dump(dag, handle, indent=2)
            handle.flush()
            dag_path = Path(handle.name)
        proc = subprocess.run(
            [uv_bin, "run", "--directory", str(project_dir), "phart-dag-chart", "chart", str(dag_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )
        dag_path.unlink(missing_ok=True)
        if proc.returncode != 0:
            return None
        out = proc.stdout.strip()
        if not out and proc.stderr.strip():
            return None
        return out or None
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def _format_dag_ascii_chart_phart_pypi(dag: dict[str, Any]) -> str | None:
    """Render DAG via PHART PyPI (1.1.x, in-process, Python 3.11–3.12)."""
    if ASCIIRenderer is None or nx is None:
        return None
    graph = _dag_to_networkx(dag)
    if graph is None or graph.number_of_nodes() == 0:
        return None
    try:
        renderer = ASCIIRenderer(
            graph,
            layer_spacing=3,
            node_spacing=5,
        )
        body = renderer.render().rstrip()
    except Exception:
        return None
    graph_id = str(dag.get("graph_id") or dag.get("source_graph_id") or "ask-dag")
    schema = str(dag.get("schema_version") or dag.get("source_graph_version") or ASK_DAG_SCHEMA_VERSION)
    goal = str(dag.get("graph_goal") or "").strip()
    header = [
        "```text",
        f"DAG decision tree · {graph_id} (phart pypi)",
        f"schema={schema} · max_concurrency={dag.get('max_concurrency', 8)}",
    ]
    if goal:
        header.append(f"goal: {goal}")
    header.append("node label: id:short_type  (? = allow_failure)")
    header.append("")
    footer = [
        "",
        "renderer: phart (pypi) · upgrade: phart-dag-chart skill uses github.com/scottvr/phart",
    ]
    return "\n".join(header + [body] + footer + ["```"])


def _format_dag_ascii_chart_phart(dag: dict[str, Any]) -> str | None:
    """Prefer PHART 1.5 git (bboxes); fall back to in-process PyPI phart."""
    return _format_dag_ascii_chart_phart_git(dag) or _format_dag_ascii_chart_phart_pypi(dag)


def format_dag_ascii_chart(dag: dict[str, Any], *, prefer_phart: bool = True) -> str:
    """Render terminal DAG chart; PHART when installed, else built-in fallback."""
    if prefer_phart:
        phart_chart = _format_dag_ascii_chart_phart(dag)
        if phart_chart:
            return phart_chart
    return _format_dag_ascii_chart_fallback(dag)


def dag_ascii_renderer_name(dag: dict[str, Any] | None = None) -> str:
    """Report which renderer would be used (phart-git|phart-pypi|fallback)."""
    if dag is not None:
        if _format_dag_ascii_chart_phart_git(dag) is not None:
            return "phart-git"
        if _format_dag_ascii_chart_phart_pypi(dag) is not None:
            return "phart-pypi"
    return "fallback"


def dag_dry_run_summary(dag: dict[str, Any] | None) -> dict[str, Any] | None:
    if not dag:
        return None
    layers = dag_execution_layers(dag)
    return {
        "schema_version": ASK_DAG_SCHEMA_VERSION,
        "source_graph_version": dag.get("source_graph_version", ""),
        "graph_id": dag.get("graph_id", ""),
        "max_concurrency": dag.get("max_concurrency", 8),
        "node_count": len(dag["nodes"]),
        "layer_count": len(layers),
        "layers": layers,
        "ascii_chart": format_dag_ascii_chart(dag),
        "ascii_renderer": dag_ascii_renderer_name(dag),
        "nodes": [
            {
                "id": node["id"],
                "type": node["type"],
                "depends_on": node.get("depends_on", []),
            }
            for node in _topological_order(dag["nodes"])
        ],
    }


def execute_ask_dag(
    dag: dict[str, Any],
    *,
    question: str,
    scope: str,
    run_state: AskRunState,
    oracle_model: str | None = None,
    oracle_reasoning: str = DEFAULT_ORACLE_REASONING,
    oracle_timeout: float = DEFAULT_ORACLE_TIMEOUT,
    oracle_image_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Execute a validated ask DAG and return context items for synthesis."""
    ordered_nodes = _topological_order(dag["nodes"])
    layers = _topological_layers(dag["nodes"])
    dag_dir = run_state.run_dir / "dag"
    dag_dir.mkdir(parents=True, exist_ok=True)
    context: dict[str, dict[str, Any]] = {}
    context_items: list[dict[str, Any]] = []
    max_concurrency = int(dag.get("max_concurrency") or 8)
    run_state.event(
        "dag_started",
        schema_version=ASK_DAG_SCHEMA_VERSION,
        source_graph_version=dag.get("source_graph_version", ""),
        node_count=len(ordered_nodes),
        max_concurrency=max_concurrency,
    )
    for layer_index, layer in enumerate(layers, 1):
        run_state.event(
            "dag_layer_started",
            layer_index=layer_index,
            node_ids=[node["id"] for node in layer],
            concurrent=len(layer) > 1,
        )
        for node in layer:
            run_state.step_started("dag_node", node_id=node["id"], node_type=node["type"], layer_index=layer_index)
        with ThreadPoolExecutor(max_workers=min(len(layer), max_concurrency)) as executor:
            futures = {}
            oracle_nodes = [node for node in layer if node["type"] == "ask.oracle"]
            other_nodes = [node for node in layer if node["type"] != "ask.oracle"]
            if oracle_nodes:
                futures[
                    executor.submit(
                        _execute_scillm_oracle_partition,
                        oracle_nodes,
                        question=question,
                        run_state=run_state,
                        dag_dir=dag_dir,
                        context=dict(context),
                        oracle_model=oracle_model or DEFAULT_ORACLE_MODEL,
                        oracle_reasoning=oracle_reasoning,
                        oracle_timeout=oracle_timeout,
                        oracle_image_paths=oracle_image_paths or [],
                        max_concurrency=max_concurrency,
                        layer_index=layer_index,
                    )
                ] = {"id": "__scillm_partition__", "type": "scillm.partition", "nodes": oracle_nodes}
            for node in other_nodes:
                futures[
                    executor.submit(
                        _execute_node_with_retries,
                        node,
                        question=question,
                        scope=scope,
                        run_state=run_state,
                        dag_dir=dag_dir,
                        context=dict(context),
                        oracle_model=oracle_model or DEFAULT_ORACLE_MODEL,
                        oracle_reasoning=oracle_reasoning,
                        oracle_timeout=oracle_timeout,
                        oracle_image_paths=oracle_image_paths or [],
                    )
                ] = node
            layer_results: dict[str, dict[str, Any]] = {}
            for future in as_completed(futures):
                node = futures[future]
                node_id = node["id"]
                node_type = node["type"]
                try:
                    result = future.result()
                except Exception as exc:
                    if node_type == "scillm.partition":
                        for partition_node in node["nodes"]:
                            run_state.step_finished("dag_node", node_id=partition_node["id"], node_type=partition_node["type"], ok=False, error=str(exc))
                    else:
                        run_state.step_finished("dag_node", node_id=node_id, node_type=node_type, ok=False, error=str(exc))
                    raise
                results = result.get("nodes", []) if node_type == "scillm.partition" else [result]
                for node_result in results:
                    result_node_id = str(node_result["id"])
                    result_node_type = str(node_result["type"])
                    node_artifact = dag_dir / f"{result_node_id}.json"
                    node_artifact.write_text(json.dumps(node_result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
                    node_result["artifact_path"] = str(node_artifact)
                    layer_results[result_node_id] = node_result
                    run_state.step_finished(
                        "dag_node",
                        node_id=result_node_id,
                        node_type=result_node_type,
                        ok=bool(node_result.get("ok")),
                        context_items_count=len(node_result.get("context_items", [])),
                        artifact_path=str(node_artifact),
                        layer_index=layer_index,
                    )
        for node in layer:
            result = layer_results[node["id"]]
            context[node["id"]] = result
            context_items.extend(result.get("context_items", []))
        failed_required = [
            node
            for node in layer
            if not bool(layer_results[node["id"]].get("ok")) and not bool(node.get("allow_failure"))
        ]
        if failed_required:
            failed_ids = [node["id"] for node in failed_required]
            run_state.event(
                "dag_layer_failed",
                layer_index=layer_index,
                failed_node_ids=failed_ids,
                safe_default="stop_before_dependent_nodes",
            )
            raise AskDagError(f"DAG required node(s) failed: {failed_ids}.")
        run_state.event(
            "dag_layer_finished",
            layer_index=layer_index,
            node_ids=[node["id"] for node in layer],
        )
    manifest = {
        "schema_version": ASK_DAG_SCHEMA_VERSION,
        "source_graph_version": dag.get("source_graph_version", ""),
        "graph_id": dag.get("graph_id", ""),
        "question": question,
        "scope": scope,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "nodes": [
            {
                "id": node_id,
                "type": node_result.get("type"),
                "ok": node_result.get("ok"),
                "artifact_path": node_result.get("artifact_path"),
            }
            for node_id, node_result in context.items()
        ],
        "context_items_count": len(context_items),
    }
    manifest_path = dag_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    run_state.add_artifacts({"dag_manifest": manifest_path})
    run_state.event("dag_finished", context_items_count=len(context_items), manifest_path=str(manifest_path))
    return {
        "schema_version": ASK_DAG_SCHEMA_VERSION,
        "manifest_path": str(manifest_path),
        "nodes": list(context.values()),
        "context_items": context_items,
    }


def _execute_node(
    node: dict[str, Any],
    *,
    question: str,
    scope: str,
    run_state: AskRunState,
    dag_dir: Path,
    context: dict[str, dict[str, Any]],
    oracle_model: str,
    oracle_reasoning: str,
    oracle_timeout: float,
    oracle_image_paths: list[str] | None = None,
) -> dict[str, Any]:
    node_type = node["type"]
    node_input = node["input"]
    if node_type == "memory.recall":
        return _execute_memory_recall(node, question=question, scope=scope)
    if node_type == "dogpile.search":
        return _execute_dogpile_search(node, question=question, context=context)
    if node_type == "skill.run":
        return _execute_skill_run(node, dag_dir=dag_dir, context=context)
    if node_type == "ask.report":
        return _execute_report(node, dag_dir=dag_dir, context=context)
    if node_type == "scillm.agent_turn":
        return _execute_scillm_agent_turn(
            node,
            question=question,
            run_state=run_state,
            context=context,
        )
    if node_type == "ask.oracle":
        return _execute_oracle_node(
            node,
            question=question,
            run_state=run_state,
            dag_dir=dag_dir,
            context=context,
            model=str(node_input.get("model") or oracle_model),
            reasoning_effort=str(node_input.get("reasoning_effort") or oracle_reasoning),
            timeout=float(node_input.get("timeout") or oracle_timeout),
            image_paths=list(node_input.get("image_paths") or oracle_image_paths or []),
        )
    raise AskDagError(f"Unsupported node type {node_type!r}.")


def _execute_node_with_retries(*args: Any, **kwargs: Any) -> dict[str, Any]:
    node = args[0] if args else kwargs.get("node")
    attempts = int(node.get("max_attempts", 1)) if isinstance(node, dict) else 1
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            result = _execute_node(*args, **kwargs)
            result["attempt"] = attempt
            result["max_attempts"] = attempts
            if not result.get("ok"):
                repaired = _auto_repair_node_result(node, result, args=args, kwargs=kwargs)
                if repaired is not None:
                    result = repaired
                    result["attempt"] = attempt
                    result["max_attempts"] = attempts
            if result.get("ok") or attempt >= attempts:
                return result
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                raise
    if last_error:
        raise last_error
    raise AskDagError("DAG node retry loop ended without a result.")


def _auto_repair_node_result(
    node: dict[str, Any] | None,
    result: dict[str, Any],
    *,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, Any] | None:
    """Apply bounded, deterministic repair from config and skill-published hints."""
    if not isinstance(node, dict):
        return None
    run_state = kwargs.get("run_state")
    return apply_dag_repairs(
        node,
        result,
        execute_fn=_execute_node,
        execute_args=args,
        execute_kwargs=kwargs,
        run_state=run_state if isinstance(run_state, AskRunState) else None,
    )


def _execute_scillm_oracle_partition(
    nodes: list[dict[str, Any]],
    *,
    question: str,
    run_state: AskRunState,
    dag_dir: Path,
    context: dict[str, dict[str, Any]],
    oracle_model: str,
    oracle_reasoning: str,
    oracle_timeout: float,
    oracle_image_paths: list[str],
    max_concurrency: int,
    layer_index: int,
) -> dict[str, Any]:
    """Execute the ask.oracle slice of a DAG through scillm-owned model lanes."""
    partition_id = f"layer-{layer_index:03d}-scillm"
    partition_path = dag_dir / f"{partition_id}.subgraph.json"
    subgraph = {
        "exec_graph_version": SCILLM_EXEC_GRAPH_VERSION,
        "partition_id": partition_id,
        "owner": "ask",
        "lane_owner": "scillm",
        "node_ids": [node["id"] for node in nodes],
        "nodes": [
            {
                "id": node["id"],
                "title": node.get("title", node["id"]),
                "depends_on": node.get("depends_on", []),
                "execution": {
                    "call_type": "one-shot",
                    "model": str(node["input"].get("model") or oracle_model),
                    "reasoning_effort": str(node["input"].get("reasoning_effort") or oracle_reasoning),
                },
                "prompt_payload": {
                    "prompt": str(node["input"].get("prompt") or question),
                    "response_format": node["input"].get("response_format", ""),
                    "image_paths": list(node["input"].get("image_paths") or oracle_image_paths or []),
                },
            }
            for node in nodes
        ],
    }
    partition_path.write_text(json.dumps(subgraph, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    run_state.event(
        "dag_scillm_partition_started",
        partition_id=partition_id,
        node_ids=[node["id"] for node in nodes],
        node_count=len(nodes),
        artifact_path=str(partition_path),
    )
    with ThreadPoolExecutor(max_workers=min(len(nodes), max_concurrency)) as executor:
        futures = {
            executor.submit(
                _execute_node_with_retries,
                node,
                question=question,
                scope="ask",
                run_state=run_state,
                dag_dir=dag_dir,
                context=context,
                oracle_model=oracle_model,
                oracle_reasoning=oracle_reasoning,
                oracle_timeout=oracle_timeout,
                oracle_image_paths=oracle_image_paths,
            ): node
            for node in nodes
        }
        results = [future.result() for future in as_completed(futures)]
    run_state.event(
        "dag_scillm_partition_finished",
        partition_id=partition_id,
        node_ids=[result["id"] for result in results],
        ok=all(bool(result.get("ok")) for result in results),
        artifact_path=str(partition_path),
    )
    return {"partition_id": partition_id, "artifact_path": str(partition_path), "nodes": results}


def _execute_memory_recall(node: dict[str, Any], *, question: str, scope: str) -> dict[str, Any]:
    node_input = node["input"]
    query = str(node_input.get("q") or node_input.get("query") or question)
    node_scope = str(node_input.get("scope") or scope)
    k = int(node_input.get("k") or 5)
    timeout = int(node_input.get("timeout") or 15)
    collections = node_input.get("collections")
    tags = node_input.get("tags")
    result = run_memory_recall(
        query,
        node_scope,
        k=k,
        timeout=timeout,
        collections=",".join(collections) if isinstance(collections, list) else collections,
        tags=tags if isinstance(tags, list) else None,
    )
    parsed = parse_json_output(result.get("stdout", "")) or {}
    items = parse_memory_output(result.get("stdout", ""))
    return {
        "id": node["id"],
        "type": node["type"],
        "ok": result["returncode"] == 0,
        "returncode": result["returncode"],
        "stderr": result.get("stderr", ""),
        "payload": parsed,
        "items": items,
        "context_items": [
            {
                **item,
                "via": "ask_dag",
                "dag_node_id": node["id"],
                "dag_node_type": node["type"],
            }
            for item in items
        ],
    }


def _execute_dogpile_search(node: dict[str, Any], *, question: str, context: dict[str, dict[str, Any]]) -> dict[str, Any]:
    node_input = node["input"]
    query = str(node_input.get("q") or node_input.get("query") or question)
    args = ["search", query]
    for option in ("preset", "persona", "rationale", "context", "context-file"):
        value = node_input.get(option.replace("-", "_"), node_input.get(option))
        if value:
            args.extend([f"--{option}", str(value)])
    if node_input.get("auto_preset"):
        args.append("--auto-preset")
    timeout = resolve_node_timeout(node)
    result = run_skill("dogpile", args, timeout=timeout)
    parsed = parse_json_output(result.get("stdout", "")) or {}
    stdout = result.get("stdout", "")
    context_text = json.dumps(parsed, sort_keys=True, default=str) if parsed else stdout
    return {
        "id": node["id"],
        "type": node["type"],
        "ok": result["returncode"] == 0,
        "returncode": result["returncode"],
        "stderr": result.get("stderr", ""),
        "payload": parsed,
        "stdout_excerpt": stdout[:8000],
        "context_items": [{
            "problem": query,
            "solution": context_text[:12000],
            "via": "ask_dag",
            "source": "dogpile",
            "dag_node_id": node["id"],
            "dag_node_type": node["type"],
        }] if context_text.strip() else [],
    }


def _execute_report(node: dict[str, Any], *, dag_dir: Path, context: dict[str, dict[str, Any]]) -> dict[str, Any]:
    node_input = node["input"]
    title = str(node_input.get("title") or "Ask DAG Report").strip() or "Ask DAG Report"
    context_path = dag_dir / f"{node['id']}.context.json"
    output_path = dag_dir / f"{node['id']}.out.md"
    dependency_context = {
        "node_id": node["id"],
        "depends_on": node.get("depends_on", []),
        "dependencies": {
            dependency: context.get(dependency, {})
            for dependency in node.get("depends_on", [])
        },
    }
    context_path.write_text(json.dumps(dependency_context, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    dependency_lines: list[str] = []
    for dependency in node.get("depends_on", []):
        result = context.get(dependency, {})
        dependency_lines.append(
            f"- `{dependency}`: type `{result.get('type', 'unknown')}`, ok `{result.get('ok')}`"
        )
    if not dependency_lines:
        dependency_lines.append("- No dependency nodes were declared.")

    markdown = "\n".join(
        [
            f"# {title}",
            "",
            "## Report Summary",
            "",
            "This report was generated by the internal `$ask` DAG report node from completed dependency receipts.",
            "",
            "## Source-of-Truth Inventory",
            "",
            *dependency_lines,
            "",
            "## Evidence Artifacts",
            "",
            f"- Dependency context JSON: `{context_path}`",
            "",
            "## Non-Claims",
            "",
            "- This report does not prove provider/model semantic correctness.",
            "- This report does not prove downstream skill behavior beyond the dependency receipts it cites.",
            "",
        ]
    )
    output_path.write_text(markdown, encoding="utf-8")
    return {
        "id": node["id"],
        "type": node["type"],
        "ok": True,
        "returncode": 0,
        "payload": {
            "ok": True,
            "report_path": str(output_path),
            "dependency_context_path": str(context_path),
        },
        "stdout_excerpt": json.dumps({"ok": True, "report_path": str(output_path)}, sort_keys=True),
        "stderr": "",
        "dependency_context_path": str(context_path),
        "output_path": str(output_path),
        "context_items": [
            {
                "problem": f"Generate {title}",
                "solution": markdown[:12000],
                "via": "ask_dag",
                "source": "ask.report",
                "dag_node_id": node["id"],
                "dag_node_type": node["type"],
            }
        ],
    }


def _execute_skill_run(node: dict[str, Any], *, dag_dir: Path, context: dict[str, dict[str, Any]]) -> dict[str, Any]:
    node_input = node["input"]
    skill = str(node_input["skill"])
    raw_args = [str(arg) for arg in node_input.get("args", [])]
    context_path = dag_dir / f"{node['id']}.context.json"
    output_path = dag_dir / f"{node['id']}.out.md"
    dependency_context = {
        "node_id": node["id"],
        "depends_on": node.get("depends_on", []),
        "dependencies": {
            dependency: context.get(dependency, {})
            for dependency in node.get("depends_on", [])
        },
    }
    if node.get("depends_on"):
        context_path.write_text(json.dumps(dependency_context, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    args = [
        arg.replace("${dag_context_json}", str(context_path)).replace("${dag_node_output}", str(output_path))
        for arg in raw_args
    ]
    timeout = resolve_node_timeout(node)
    result = run_skill(skill, args, timeout=timeout)
    parsed = parse_json_output(result.get("stdout", "")) or {}
    context_text = json.dumps(parsed, sort_keys=True, default=str) if parsed else result.get("stdout", "")
    report_text = ""
    if output_path.exists():
        try:
            report_text = output_path.read_text(encoding="utf-8")[:12000]
        except OSError:
            report_text = ""
    return {
        "id": node["id"],
        "type": node["type"],
        "skill": skill,
        "ok": result["returncode"] == 0,
        "returncode": result["returncode"],
        "stderr": result.get("stderr", ""),
        "payload": parsed,
        "stdout_excerpt": result.get("stdout", "")[:8000],
        "dependency_context_path": str(context_path) if node.get("depends_on") else "",
        "output_path": str(output_path) if output_path.exists() else "",
        "context_items": [{
            "problem": f"{skill} {' '.join(args)}".strip(),
            "solution": (report_text or context_text)[:12000],
            "via": "ask_dag",
            "source": skill,
            "dag_node_id": node["id"],
            "dag_node_type": node["type"],
        }] if (report_text or context_text).strip() else [],
    }


def _execute_scillm_agent_turn(
    node: dict[str, Any],
    *,
    question: str,
    run_state: AskRunState,
    context: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    node_input = node["input"]
    operation = str(node_input.get("operation") or "launch").strip().lower()
    goal = str(node_input.get("goal") or node_input.get("prompt") or question).strip()
    worker_id = str(node_input.get("worker_id") or "").strip() or default_coding_worker_id()
    sandbox = str(node_input.get("sandbox") or "workspace-write")
    phase_id = str(node_input.get("phase_id") or "ask-dag-implement")
    timeout = float(node_input.get("timeout") or node_input.get("result_timeout_seconds") or 900)
    handoff_id = str(node_input.get("handoff_id") or "")
    lease_id = str(node_input.get("lease_id") or "")
    memory_context = node_input.get("memory_context")
    if not isinstance(memory_context, list):
        memory_context = memory_context_from_dag_dependencies(context)
    run_state.step_started(
        "scillm_agent_turn",
        node_id=node["id"],
        worker_id=worker_id,
        operation=operation,
        sandbox=sandbox,
    )
    try:
        delivery = run_agent_turn(
            worker_id=worker_id,
            operation=operation,
            goal=goal,
            handoff_id=handoff_id,
            lease_id=lease_id,
            phase_id=phase_id,
            ask_id=run_state.ask_id,
            service_name=f"ask-dag-{node['id']}",
            sandbox=sandbox,
            wait_for_result=bool(node_input.get("wait_for_result", True)),
            result_timeout_seconds=float(node_input.get("result_timeout_seconds") or timeout),
            approval_policy=str(node_input.get("approval_policy") or "never"),
            memory_context=memory_context,
            metadata={
                "dag_node_id": node["id"],
                "question": question,
                "depends_on": node.get("depends_on", []),
            },
            steer_input=str(node_input.get("steer_input") or ""),
            timeout=timeout,
        )
        final_text = str(delivery.get("final_text") or "").strip()
        ok = bool(final_text) or operation == "steer"
        run_state.step_finished(
            "scillm_agent_turn",
            ok=ok,
            worker_id=worker_id,
            handoff_id=delivery.get("handoff_id"),
            lease_id=delivery.get("lease_id"),
            result_path=delivery.get("result_path"),
        )
        return {
            "id": node["id"],
            "type": node["type"],
            "ok": ok,
            "worker_id": worker_id,
            "handoff_id": delivery.get("handoff_id"),
            "lease_id": delivery.get("lease_id"),
            "result_path": delivery.get("result_path"),
            "final_text": final_text,
            "delivery": delivery,
            "context_items": [{
                "problem": goal[:500],
                "solution": final_text[:12000],
                "via": "ask_dag",
                "source": "scillm.agent_turn",
                "dag_node_id": node["id"],
                "dag_node_type": node["type"],
                "worker_id": worker_id,
                "handoff_id": delivery.get("handoff_id"),
            }] if final_text else [],
        }
    except (ScillmAgentsError, httpx.HTTPError, ValueError) as exc:
        run_state.step_finished("scillm_agent_turn", ok=False, error=f"{type(exc).__name__}: {exc}")
        return {
            "id": node["id"],
            "type": node["type"],
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "context_items": [],
        }


def _execute_oracle_node(
    node: dict[str, Any],
    *,
    question: str,
    run_state: AskRunState,
    dag_dir: Path,
    context: dict[str, dict[str, Any]],
    model: str,
    reasoning_effort: str,
    timeout: float,
    image_paths: list[str] | None = None,
) -> dict[str, Any]:
    prompt = _build_oracle_prompt(node, question=question, context=context)
    user_content: str | list[dict[str, object]]
    image_parts = _oracle_image_parts(image_paths or [])
    if image_parts:
        user_content = [*image_parts, {"type": "text", "text": prompt}]
    else:
        user_content = prompt
    metadata = build_scillm_metadata(
        ask_id=run_state.ask_id,
        protocol="dag",
        node_id=node["id"],
        node_role="ask_oracle",
        question=prompt,
        artifact_dir=dag_dir,
        extra={"prompt_version": ASK_DAG_SCHEMA_VERSION},
    )
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are executing the scillm-owned model lane for an /ask DAG. "
                    "Answer only the current DAG node prompt. Do not claim support "
                    "outside the supplied DAG context."
                ),
            },
            {"role": "user", "content": user_content},
        ],
        "temperature": _temperature_for_model(model),
        "reasoning_effort": reasoning_effort,
        "stream": True,
        "stream_progress_events": True,
        "timeout": timeout,
        "stream_heartbeat_s": max(5.0, min(15.0, float(timeout) / 20.0)),
        "scillm_metadata": metadata,
    }
    if node["input"].get("response_format") == "json_object":
        body["response_format"] = {"type": "json_object"}
    if image_paths:
        body["oracle_image_paths"] = image_paths
    run_state.event(
        "dag_scillm_node_call_started",
        node_id=node["id"],
        model=model,
        reasoning_effort=reasoning_effort,
        stream=True,
        timeout_seconds=timeout,
        image_count=len(image_paths or []),
    )
    content, model_served, stream_events_path = _call_scillm_chat_stream(
        body,
        timeout=timeout,
        run_state=run_state,
        dag_dir=dag_dir,
        node_id=node["id"],
    )
    payload = {
        "model": model_served,
        "choices": [{"message": {"content": content}}],
        "stream_events_path": stream_events_path,
    }
    run_state.event(
        "dag_scillm_node_call_finished",
        node_id=node["id"],
        model_requested=model,
        model_served=model_served,
        stream=True,
        content_chars=len(content),
        stream_events_path=stream_events_path,
    )
    return _oracle_result_from_content(
        node,
        prompt=prompt,
        content=content,
        model_requested=model,
        model_served=model_served,
        payload=payload,
        metadata=metadata,
        ok=True,
        partition_id="",
        batch_events_path="",
    )


def _oracle_image_parts(image_paths: list[str]) -> list[dict[str, object]]:
    parts: list[dict[str, object]] = []
    for raw_path in image_paths:
        path = Path(raw_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"oracle image path does not exist: {path}")
        if not path.is_file():
            raise ValueError(f"oracle image path is not a file: {path}")
        mime = mimetypes.guess_type(str(path))[0] or "image/png"
        if not mime.startswith("image/"):
            raise ValueError(f"oracle image path is not an image MIME type: {path} ({mime})")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}})
    return parts


def _build_oracle_prompt(node: dict[str, Any], *, question: str, context: dict[str, dict[str, Any]]) -> str:
    prompt = str(node["input"].get("prompt") or question)
    context_text = _render_dependency_context(node, context)
    if context_text:
        prompt = f"{prompt}\n\n## DAG context\n{context_text}"
    return prompt


def _call_scillm_chat_stream(
    body: dict[str, Any],
    *,
    timeout: float,
    run_state: AskRunState,
    dag_dir: Path,
    node_id: str,
) -> tuple[str, str, str]:
    events_path = dag_dir / f"{node_id}.scillm-events.jsonl"
    content_parts: list[str] = []
    model_served = str(body.get("model") or "")
    saw_done = False
    last_progress_at = time.monotonic()
    heartbeat_interval = float(body.get("stream_heartbeat_s") or 5.0)
    timeout_config = httpx.Timeout(
        float(timeout),
        connect=min(10.0, float(timeout)),
        read=max(30.0, heartbeat_interval * 3.0),
        write=30.0,
        pool=10.0,
    )
    with httpx.stream(
        "POST",
        f"{SCILLM_BASE_URL.rstrip('/')}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {SCILLM_API_KEY}",
            "X-Caller-Skill": "ask",
        },
        json=body,
        timeout=timeout_config,
    ) as response:
        response.raise_for_status()
        with events_path.open("w", encoding="utf-8") as events:
            for line in response.iter_lines():
                if not line:
                    continue
                events.write(json.dumps({"line": line}, sort_keys=True) + "\n")
                if line.startswith(":"):
                    now = time.monotonic()
                    if now - last_progress_at >= heartbeat_interval:
                        run_state.event(
                            "dag_scillm_stream_progress",
                            node_id=node_id,
                            model_served=model_served,
                            content_chars=sum(len(part) for part in content_parts),
                            heartbeat=True,
                        )
                        last_progress_at = now
                    continue
                if not line.startswith("data:"):
                    continue
                data_text = line[len("data:"):].strip()
                if data_text == "[DONE]":
                    saw_done = True
                    break
                try:
                    data = json.loads(data_text)
                except json.JSONDecodeError:
                    continue
                if data.get("error"):
                    raise RuntimeError(str(data["error"]))
                model_served = str(data.get("model") or model_served)
                choices = data.get("choices") or []
                if choices and isinstance(choices[0], dict):
                    choice = choices[0]
                    delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
                    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
                    content = delta.get("content")
                    if content is None:
                        content = message.get("content")
                    if content:
                        content_parts.append(str(content))
                now = time.monotonic()
                if now - last_progress_at >= heartbeat_interval:
                    run_state.event(
                        "dag_scillm_stream_progress",
                        node_id=node_id,
                        model_served=model_served,
                        content_chars=sum(len(part) for part in content_parts),
                    )
                    last_progress_at = now
    content = "".join(content_parts)
    if not saw_done and not content:
        raise RuntimeError("scillm stream ended without content or [DONE]")
    return content, model_served, str(events_path)


def _oracle_result_from_content(
    node: dict[str, Any],
    *,
    prompt: str,
    content: str,
    model_requested: str,
    model_served: str,
    payload: dict[str, Any],
    metadata: dict[str, Any],
    ok: bool,
    partition_id: str,
    batch_events_path: str,
) -> dict[str, Any]:
    return {
        "id": node["id"],
        "type": node["type"],
        "ok": ok,
        "model_requested": model_requested,
        "model_served": model_served,
        "scillm_metadata": metadata,
        "partition_id": partition_id,
        "batch_events_path": batch_events_path,
        "payload": payload,
        "content": content,
        "context_items": [{
            "problem": prompt[:500],
            "solution": content,
            "via": "ask_dag",
            "source": "ask.oracle",
            "dag_node_id": node["id"],
            "dag_node_type": node["type"],
        }] if content.strip() else [],
    }


def _extract_chat_content(payload: dict[str, Any]) -> str:
    try:
        choices = payload.get("choices") or []
        message = choices[0].get("message") or {}
        return str(message.get("content") or "")
    except Exception:
        return ""


def _render_dependency_context(node: dict[str, Any], context: dict[str, dict[str, Any]]) -> str:
    blocks: list[str] = []
    for dependency in node.get("depends_on", []):
        node_result = context.get(dependency) or {}
        items = node_result.get("context_items") or []
        if not items:
            continue
        blocks.append(f"### {dependency}")
        for item in items[:5]:
            text = str(item.get("solution") or item.get("answer") or item.get("text") or item.get("problem") or "")
            if text:
                blocks.append(text[:2000])
    return "\n\n".join(blocks).strip()


def _topological_order(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {node["id"]: node for node in nodes}
    indegree = {node["id"]: 0 for node in nodes}
    outgoing: dict[str, list[str]] = {node["id"]: [] for node in nodes}
    for node in nodes:
        for dependency in node.get("depends_on", []):
            indegree[node["id"]] += 1
            outgoing[dependency].append(node["id"])
    queue = deque(sorted(node_id for node_id, degree in indegree.items() if degree == 0))
    ordered_ids: list[str] = []
    while queue:
        node_id = queue.popleft()
        ordered_ids.append(node_id)
        for child_id in sorted(outgoing[node_id]):
            indegree[child_id] -= 1
            if indegree[child_id] == 0:
                queue.append(child_id)
    if len(ordered_ids) != len(nodes):
        raise AskDagError("DAG contains a dependency cycle.")
    return [by_id[node_id] for node_id in ordered_ids]


def _topological_layers(nodes: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    by_id = {node["id"]: node for node in nodes}
    indegree = {node["id"]: 0 for node in nodes}
    outgoing: dict[str, list[str]] = {node["id"]: [] for node in nodes}
    for node in nodes:
        for dependency in node.get("depends_on", []):
            indegree[node["id"]] += 1
            outgoing[dependency].append(node["id"])
    ready = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
    layers: list[list[dict[str, Any]]] = []
    processed = 0
    while ready:
        layer_ids = ready
        ready = []
        layers.append([by_id[node_id] for node_id in layer_ids])
        processed += len(layer_ids)
        for node_id in layer_ids:
            for child_id in sorted(outgoing[node_id]):
                indegree[child_id] -= 1
                if indegree[child_id] == 0:
                    ready.append(child_id)
        ready.sort()
    if processed != len(nodes):
        raise AskDagError("DAG contains a dependency cycle.")
    return layers
