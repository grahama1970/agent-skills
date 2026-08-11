"""Compile deterministic Memory query plans from GitHub ticket contracts.

Inputs are a live GitHub issue or an explicit body file plus a versioned recipe
registry. Outputs are JSON-only planning artifacts: concepts, effective search
steps, selectors, digests, and copy-pasteable diagnostics. This module never
executes Memory retrieval and never mutates GitHub.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import typer
import yaml
from loguru import logger


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SKILL_DIR.parent.parent
DEFAULT_RECIPE_ID = "ticket-repair-context-v1"
CONCEPT_SCHEMA = "ticket.memory_concepts.v1"
PLAN_SCHEMA = "ticket.memory_query_plan.v1"
RECIPES_PATH = SKILL_DIR / "references" / "memory-query-recipes.yaml"
TICKET_MARKER_RE = re.compile(r"<!--\s*ticket-skill(?P<body>.*?)-->", re.DOTALL)
SECTION_RE = re.compile(r"^## (?P<title>.+?)\s*$", re.MULTILINE)
SAFE_PATH_RE = re.compile(r"^(?:[A-Za-z0-9_.@:+-]+/)*[A-Za-z0-9_.@:+-]+/?$")
CODE_ROUTES = {
    "backend_python_or_skill_runtime",
    "frontend_code",
    "rust_or_binary",
    "ops_or_scheduler",
    "security_or_compliance",
}
HUMAN_FIRST_TYPES = {"question", "triage"}


@dataclass(frozen=True, slots=True)
class IssueSource:
    """Validated issue-body source used to compile a plan."""

    number: int | None
    title: str
    body: str
    repo: str | None
    url: str | None = None
    state: str | None = None
    labels: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TicketConcepts:
    """Machine concepts derived only from explicit ticket fields."""

    repository: str | None
    issue_ref: str | None
    issue_number: int | None
    issue_url: str | None
    title: str
    ticket_type: str
    route: str
    requested_agent: str
    lane: str
    target: str
    target_paths: tuple[str, ...]
    current_state: str
    requested_outcome: str
    proof_contract: str
    invariants: tuple[str, ...]
    non_goals: tuple[str, ...]
    context_files: tuple[str, ...]
    required_skills: tuple[str, ...]
    dependency_refs: tuple[str, ...]
    symbols: tuple[str, ...]
    identifiers: tuple[str, ...]
    anchors: tuple[str, ...]
    commands: tuple[str, ...]
    artifact_names: tuple[str, ...]
    recipe_id: str

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": CONCEPT_SCHEMA,
            "repository": self.repository,
            "issue_ref": self.issue_ref,
            "issue_number": self.issue_number,
            "issue_url": self.issue_url,
            "title": self.title,
            "ticket_type": self.ticket_type,
            "route": self.route,
            "requested_agent": self.requested_agent,
            "lane": self.lane,
            "target": self.target,
            "target_paths": list(self.target_paths),
            "current_state": self.current_state,
            "requested_outcome": self.requested_outcome,
            "proof_contract": self.proof_contract,
            "invariants": list(self.invariants),
            "non_goals": list(self.non_goals),
            "context_files": list(self.context_files),
            "required_skills": list(self.required_skills),
            "dependency_refs": list(self.dependency_refs),
            "symbols": list(self.symbols),
            "identifiers": list(self.identifiers),
            "anchors": list(self.anchors),
            "commands": list(self.commands),
            "artifact_names": list(self.artifact_names),
            "recipe_id": self.recipe_id,
        }


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(data: Any) -> str:
    text = data if isinstance(data, str) else _canonical_json(data)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _die(message: str) -> None:
    typer.echo(f"ERROR: {message}", err=True)
    raise typer.Exit(2)


def _normalize_repo(repo: Optional[str]) -> Optional[str]:
    if not repo or not Path(repo).is_dir():
        return repo
    proc = subprocess.run(
        ["git", "-C", repo, "remote", "get-url", "origin"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=10,
    )
    if proc.returncode != 0:
        _die(f"--repo {repo!r} is a directory without an origin remote")
    url = proc.stdout.strip()
    tail = url.split(":", 1)[-1] if url.startswith("git@") else url.rsplit(".com/", 1)[-1]
    parts = [part for part in tail.removesuffix(".git").split("/") if part]
    if len(parts) < 2:
        _die(f"cannot derive OWNER/REPO from origin URL {url!r}")
    return f"{parts[-2]}/{parts[-1]}"


def _split_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))


def _parse_marker(body: str) -> dict[str, str]:
    match = TICKET_MARKER_RE.search(body)
    if not match:
        return {}
    marker: dict[str, str] = {}
    for raw_line in match.group("body").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" not in line:
            _die(f"malformed ticket-skill marker line: {line!r}")
        key, value = line.split(":", 1)
        key = key.strip()
        if not re.fullmatch(r"[a-z_]+", key):
            _die(f"unsafe ticket-skill marker key: {key!r}")
        marker[key] = value.strip()
    return marker


def _sections(body: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(body))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[match.group("title").strip().lower()] = body[start:end].strip()
    return sections


def _plain_section(sections: dict[str, str], name: str) -> str:
    value = sections.get(name.lower(), "").strip()
    if value == "Not specified.":
        return ""
    return value


def _bullet_values(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            values.append(stripped[2:].strip().strip("`"))
    return tuple(dict.fromkeys(item for item in values if item))


def _target_path_values(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        bullet = stripped[2:].strip()
        backticked = re.findall(r"`([^`]+)`", bullet)
        if backticked:
            values.extend(item.strip() for item in backticked if item.strip())
        else:
            values.append(bullet.strip("`"))
    return tuple(dict.fromkeys(item for item in values if item))


def _blocked_by_values(text: str) -> tuple[str, ...]:
    refs: list[str] = []
    for line in text.splitlines():
        stripped = line.strip().removeprefix("-").strip()
        if stripped.startswith("blocked-by:"):
            refs.append(stripped.split(":", 1)[1].strip())
    return tuple(dict.fromkeys(refs))


def _extract_commands(text: str) -> tuple[str, ...]:
    candidates: list[str] = []
    for match in re.finditer(r"`([^`]+)`", text):
        snippet = match.group(1).strip()
        if any(token in snippet for token in ("run.sh", "pytest", "uv ", "gh ", "python", "npm ", "cargo ")):
            candidates.append(snippet)
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("./", "skills/", "uv ", "gh ", "pytest ", "npm ", "python ")):
            candidates.append(stripped)
    return tuple(dict.fromkeys(candidates))


def _extract_artifacts(text: str) -> tuple[str, ...]:
    names = re.findall(r"[\w./-]+\.(?:json|jsonl|md|txt|html|png|zip)", text)
    return tuple(dict.fromkeys(names))


def _validate_safe_values(label: str, values: tuple[str, ...]) -> None:
    for value in values:
        if value.startswith(("/", "~")) or ".." in Path(value).parts:
            _die(f"unsafe {label}: {value!r}")
        if label in {"target path", "context file"} and not SAFE_PATH_RE.fullmatch(value):
            _die(f"unsafe {label}: {value!r}")


def _derive_lane(route: str, labels: list[str]) -> str:
    for label in labels:
        if label.startswith("lane:"):
            return label.split(":", 1)[1]
    return {
        "frontend_code": "fe",
        "design_or_ux": "fe",
        "backend_python_or_skill_runtime": "be",
        "rust_or_binary": "be",
        "ops_or_scheduler": "ops",
        "documentation_or_report": "docs",
        "security_or_compliance": "sec",
    }.get(route, "")


def _concepts_from_issue(issue: IssueSource, *, recipe_id: str) -> TicketConcepts:
    marker = _parse_marker(issue.body)
    sections = _sections(issue.body)
    ticket_type = marker.get("type") or _plain_section(sections, "Type")
    route = marker.get("route") or _plain_section(sections, "Route") or "unknown"
    target = marker.get("target") or _plain_section(sections, "Target")
    agent = marker.get("agent") or _plain_section(sections, "Requested repair agent")
    context_files = _split_csv(marker.get("context_files")) or _bullet_values(
        _plain_section(sections, "Required repository context")
    )
    required_skills = _split_csv(marker.get("required_skills")) or _bullet_values(
        _plain_section(sections, "Required skills")
    )
    dependency_refs = _split_csv(marker.get("depends_on")) or _blocked_by_values(
        _plain_section(sections, "Dependencies")
    )
    target_path_bullets = _target_path_values(_plain_section(sections, "Target paths"))
    target_paths = target_path_bullets or ((target,) if target and SAFE_PATH_RE.fullmatch(target) else ())
    symbols = _split_csv(marker.get("memory_symbols"))
    identifiers = _split_csv(marker.get("memory_identifiers"))
    anchors = _split_csv(marker.get("memory_anchors"))
    marker_recipe = marker.get("memory_recipe")
    if marker_recipe:
        recipe_id = marker_recipe
    current_state = _plain_section(sections, "Current state")
    requested_outcome = _plain_section(sections, "Requested outcome")
    proof_contract = _plain_section(sections, "Required proof")
    non_goals = tuple(line.strip("- ").strip() for line in _plain_section(sections, "Non-goals").splitlines() if line.strip())
    detail_text = _plain_section(sections, "Ticket type details")
    invariants = tuple(
        line.split(":", 1)[1].strip()
        for line in detail_text.splitlines()
        if "invariant" in line.lower() and ":" in line
    )
    commands = _extract_commands(proof_contract)
    artifacts = _extract_artifacts(proof_contract)
    _validate_safe_values("target path", tuple(path for path in target_paths if path))
    _validate_safe_values("context file", tuple(path for path in context_files if path))
    if ticket_type in HUMAN_FIRST_TYPES and marker_recipe:
        _die("human-first tickets cannot become dispatchable by adding memory_recipe")
    if not ticket_type or not target or not proof_contract:
        _die("missing required ticket fields for memory plan: type, target, and required proof are mandatory")
    repo = issue.repo
    issue_ref = f"{repo}#{issue.number}" if repo and issue.number is not None else None
    return TicketConcepts(
        repository=repo,
        issue_ref=issue_ref,
        issue_number=issue.number,
        issue_url=issue.url,
        title=issue.title,
        ticket_type=ticket_type,
        route=route,
        requested_agent=agent,
        lane=_derive_lane(route, issue.labels),
        target=target,
        target_paths=tuple(target_paths),
        current_state=current_state,
        requested_outcome=requested_outcome,
        proof_contract=proof_contract,
        invariants=invariants,
        non_goals=non_goals,
        context_files=tuple(context_files),
        required_skills=tuple(required_skills),
        dependency_refs=tuple(dependency_refs),
        symbols=symbols,
        identifiers=identifiers,
        anchors=anchors,
        commands=commands,
        artifact_names=artifacts,
        recipe_id=recipe_id,
    )


def _read_live_issue(issue: int, repo: str) -> IssueSource:
    command = [
        "gh",
        "issue",
        "view",
        str(issue),
        "--repo",
        repo,
        "--json",
        "number,title,body,url,state,labels",
    ]
    proc = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    if proc.returncode != 0:
        _die(f"gh issue view failed: {proc.stderr.strip() or proc.stdout.strip()}")
    data = json.loads(proc.stdout)
    labels = [item.get("name", "") for item in data.get("labels", []) if item.get("name")]
    return IssueSource(
        number=int(data["number"]),
        title=str(data.get("title") or ""),
        body=str(data.get("body") or ""),
        repo=repo,
        url=str(data.get("url") or ""),
        state=str(data.get("state") or ""),
        labels=labels,
    )


def _read_body_file(path: Path, repo: str | None) -> IssueSource:
    if not path.is_file():
        _die(f"--body-file not found: {path}")
    return IssueSource(
        number=None,
        title=path.stem,
        body=path.read_text(encoding="utf-8"),
        repo=repo,
    )


def _load_recipes(path: Path) -> dict[str, Any]:
    if not path.is_file():
        _die(f"recipe registry not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != "ticket.memory_query_recipes.v1":
        _die("recipe registry has invalid schema")
    recipes = data.get("recipes")
    if not isinstance(recipes, dict):
        _die("recipe registry has no recipes map")
    return data


def _selector_values(concepts: TicketConcepts, names: list[str]) -> dict[str, Any]:
    raw = concepts.to_json()
    aliases = {
        "proof_contract": concepts.proof_contract,
        "commands": list(concepts.commands),
        "artifact_names": list(concepts.artifact_names),
        "anchors": list(concepts.anchors),
        "symbols": list(concepts.symbols),
        "identifiers": list(concepts.identifiers),
        "dependency_refs": list(concepts.dependency_refs),
        "target_paths": list(concepts.target_paths),
        "required_skills": list(concepts.required_skills),
        "invariants": list(concepts.invariants),
        "non_goals": list(concepts.non_goals),
        "goal_identity": concepts.requested_outcome,
    }
    return {name: aliases.get(name, raw.get(name)) for name in names}


def _step_enabled(step: dict[str, Any], concepts: TicketConcepts) -> tuple[bool, str]:
    step_id = str(step.get("id", ""))
    route = concepts.route
    if step_id == "exact-ticket-history":
        return bool(concepts.repository and concepts.issue_ref), "requires repository and issue_ref"
    if step_id in {"current-project-decisions", "current-target-state"}:
        return bool(concepts.target), "requires target"
    if step_id == "target-code-entry":
        return route in CODE_ROUTES, "requires code-changing route"
    if step_id == "related-prior-fixes":
        return bool(concepts.current_state or concepts.requested_outcome), "requires current state or outcome"
    if step_id == "bounded-impact":
        return bool(concepts.symbols), "requires at least one exact symbol"
    if step_id == "proof-history":
        return bool(concepts.proof_contract), "requires proof contract"
    if step_id == "cross-repo-analogy":
        return False, "exploratory late step; enabled only after local searches are insufficient"
    return True, "default"


def _compile_plan(issue: IssueSource, recipes_data: dict[str, Any], recipe_id: str) -> dict[str, Any]:
    concepts = _concepts_from_issue(issue, recipe_id=recipe_id)
    recipes = recipes_data["recipes"]
    if concepts.recipe_id not in recipes:
        _die(f"unknown memory recipe: {concepts.recipe_id}")
    recipe = recipes[concepts.recipe_id]
    compatible = set(recipe.get("route_compatibility") or [])
    if concepts.route not in compatible:
        _die(f"recipe {concepts.recipe_id!r} is incompatible with route {concepts.route!r}")
    if concepts.ticket_type in HUMAN_FIRST_TYPES:
        _die(f"{concepts.ticket_type} tickets are human-first and do not compile dispatchable Memory plans")

    effective_steps: list[dict[str, Any]] = []
    skipped_steps: list[dict[str, Any]] = []
    for index, raw_step in enumerate(recipe.get("steps", []), start=1):
        enabled, reason = _step_enabled(raw_step, concepts)
        selector_inputs = list(raw_step.get("selector_inputs") or [])
        compiled = {
            "id": raw_step["id"],
            "order": index,
            "class": raw_step["class"],
            "purpose": raw_step["purpose"],
            "memory_product": raw_step["memory_product"],
            "selectors": _selector_values(concepts, selector_inputs),
            "prerequisites": raw_step.get("prerequisites", []),
            "run_condition": raw_step.get("run_condition"),
            "enabled": enabled,
            "enabled_reason": reason,
            "budget": raw_step.get("budget", {}),
            "required_evidence_fields": raw_step.get("required_evidence_fields", []),
            "healthy_no_match": raw_step.get("healthy_no_match"),
            "stops_dispatch": bool(raw_step.get("stops_dispatch")),
        }
        (effective_steps if enabled else skipped_steps).append(compiled)

    concept_json = concepts.to_json()
    recipe_digest = _sha256(recipe)
    body_digest = _sha256(issue.body)
    plan_without_digest = {
        "schema": PLAN_SCHEMA,
        "compiled_at": "deterministic-preview",
        "issue_body_sha256": body_digest,
        "concepts": concept_json,
        "concepts_sha256": _sha256(concept_json),
        "recipe_id": concepts.recipe_id,
        "recipe_registry_path": str(RECIPES_PATH.relative_to(REPO_ROOT)),
        "recipe_digest": recipe_digest,
        "effective_steps": effective_steps,
        "skipped_steps": skipped_steps,
        "dependencies": list(concepts.dependency_refs),
        "diagnostic_commands": _diagnostic_commands(concepts),
        "github_mutation": False,
        "memory_retrieval_executed": False,
    }
    plan = dict(plan_without_digest)
    plan["plan_sha256"] = _sha256(plan_without_digest)
    plan["seam_validation"] = {
        "kind": "ticket.memory_query_plan.v1",
        "status": "PASS",
    }
    return plan


def _diagnostic_commands(concepts: TicketConcepts) -> list[str]:
    commands = []
    if concepts.issue_number and concepts.repository:
        commands.append(
            f"gh issue view {concepts.issue_number} --repo {concepts.repository} --json number,title,body,url,state,labels"
        )
    commands.append(
        f"skills/ticket/run.sh memory-plan {concepts.issue_number or '<issue>'}"
        + (f" --repo {concepts.repository}" if concepts.repository else "")
        + " --json"
    )
    for step in ("exact-ticket-history", "current-project-decisions", "current-target-state"):
        commands.append(f"skills/memory/run.sh recall --q '<{step} selector from plan>' --brief")
    return commands


def memory_plan_command(
    issue: Optional[int] = typer.Argument(None, help="GitHub issue number to compile from."),
    repo: Optional[str] = typer.Option(None, "--repo", "-R", help="OWNER/REPO or local checkout path."),
    body_file: Optional[Path] = typer.Option(None, "--body-file", help="Compile from an unfiled ticket body."),
    recipe: str = typer.Option(DEFAULT_RECIPE_ID, "--recipe", help="Memory recipe id to resolve."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Preview a deterministic Memory query plan for a ticket without retrieval."""
    normalized_repo = _normalize_repo(repo)
    if issue is None and body_file is None:
        _die("memory-plan requires ISSUE or --body-file")
    if issue is not None and not normalized_repo:
        _die("memory-plan ISSUE requires --repo OWNER/REPO")
    source = _read_live_issue(issue, normalized_repo) if issue is not None else _read_body_file(body_file, normalized_repo)
    recipes = _load_recipes(RECIPES_PATH)
    plan = _compile_plan(source, recipes, recipe)
    if as_json:
        typer.echo(json.dumps(plan, indent=2, sort_keys=True))
        return
    typer.echo(f"schema: {plan['schema']}")
    typer.echo(f"recipe: {plan['recipe_id']} {plan['recipe_digest']}")
    typer.echo(f"issue_body_sha256: {plan['issue_body_sha256']}")
    typer.echo(f"plan_sha256: {plan['plan_sha256']}")
    typer.echo("effective_steps:")
    for step in plan["effective_steps"]:
        typer.echo(f"  - {step['id']} ({step['class']}) -> {step['memory_product']}")


if __name__ == "__main__":
    memory_plan_command()
