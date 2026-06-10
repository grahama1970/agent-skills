"""review-plan: Validate task files before /orchestrate."""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import typer
from dotenv import load_dotenv
from loguru import logger

sys.path.append(str(Path(__file__).resolve().parents[1]))
from _shared.structured_plan import (  # type: ignore
    is_structured_plan,
    load_structured_plan,
    summarize_structured_plan,
    validate_structured_plan,
)

app = typer.Typer(help="Validate task files before orchestration")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")
CALLER_ROOT = Path(os.environ.get("REVIEW_PLAN_CALLER_CWD", os.getcwd())).resolve()
MANIFEST_PATH = PROJECT_ROOT / ".pi" / "skills-manifest.json"

# Execution-first: /review-plan is one preflight before /orchestrate, not a review loop.
REVIEW_PLAN_MAX_ROUNDS_DEFAULT = 1
REVIEW_PLAN_MAX_ROUNDS_HARD_CAP = 2  # only with --allow-extended-review
REVIEW_PLAN_MAX_WEBGPT_ORACLE_ITERATIONS = 1
# Substring that breaks $ask webgpt routing (plan diff review instead of bundle inline).
_ASK_WEBGPT_FORBIDDEN_SUBSTRINGS = ("/review-plan",)

# ─── Data Structures ─────────────────────────────────────────────────────────


@dataclass
class Finding:
    task: str
    check: str
    grade: str  # PASS, WARN, FAIL
    message: str
    line: int = 0
    suggestion: str = ""


@dataclass
class ReviewResult:
    file: str
    tasks: int = 0
    phases: int = 0
    findings: list[Finding] = field(default_factory=list)

    @property
    def pass_count(self) -> int:
        return sum(1 for f in self.findings if f.grade == "PASS")

    @property
    def warn_count(self) -> int:
        return sum(1 for f in self.findings if f.grade == "WARN")

    @property
    def fail_count(self) -> int:
        return sum(1 for f in self.findings if f.grade == "FAIL")


@dataclass
class GateResult:
    verdict: str
    reason: str
    review_result_json: str
    iterations: int
    next_iteration_plan: list[str] = field(default_factory=list)
    ask_artifacts: dict = field(default_factory=dict)


# ─── Parsers ─────────────────────────────────────────────────────────────────


def parse_task_file(content: str) -> list[dict]:
    """Extract tasks from a 0N_TASKS.md or plan file."""
    tasks = []
    current_task = None
    lines = content.split("\n")

    for i, line in enumerate(lines, 1):
        # Match task headers: ### Task N.N: Title or ## Task N: Title
        task_match = re.match(r"^#{2,3}\s+Task\s+(\d+(?:\.\d+)?):?\s*(.*)", line)
        if task_match:
            if current_task:
                tasks.append(current_task)
            current_task = {
                "id": task_match.group(1),
                "title": task_match.group(2).strip(),
                "line": i,
                "body": "",
                "dod": "",
                "gate": "",
            }
            continue

        # Match phase headers
        phase_match = re.match(r"^#{1,2}\s+Phase\s+(\d+(?:\.\d+)?)", line)
        if phase_match and current_task:
            tasks.append(current_task)
            current_task = None

        if current_task:
            current_task["body"] += line + "\n"

            # Extract Definition of Done
            if re.match(r"^[-*]\s+\*\*Definition of Done\*\*:", line, re.I):
                current_task["dod"] = line
            elif "definition of done" in line.lower() and ":" in line:
                current_task["dod"] = line

            # Extract Gate
            if re.match(r"^[-*]\s+\*\*Gate\*\*:", line, re.I):
                current_task["gate"] = line
            elif re.match(r"^[-*]\s+Gate:", line, re.I):
                current_task["gate"] = line

    if current_task:
        tasks.append(current_task)

    return tasks


def parse_structured_task_file(path: Path) -> tuple[list[dict], int]:
    """Extract tasks from structured YAML/JSON plan files."""
    data = load_structured_plan(path)
    summary = summarize_structured_plan(data)
    repo_root = str(data.get("repo_root") or PROJECT_ROOT)
    raw_tasks = [
        task for task in (data.get("tasks") or [])
        if isinstance(task, dict)
    ]
    raw_by_id: dict[str, dict] = {}
    duplicate_ids: set[str] = set()
    for task in raw_tasks:
        task_id = str(task.get("id") or "")
        if task_id in raw_by_id:
            duplicate_ids.add(task_id)
            continue
        raw_by_id[task_id] = task
    tasks: list[dict] = []
    for item in summary["tasks"]:
        raw_item = raw_by_id.get(str(item.get("id") or ""), {})
        dod = {
            "command": item.get("definition_of_done", {}).get("command", "")
            if isinstance(item.get("definition_of_done"), dict)
            else "",
            "assertion": item.get("definition_of_done", {}).get("assertion", "")
            if isinstance(item.get("definition_of_done"), dict)
            else "",
        }
        tests = item.get("tests") or []
        blind_tests = item.get("blind_tests") or []
        impl = item.get("implementation") or []
        body_parts = [
            f"Runner: {item.get('runner', '')}",
            f"Backend: {item.get('backend', '')}",
            f"Mode: {item.get('mode', '')}",
            f"Lane: {item.get('lane', '')}",
            f"Dependencies: {', '.join(item.get('dependencies', [])) or 'none'}",
            f"Command: {item.get('command', '')}",
            f"Prompt: {item.get('prompt', '')}",
        ]
        body_parts.extend(str(x) for x in impl)
        body_parts.extend(str(x) for x in tests)
        task = {
            "id": item.get("id", ""),
            "title": item.get("title", ""),
            "line": 1,
            "body": "\n".join(body_parts),
            "dod": json.dumps(dod),
            "definition_of_done": dod,
            "gate": item.get("gate", ""),
            "runner": item.get("runner", ""),
            "backend": item.get("backend", ""),
            "mode": item.get("mode", ""),
            "lane": item.get("lane", ""),
            "tests": tests,
            "blind_tests": blind_tests,
            "command": item.get("command", ""),
            "prompt": item.get("prompt", ""),
            "allowlist": item.get("allowlist") or [],
            "read_context": item.get("read_context") or [],
            "allowlist_optional": item.get("allowlist_optional", False),
            "implementation": impl,
            "skills": item.get("skills") or [],
            "depends_on": item.get("dependencies") or [],
            "repo_root": repo_root,
            "dirty_worktree_policy": raw_item.get("dirty_worktree_policy") or "",
            "apply_to_source": raw_item.get("apply_to_source", False),
            "commit_on_success": raw_item.get("commit_on_success", False),
            "rollback_on_failure": raw_item.get("rollback_on_failure", True),
            "service_under_test": raw_item.get("service_under_test"),
            "external_service": raw_item.get("external_service"),
            "hidden_tests": raw_item.get("hidden_tests"),
            "backend_racing": raw_item.get("backend_racing"),
            "planner": raw_item.get("planner"),
            "reviewer": raw_item.get("reviewer"),
            "tools": raw_item.get("tools"),
            "tool_surface": raw_item.get("tool_surface"),
            "cwd": raw_item.get("cwd"),
            "predecessor_patches": raw_item.get("predecessor_patches"),
            "memory": raw_item.get("memory"),
            "memory_query": raw_item.get("memory_query"),
            "memory_context": raw_item.get("memory_context"),
            "dogpile_context": raw_item.get("dogpile_context"),
            "web_context": raw_item.get("web_context"),
            "dod_scope": raw_item.get("dod_scope"),
            "requires_network": raw_item.get("requires_network"),
            "requires_live_server": raw_item.get("requires_live_server"),
            "browser_required": raw_item.get("browser_required"),
            "opaque_command_reviewed": raw_item.get("opaque_command_reviewed"),
            "duplicate_task_id": str(item.get("id") or "") in duplicate_ids,
        }
        tasks.append(task)
    return tasks, 0


def count_phases(content: str) -> int:
    return len(re.findall(r"^#{1,2}\s+Phase\s+\d+", content, re.MULTILINE))


# ─── Checkers ────────────────────────────────────────────────────────────────


def check_claims(task: dict, findings: list[Finding]):
    """Check 1: Verify file paths and references exist in the codebase."""
    body = task["body"]
    planned_outputs = {
        Path(str(path)).as_posix().lstrip("./")
        for path in (task.get("allowlist") or [])
        if str(path).strip()
    }

    # Extract file paths from backticks and markdown
    file_refs = re.findall(r"`([^`]*(?:\.(?:py|ts|js|rs|go|sh|json|toml|yaml|yml|md))\b[^`]*)`", body)
    # Also catch paths in **bold** or plain text
    file_refs += re.findall(r"(?:^|\s)((?:\.?/)?(?:[\w.-]+/)+[\w.-]+\.(?:py|ts|js|rs|go|sh|json|toml|yaml|yml|md))\b", body)
    unique_refs = list(dict.fromkeys(ref.strip().split(":")[0] for ref in file_refs if ref.strip()))

    for ref in unique_refs:
        normalized_ref = Path(ref).as_posix().lstrip("./")
        if normalized_ref in planned_outputs:
            continue
        if not _reference_exists(ref, task.get("repo_root")):
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="claim",
                grade="WARN",
                message=f"Referenced path `{ref}` not found in codebase",
                line=task["line"],
                suggestion=f"Verify path exists or update reference",
            ))


def check_skill_overlap(task: dict, manifest: dict | None, findings: list[Finding]):
    """Check 2: Detect tasks that reinvent existing skills.

    Two checks:
    1. FAIL if bespoke implementation overlaps an existing skill (>60% keyword match)
    2. WARN if code-runner task has empty skills field (missing skill discovery)
    """
    runner = task.get("runner", "")
    task_skills = task.get("skills", [])

    # Check 2a: code-runner tasks without skills field populated
    if runner == "code-runner" and not task_skills:
        findings.append(Finding(
            task=f"Task {task['id']}",
            check="overlap",
            grade="WARN",
            message="code-runner task has no `skills` field — /orchestrate can't compile skill context",
            line=task.get("line", 0),
            suggestion="Add `skills: [skill-name]` or run /recommend-skill-chain to auto-discover",
        ))

    # Check 2b: validate skill names exist in manifest
    if task_skills and manifest:
        known = {s.get("name", "") for s in manifest.get("skills", []) if isinstance(s, dict)}
        for skill_name in task_skills:
            if skill_name and skill_name not in known:
                findings.append(Finding(
                    task=f"Task {task['id']}",
                    check="overlap",
                    grade="WARN",
                    message=f"skills field references unknown skill `/{skill_name}`",
                    line=task.get("line", 0),
                    suggestion="Check skill name spelling or run `ls ~/.pi/skills/`",
                ))

    if not manifest:
        return

    body = task.get("body", "").lower()
    title = task.get("title", "").lower()

    # Only check tasks that are building something new
    build_signals = ["create", "build", "implement", "add", "write", "develop"]
    if not any(signal in title for signal in build_signals):
        return

    stopwords = {"the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "with", "is", "it", "this", "that"}
    skills = manifest.get("skills", [])
    for skill in skills:
        name = skill.get("name", "")
        desc = (skill.get("description", "") or "").lower()

        desc_words = set(desc.split()) - stopwords
        body_words = set(body.split()) - stopwords

        if len(desc_words) < 5:
            continue

        overlap = desc_words & body_words
        overlap_ratio = len(overlap) / len(desc_words) if desc_words else 0

        if overlap_ratio > 0.6:
            # FAIL: strong overlap — use the existing skill
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="overlap",
                grade="FAIL",
                message=f"Bespoke code overlaps existing skill `/{name}`: {skill.get('description', '')[:80]}",
                line=task.get("line", 0),
                suggestion=f"Use `/{name}` instead. Add `skills: [\"{name}\"]` to the task.",
            ))
        elif overlap_ratio > 0.4:
            # WARN: possible overlap
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="overlap",
                grade="WARN",
                message=f"Possible overlap with existing skill `/{name}`: {skill.get('description', '')[:80]}",
                line=task.get("line", 0),
                suggestion=f"Consider using `/{name}` instead of building from scratch",
            ))


def check_dod(task: dict, findings: list[Finding]):
    """Check 4: Audit Definition of Done quality."""
    dod = task.get("dod", "")

    if not dod:
        # Skip explore/research tasks
        body_lower = task["body"].lower()
        if any(kw in body_lower for kw in ["research", "explore", "investigate", "read", "understand"]):
            return
        findings.append(Finding(
            task=f"Task {task['id']}",
            check="dod",
            grade="WARN",
            message="No Definition of Done found",
            line=task["line"],
            suggestion="Add: `- **Definition of Done**: <test command> exits 0`",
        ))
        return

    # Check for vague DoD
    vague_patterns = [
        r"\bworks?\b",
        r"\bcorrect(ly)?\b",
        r"\bverif(y|ied)\b(?!.*\btest\b)",
        r"\bconfirm\b(?!.*\b(exit|pass|run)\b)",
        r"\bcheck\b(?!.*\b(exit|pass|run)\b)",
    ]
    for pattern in vague_patterns:
        if re.search(pattern, dod, re.I) and not re.search(r"(pytest|test|exit\s+0|run\.sh|sanity)", dod, re.I):
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="dod",
                grade="WARN",
                message=f"Definition of Done may be vague: `{dod.strip()[:80]}`",
                line=task["line"],
                suggestion="Use concrete assertions: `<command> exits 0` or `test_file.py::test_name passes`",
            ))
            break


def check_gate(task: dict, findings: list[Finding]):
    """Check 3: Verify gate definitions exist."""
    gate = task.get("gate", "")
    if not gate:
        body_lower = task["body"].lower()
        if any(kw in body_lower for kw in ["research", "explore", "reference only"]):
            return
        # Only warn if task has implementation content
        if any(kw in body_lower for kw in ["implement", "create", "build", "fix", "port", "install"]):
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="gate",
                grade="WARN",
                message="No Gate field found for implementation task",
                line=task["line"],
                suggestion="Add: `- **Gate**: <what must be true before this task is complete>`",
            ))


def check_skill_chains(task: dict, findings: list[Finding]):
    """Check 5: Validate /skill-name references in task body."""
    body = task["body"]

    # Extract slash skill references
    skill_refs = re.findall(r"/([a-z][a-z0-9-]{1,63})(?:\s|$|[.,;:!?)])", body)

    if not skill_refs:
        return

    # Check each ref against known skills
    manifest = load_manifest()
    if not manifest:
        return

    known_skills = {s.get("name", "") for s in manifest.get("skills", [])}

    for ref in skill_refs:
        if ref not in known_skills:
            # Skip common non-skill patterns
            if ref in {"home", "tmp", "dev", "etc", "usr", "var", "mnt", "opt", "model",
                       "run", "learn", "recall", "embed", "query", "list", "search",
                       "health", "status", "check", "scan", "test", "help",
                       "localhost", "null", "bin", "lib", "api", "v1", "solution",
                       "completions", "chaos", "creator", "commands", "config",
                       "python", "exploits", "battle", "patches", "arena"}:
                continue
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="chain",
                grade="WARN",
                message=f"Referenced skill `/{ref}` not found in manifest",
                line=task["line"],
                suggestion=f"Check skill name spelling or add to skills-manifest.json",
            ))


def check_sanity_scripts(task: dict, findings: list[Finding]):
    """Check: /plan requires sanity scripts for non-standard dependencies."""
    body = task["body"]

    # Look for dependency references that might need sanity scripts
    dep_patterns = [
        r"(?:install|add|require)\s+(\w[\w-]+)",  # install X, add X
        r"(?:import|from)\s+([\w.]+)",             # import X
    ]

    has_sanity_ref = bool(re.search(r"sanity", body, re.I))
    has_dependency_section = bool(re.search(r"(?:depend|sanity\s+script|crucial\s+depend)", body, re.I))

    # If task mentions non-trivial dependencies but no sanity reference
    non_std_deps = re.findall(r"(?:camelot|paddleocr|surya|demucs|transformers|opencv|torch|tensorflow)", body, re.I)
    if non_std_deps and not has_sanity_ref:
        findings.append(Finding(
            task=f"Task {task['id']}",
            check="sanity-script",
            grade="WARN",
            message=f"References non-standard deps ({', '.join(non_std_deps)}) but no sanity script mentioned",
            line=task["line"],
            suggestion="Add sanity script per /plan conventions: `sanity/<dep>.py` that verifies the API works in isolation",
        ))


def check_blockers_resolved(task: dict, findings: list[Finding]):
    """Check: /plan requires Questions/Blockers to be resolved before orchestration."""
    body = task["body"]

    # Look for unresolved blockers/questions
    blocker_patterns = [
        r"\?\s*$",                    # Questions ending with ?
        r"(?:BLOCKER|BLOCKED|TBD|TODO|FIXME|UNCLEAR)",
        r"(?:need(?:s)?\s+clarif)",   # "needs clarification"
        r"(?:ask\s+(?:the\s+)?human)",
    ]

    for pattern in blocker_patterns:
        matches = re.findall(pattern, body, re.I | re.M)
        if len(matches) > 2:  # Allow some inline questions
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="blockers",
                grade="WARN",
                message=f"Task contains unresolved blockers/questions ({len(matches)} matches)",
                line=task["line"],
                suggestion="Resolve all Questions/Blockers before /orchestrate per /plan conventions",
            ))
            break


def check_persona_routing(task: dict, findings: list[Finding]):
    """Check: /plan requires persona agent tasks to specify the persona."""
    body = task["body"]

    # Look for persona-related language without explicit agent assignment
    persona_signals = [
        r"(?<!/)\b(?:brandon|margaret|rob|nico|jennifer|lisa)\b",
        r"\b(?:persona|agent\s+should|have\s+someone)\b",
    ]

    has_agent_field = bool(re.search(r"(?:Agent|Persona)\s*:\s*\S+", body, re.I))

    for pattern in persona_signals:
        if re.search(pattern, body, re.I) and not has_agent_field:
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="persona-routing",
                grade="WARN",
                message="References a persona but no `Agent: <persona-name>` field found",
                line=task["line"],
                suggestion="Add `Agent: <persona-name>` per /plan conventions for persona tasks",
            ))
            break


def check_adversarial_test(task: dict, findings: list[Finding]):
    """Check 7: MANDATORY blind adversarial test enforcement. No exceptions.

    Adversarial = the implementing agent CANNOT see the test source code.
    The agent sees ONLY pass/fail output. This prevents the agent from gaming
    or faking success. /test-lab and sanity.sh are the primary blind harnesses.
    """
    body = task["body"]
    body_lower = body.lower()
    dod = task.get("dod", "")

    # Skip pure research/explore/reference tasks
    title_lower = task["title"].lower()
    if any(kw in title_lower for kw in ["verify", "check", "validate", "test"]):
        return  # Already a testing task
    if all(kw not in title_lower and kw not in body_lower[:200]
           for kw in ["implement", "create", "build", "fix", "port", "install", "add", "write", "configure"]):
        return  # Not an implementation task

    # Skip local runner tasks that execute pre-existing commands — agent isn't writing code
    runner = str(task.get("runner", "")).strip()
    if runner == "local" and str(task.get("command", "")).strip():
        return  # Deterministic shell command, not agent-authored code

    combined = dod + "\n" + body

    # Skip design tasks that follow existing patterns — TypeScript compilation is the gate
    # Pattern reuse = "same pattern as X", "reuse Y pattern", "follows existing pattern"
    # Design/UI tasks = TSX/component work, ux-lab routes, type definitions
    pattern_reuse_keywords = [
        r"same\s+pattern\s+as", r"reuse\s+.*pattern", r"follow.*pattern",
        r"pattern\s+from", r"follows\s+existing", r"existing\s+pattern",
        r"scillm.*gemini.*review", r"gemini.*vlm", r"vlm.*verification",
    ]
    design_keywords = [
        r"\.tsx", r"component", r"react", r"embry", r"gatechain", r"recallcard",
        r"ux-lab", r"types\.ts", r"routes\.ts", r"artifact", r"shared-chat",
    ]
    has_pattern_reuse = any(re.search(p, combined, re.I) for p in pattern_reuse_keywords)
    has_design_context = any(re.search(p, combined, re.I) for p in design_keywords)
    if has_pattern_reuse and has_design_context:
        return  # Pattern-following design task — TypeScript compilation is sufficient gate

    # Tier 1: Blind test patterns (agent cannot see test source)
    blind_patterns = [
        r"test-lab",                          # /test-lab harness
        r"verify-task",                       # test-lab verify-task
        r"sanity\.sh",                        # pre-existing sanity harness
        r"skills[_-]ci",                      # skills-ci scan (external validator)
    ]

    # code-runner tasks are inherently blind — /code-runner runs the DoD
    # command and the agent only sees pass/fail output
    if runner == "code-runner":
        return

    # Tier 2: Acceptable test patterns (runnable, but agent may have visibility)
    runnable_patterns = [
        r"pytest\s+\S+",                      # pytest test_file.py
        r"uv run pytest\s+\S+",              # uv run pytest tests/
        r"npm test",                          # npm test
        r"npx vitest\s+\S+",                 # npx vitest
        r"cargo test\s+\S+",                 # cargo test
        r"run\.sh\s+\S+.*(?:exits?\s+0)",    # run.sh command exits 0
        r"test_\w+\.py",                      # test file reference
        r"\.test\.(ts|js)",                   # JS/TS test file
        r"exits?\s+0",                        # explicit exit code check
        r"grep\s+-q\b",                       # quiet grep (returns exit code)
    ]

    has_blind = any(re.search(p, combined, re.I) for p in blind_patterns)
    has_runnable = any(re.search(p, combined, re.I) for p in runnable_patterns)

    if not has_blind and not has_runnable:
        findings.append(Finding(
            task=f"Task {task['id']}",
            check="adversarial-test",
            grade="FAIL",
            message="Implementation task has no adversarial test. Agent must not see test source — only pass/fail output.",
            line=task["line"],
            suggestion=(
                "Add blind test: `test-lab/run.sh verify-task <id> <target>` or `sanity.sh` exits 0. "
                "The implementing agent must NEVER see the test code. "
                "If using pytest, the test must be pre-existing or generated by /test-lab, not written by the same agent."
            ),
        ))
        return

    if has_runnable and not has_blind:
        # Has a test but it's not explicitly blind
        findings.append(Finding(
            task=f"Task {task['id']}",
            check="adversarial-test",
            grade="WARN",
            message="Has runnable test but no blind harness (test-lab/sanity.sh). Agent may be able to see and game the test.",
            line=task["line"],
            suggestion=(
                "Prefer blind testing via `/test-lab verify-task` or pre-existing `sanity.sh`. "
                "If the agent writes both code AND test, it can optimize for passing rather than correctness."
            ),
        ))

def check_tool_names(task: dict, findings: list[Finding]):
    """Check 6: Audit tool name references for Pi compatibility."""
    body = task["body"]

    # Claude Code tool names that differ in Pi
    tool_renames = {
        "Glob": "find",
        "Task": "subagent (via pi-subagents)",
        "WebSearch": "/dogpile",
        "WebFetch": "/fetcher or /dogpile",
        "AskUserQuestion": "/interview",
        "EnterPlanMode": "/plan command",
    }

    for cc_name, pi_name in tool_renames.items():
        # Look for capitalized tool name references (Claude Code style)
        if re.search(rf"\b{cc_name}\b", body):
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="tool-name",
                grade="WARN",
                message=f"References Claude Code tool `{cc_name}` — Pi equivalent is `{pi_name}`",
                line=task["line"],
                suggestion=f"Update to Pi tool name: `{pi_name}`",
            ))


SOURCE_MUTATION_VERB = re.compile(
    r"\b(create|write|edit|update|modify|extend|port|replace|wire|implement|add|refactor|patch|generate|materialize)\b",
    re.IGNORECASE,
)
SOURCE_FILE_REFERENCE = re.compile(
    r"(?:^|[\s`'\"])(?:\.?/)?(?:[\w.-]+/)+[\w.-]+\.(?:py|ts|tsx|js|jsx|json|md|mjs|sh|css|html|yaml|yml|toml|rs|go)\b",
    re.IGNORECASE,
)
SOURCE_DOD_MATERIALIZATION = re.compile(
    r"\b(test\s+-[fs]|rg\s+-n|grep\s+-q|npm\s+--prefix|npx\s+tsc|backend/sanity\.sh|require\(['\"]\.?/|node\s+-e)\b",
    re.IGNORECASE,
)


def _scillm_appears_to_mutate_source(task: dict, body: str, title: str) -> bool:
    """Return true when a direct scillm task asks for repo file materialization."""
    prompt = str(task.get("prompt") or "")
    command = str(task.get("command") or "")
    dod = task.get("definition_of_done") or {}
    dod_command = str(dod.get("command") or "") if isinstance(dod, dict) else ""
    combined = "\n".join([title, body, prompt, command, dod_command])

    if task.get("allowlist"):
        return True
    if SOURCE_MUTATION_VERB.search(combined) and SOURCE_FILE_REFERENCE.search(combined):
        return True
    if SOURCE_DOD_MATERIALIZATION.search(dod_command) and SOURCE_FILE_REFERENCE.search(combined):
        return True
    return False


def check_execution_routing(task: dict, findings: list[Finding]):
    """Validate runner/backend/mode selection for structured plans."""
    runner = str(task.get("runner", "")).strip()
    backend = str(task.get("backend", "")).strip()
    mode = str(task.get("mode", "")).strip()
    body = task.get("body", "").lower()
    title = task.get("title", "").lower()

    if not runner:
        return

    valid_runners = {"local", "scillm", "code-runner"}
    if runner == "subagent-service":
        # Deprecated: flag as ERROR so plans get updated
        findings.append(Finding(
            task=f"Task {task['id']}",
            check="routing",
            grade="FAIL",
            message="runner 'subagent-service' is deprecated and archived — update plan to use 'code-runner' or 'scillm'",
            line=task["line"],
            suggestion="Use 'code-runner' (writes files, iterative) or 'scillm' (one-shot, no files). /orchestrate auto-migrates at runtime but plans should be fixed.",
        ))
        return
    if runner not in valid_runners:
        findings.append(Finding(
            task=f"Task {task['id']}",
            check="routing",
            grade="FAIL",
            message=f"Unknown runner `{runner}`",
            line=task["line"],
            suggestion="Use one of: local, code-runner, scillm",
        ))
        return

    if task.get("duplicate_task_id"):
        findings.append(Finding(
            task=f"Task {task['id']}",
            check="structured-schema",
            grade="FAIL",
            message=f"duplicate structured task id `{task['id']}` makes raw field preservation ambiguous",
            line=task["line"],
            suggestion="Give every task a unique id before /review-plan or /orchestrate consumes the plan.",
        ))

    if runner == "scillm":
        if mode and mode != "one_shot":
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="routing",
                grade="FAIL",
                message="`scillm` tasks must use `mode: one_shot`",
                line=task["line"],
                suggestion="Set `mode: one_shot` or use `code-runner` for iterative work.",
            ))
        if _scillm_appears_to_mutate_source(task, body, title):
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="routing",
                grade="FAIL",
                message=(
                    "scillm runner cannot create or edit repository files; it only writes an "
                    "LLM response artifact."
                ),
                line=task["line"],
                suggestion=(
                    "Use `code-runner` with allowlist/read_context/DoD/blind_tests for source "
                    "mutation, or `local` for deterministic file operations. Keep direct "
                    "`scillm` for non-mutating review, classification, or model judgment."
                ),
            ))
        if not str(task.get("prompt", "")).strip() and not body.strip():
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="routing",
                grade="FAIL",
                message="scillm task has no prompt payload",
                line=task["line"],
                suggestion="Set `prompt:` explicitly or provide implementation text.",
            ))
    elif runner == "code-runner":
        # code-runner: Switchboard deterministic executor + /code-runner skill.
        # Requires backend (LLM for fix proposals) and implementation steps.
        forbidden_fields = sorted(
            field for field in CODE_RUNNER_FORBIDDEN_PLAN_FIELDS
            if _has_value(task.get(field))
        )
        if forbidden_fields:
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="code-runner-boundary",
                grade="FAIL",
                message=(
                    "code-runner task contains orchestration-only fields that must not be part of "
                    f"the runner contract: {', '.join(forbidden_fields)}"
                ),
                line=task["line"],
                suggestion=(
                    "Keep hidden/blind evaluation, backend racing, planners, reviewers, tools, "
                    "memory/dogpile capability calls, skill execution, and predecessor patch orchestration "
                    "outside /code-runner."
                ),
            ))
        if mode and mode not in {"iterative", "one_shot"}:
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="routing",
                grade="WARN",
                message=f"Unexpected code-runner mode `{mode}`",
                line=task["line"],
                suggestion="Use `iterative` (multi-round fix loop) or `one_shot`.",
            ))
        if not backend:
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="routing",
                grade="FAIL",
                message="code-runner task missing backend — defaults to codex",
                line=task["line"],
                suggestion="Set `backend: codex` for the GPT-5.5 High default, or explicitly justify another healthy backend.",
            ))
        impl = task.get("implementation") or []
        if not impl and not body.strip():
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="routing",
                grade="WARN",
                message="code-runner task has no implementation steps",
                line=task["line"],
                suggestion="Add `implementation:` list so /code-runner knows what to build.",
            ))
        # Cross-file dependency check: tasks with 3+ deps and no read_context have ~50% fail rate
        depends = task.get("depends_on") or []
        read_ctx = task.get("read_context") or []
        allowlist = task.get("allowlist") or []
        if not read_ctx:
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="routing",
                grade="FAIL",
                message="code-runner task has no read_context. Interface context must be separated from writable allowlist.",
                line=task["line"],
                suggestion="Add `read_context:` listing the dependency files the LLM should read for interface context. "
                           "Code-runner extracts interface maps (signatures + types) from these files.",
            ))
        # Allowlist check
        if not allowlist and not task.get("allowlist_optional"):
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="routing",
                grade="FAIL",
                message="code-runner task has no allowlist — LLM can write to any file",
                line=task["line"],
                suggestion="Add `allowlist:` with specific files to edit, or set `allowlist_optional: true`.",
            ))
        # Weak DoD check
        dod = task.get("definition_of_done") or {}
        dod_cmd = dod.get("command", "") if isinstance(dod, dict) else ""
        dod_assert = dod.get("assertion", "") if isinstance(dod, dict) else ""
        # code-runner overuse: no allowlist AND no DoD assertion = should be scillm
        if not allowlist and not dod_assert:
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="routing",
                grade="FAIL",
                message="code-runner without allowlist or DoD assertion — use scillm for simple edits",
                line=task["line"],
                suggestion="code-runner is expensive (worktree, git cycle, multi-round). "
                           "Use runner: scillm for mechanical edits, config changes, text generation.",
            ))
        if dod_cmd and not dod_assert and "assert" not in dod_cmd.lower() and "test" not in dod_cmd.lower():
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="routing",
                grade="FAIL",
                message="code-runner DoD has no assertion and doesn't run tests — LLM may game it",
                line=task["line"],
                suggestion="Add `assertion:` or include assert statements in the DoD command. "
                           "Consider adding `blind_tests:` for adversarial verification.",
            ))
        if dod_assert and not _is_machine_checkable_assertion(str(dod_assert)):
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="routing",
                grade="FAIL",
                message="code-runner DoD assertion is free-form prose, not machine-checkable",
                line=task["line"],
                suggestion="Use one of: `exit_code == 0`, `stdout_regex:...`, `stderr_regex:...`, `contains:...`, `json_path:...`, or `json_equals:...`.",
            ))
        # Blind tests enforcement — code-runner tasks MUST have blind_tests for adversarial verification.
        # `tests` can document public checks, but it is not the hidden /orchestrate information barrier.
        blind_tests = task.get("blind_tests") or []
        if not blind_tests:
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="blind_tests",
                grade="FAIL",
                message="code-runner task has no blind_tests — agent can game DoD without adversarial verification",
                line=task["line"],
                suggestion="Add `blind_tests:` with assertions the implementing agent cannot see. "
                           "Use `/test-lab verify-task` or `sanity.sh` for truly blind verification.",
            ))
        dirty_policy = str(task.get("dirty_worktree_policy") or "isolated_worktree").strip()
        unsafe_justification = str(task.get("unsafe_direct_justification") or "").strip()
        apply_to_source = bool(task.get("apply_to_source", False))
        commit_on_success = bool(task.get("commit_on_success", False))
        rollback_on_failure = bool(task.get("rollback_on_failure", True))
        if commit_on_success and not apply_to_source:
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="source_apply",
                grade="FAIL",
                message="commit_on_success requires apply_to_source",
                line=task["line"],
                suggestion="Set `apply_to_source: true` or remove `commit_on_success`.",
            ))
        if apply_to_source and not commit_on_success:
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="source_apply",
                grade="FAIL",
                message="complete-task mode must commit successful source changes",
                line=task["line"],
                suggestion="Set `commit_on_success: true` so the project agent can revert by commit.",
            ))
        if apply_to_source and not rollback_on_failure:
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="source_apply",
                grade="FAIL",
                message="complete-task mode must roll back failed source apply or source DoD",
                line=task["line"],
                suggestion="Set `rollback_on_failure: true`.",
            ))
        if dirty_policy not in CODE_RUNNER_SAFE_POLICIES and not unsafe_justification:
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="routing",
                grade="FAIL",
                message="code-runner task does not use isolated_worktree safe mode",
                line=task["line"],
                suggestion="Set `dirty_worktree_policy: isolated_worktree`. Unsafe direct modes require explicit `unsafe_direct_justification`.",
            ))
        # External/live API detection: code-runner edits a disposable worktree.
        # Live servers serve the source tree, so endpoint DoD/tests are impossible here.
        live_surface = _code_runner_live_surface(task, dod_cmd)
        if re.search(
            r'https?://|curl\s|wget\s|requests\.get|httpx\.\w+|urllib|'
            r'playwright|puppeteer|cypress|webdriver|chromium|selenium|storybook|test-runner|cdp|\be2e\b',
            live_surface,
            re.I,
        ):
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="routing",
                grade="FAIL",
                message="code-runner DoD or tests call a live URL/API/browser, but code-runner runs in an isolated worktree",
                line=task["line"],
                suggestion=(
                    "Use runner=scillm for the source-tree edit plus a separate runner=local task for curl/browser verification, "
                    "or replace the DoD with a file/process-local check that runs inside the code-runner worktree."
                ),
            ))
        if (
            OPAQUE_CODE_RUNNER_COMMAND.search(_code_runner_opaque_surface(task, dod_cmd))
            and not _declares_worktree_local_dod_contract(task)
        ):
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="routing",
                grade="FAIL",
                message="code-runner DoD or tests use opaque shell indirection that may hide live/browser/network checks",
                line=task["line"],
                suggestion=(
                    "Use an explicit file/process-local command, for example "
                    "`python -m pytest tests/test_file.py -q`, or route make/npm/scripts checks "
                    "to a separate runner=local verification task. If the opaque command has been audited, "
                    "declare `dod_scope: worktree_local`, `requires_network: false`, "
                    "`requires_live_server: false`, `browser_required: false`, and "
                    "`opaque_command_reviewed: true`."
                ),
            ))
    elif runner == "local":
        if backend:
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="routing",
                grade="WARN",
                message="local task has backend set; backend will be ignored",
                line=task["line"],
                suggestion="Remove `backend` for deterministic local tasks.",
            ))
        if not str(task.get("command", "")).strip():
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="routing",
                grade="FAIL",
                message="local task has no command",
                line=task["line"],
                suggestion="Set `command:` for local runner tasks.",
            ))


# ─── Preflight Checks (scillm backends, endpoints, tooling) ─────────────────


# Known scillm model names (from /scillm SKILL.md)
SCILLM_MODELS = {
    # Primary models
    "text", "text-research", "text-deepseek", "text-kimi", "text-qwen3", "text-qwen3-large",
    "text-gemini", "gemini-flash", "gemini-flash-oauth", "gemini-flash-high",
    "text-gemini-paid", "text-gemini-3", "text-gemini-3-paid",
    "claude-sonnet", "claude-sonnet-high", "claude-opus", "claude-opus-high", "claude-haiku",
    "gpt-5.5", "gpt-5.3-codex", "codex-vision", "oc-kimi", "oc-qwen", "oc-deepseek",
    "chutes-deepseek", "chutes-kimi", "chutes-qwen", "chutes-vlm", "text-glm",
    "vlm", "vlm-paid", "vlm-claude", "vlm-codex", "vlm-chutes",
    "local-text", "moonshot-text",
    # Pattern-based (auto-routed)
    # claude-*, gpt-*, codex-*, gemini-*, Org/Model, model:tag
}

# Legacy/deprecated backend names that need updating
LEGACY_BACKEND_NAMES = {
    "sonnet": "claude-sonnet",
    "opus": "claude-opus",
    "haiku": "claude-haiku",
    "codex": "gpt-5.5",
    "gemini": "gemini-flash-oauth",
    "claude": "claude-sonnet",
    "text-claude": "claude-sonnet",
    "text-claude-opus": "claude-opus",
    "text-claude-haiku": "claude-haiku",
    "text-gemini-oauth": "gemini-flash-oauth",
}


# code-runner accepts short backend names and translates them internally.
CODE_RUNNER_BACKENDS = {
    "codex",
    "claude",
    "text",
    "gemini",
    "deepseek",
    "test",
    "native-fake",
    "codex-exec",
    "claude-code",
    "gemini-cli",
    "opencode",
}
CODE_RUNNER_SAFE_POLICIES = {"isolated_worktree"}
CODE_RUNNER_FORBIDDEN_PLAN_FIELDS = {
    "backend_racing",
    "hidden_tests",
    "memory",
    "memory_query",
    "planner",
    "predecessor_patches",
    "reviewer",
    "tool_surface",
    "tools",
}
MACHINE_CHECKABLE_ASSERTION = re.compile(
    r"^\s*(exit_code\s*(==|!=)\s*\d+|stdout_regex:.+|stderr_regex:.+|contains:.+|json_path:.+|json_equals:.+)\s*$",
    re.IGNORECASE | re.DOTALL,
)
OPAQUE_CODE_RUNNER_COMMAND = re.compile(
    r"(^|\s)(npm|pnpm|yarn|bun)\s+(run|test|exec)\b|"
    r"(^|\s)make(\s|$)|"
    r"(^|\s)(bash|sh|python|python3|uv\s+run\s+python)\s+(scripts|tools)/|"
    r"(^|\s)(\./)?(scripts|tools)/[^\s;|&]+",
    re.IGNORECASE,
)


def _is_machine_checkable_assertion(assertion: str) -> bool:
    return bool(MACHINE_CHECKABLE_ASSERTION.match(assertion or ""))


def _has_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return bool(str(value).strip())


def _declares_worktree_local_dod_contract(task: dict) -> bool:
    return (
        str(task.get("dod_scope") or "").strip() == "worktree_local"
        and task.get("requires_network") is False
        and task.get("requires_live_server") is False
        and task.get("browser_required") is False
        and task.get("opaque_command_reviewed") is True
    )


def _code_runner_live_surface(task: dict, dod_cmd: str) -> str:
    parts = [dod_cmd]
    for item in task.get("tests") or []:
        if isinstance(item, dict):
            parts.append(str(item.get("command") or item))
        else:
            parts.append(str(item))
    return "\n".join(parts)


def _code_runner_opaque_surface(task: dict, dod_cmd: str) -> str:
    return _code_runner_live_surface(task, dod_cmd)


def check_scillm_backend(task: dict, findings: list[Finding]):
    """Check: Verify backend names exist in scillm's model registry."""
    backend = str(task.get("backend", "")).strip()
    if not backend:
        return

    runner = str(task.get("runner", "")).strip()
    if runner == "local":
        return  # local tasks don't use backends

    # code-runner handles its own backend translation — accept its native names
    if runner == "code-runner" and backend in CODE_RUNNER_BACKENDS:
        return  # Valid for code-runner

    # Check for legacy names (only applies to scillm/other runners)
    if backend in LEGACY_BACKEND_NAMES:
        findings.append(Finding(
            task=f"Task {task['id']}",
            check="scillm-backend",
            grade="FAIL",
            message=f"Backend `{backend}` is a legacy name — scillm won't recognize it",
            line=task.get("line", 0),
            suggestion=f"Use scillm model name: `{LEGACY_BACKEND_NAMES[backend]}`",
        ))
        return

    # Check if it's a known model or follows a known pattern
    if backend in SCILLM_MODELS:
        return  # Known model

    # Check pattern-based models
    if (backend.startswith("claude-") or
        backend.startswith("gpt-") or
        backend.startswith("codex-") or
        backend.startswith("gemini-") or
        "/" in backend or  # Org/Model pattern (Chutes)
        ":" in backend):   # model:tag pattern (Ollama)
        return  # Valid pattern

    findings.append(Finding(
        task=f"Task {task['id']}",
        check="scillm-backend",
        grade="WARN",
        message=f"Backend `{backend}` not in known scillm models — verify it exists",
        line=task.get("line", 0),
        suggestion=f"Run `curl -s -H 'Authorization: Bearer sk-dev-proxy-123' http://localhost:4001/v1/models` to check. "
                   f"Common models: text, text-claude, text-claude-opus, gpt-5.3-codex, text-gemini-oauth",
    ))


def check_endpoint_routes(task: dict, plan_data: dict | None, findings: list[Finding]):
    """Check: Verify endpoint references exist in the codebase."""
    body = task.get("body", "") + "\n" + task.get("prompt", "") + "\n" + str(task.get("command", ""))
    dod = task.get("definition_of_done", {})
    if isinstance(dod, dict):
        body += "\n" + dod.get("command", "")

    # Extract endpoint references like /create-evidence-case, /recall, etc.
    endpoint_refs = re.findall(r'["\']?/([a-z][a-z0-9-]{2,40})["\']?(?:\s|$|[,})\]])', body)

    if not endpoint_refs:
        return

    # Get repo_root from plan metadata
    repo_root = None
    if plan_data:
        repo_root = plan_data.get("repo_root")
    if not repo_root:
        repo_root = str(PROJECT_ROOT)

    repo_path = Path(repo_root)
    if not repo_path.exists():
        return

    # Skip common non-endpoint patterns
    skip_patterns = {"home", "tmp", "dev", "etc", "usr", "var", "mnt", "opt",
                     "run", "bin", "lib", "api", "v1", "health", "status"}

    for endpoint in endpoint_refs:
        if endpoint in skip_patterns:
            continue

        # Search for the route definition in the codebase
        route_pattern = f'@router.post.*"{endpoint}"|@router.get.*"{endpoint}"|@app.post.*"{endpoint}"'

        # Quick grep in src/
        src_path = repo_path / "src"
        if src_path.exists():
            result = subprocess.run(
                ["grep", "-r", "-l", f"/{endpoint}", str(src_path)],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                findings.append(Finding(
                    task=f"Task {task['id']}",
                    check="endpoint-route",
                    grade="WARN",
                    message=f"Endpoint `/{endpoint}` not found in src/ — verify route exists",
                    line=task.get("line", 0),
                    suggestion=f"Check the actual route name with `grep -r '@router' src/ | grep -i '{endpoint}'`",
                ))


def check_python_tooling(task: dict, plan_data: dict | None, findings: list[Finding]):
    """Check: Verify DoD commands use correct Python tooling for the project."""
    dod = task.get("definition_of_done", {})
    dod_cmd = dod.get("command", "") if isinstance(dod, dict) else ""
    task_cmd = str(task.get("command", ""))
    combined = dod_cmd + "\n" + task_cmd

    if not combined.strip():
        return

    # Get repo_root to check for pyproject.toml
    repo_root = None
    if plan_data:
        repo_root = plan_data.get("repo_root")
    if not repo_root:
        repo_root = str(PROJECT_ROOT)

    repo_path = Path(repo_root)
    has_pyproject = (repo_path / "pyproject.toml").exists()
    has_uv_lock = (repo_path / "uv.lock").exists()

    # If project uses uv (has pyproject.toml or uv.lock), check for bare python3 calls
    if has_pyproject or has_uv_lock:
        # Look for python3 -c "from module..." without uv run
        bare_python_import = re.search(
            r'(?<!uv run )python3?\s+-c\s+["\'](?:from|import)\s+\w+',
            combined
        )
        if bare_python_import:
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="python-tooling",
                grade="WARN",
                message="DoD uses `python3 -c` but project has pyproject.toml — may fail to import packages",
                line=task.get("line", 0),
                suggestion="Use `uv run python3 -c` to ensure packages are available, or set PYTHONPATH explicitly",
            ))

        # Check for bare pytest without uv run
        bare_pytest = re.search(r'(?<!uv run )pytest\s+', combined)
        if bare_pytest:
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="python-tooling",
                grade="WARN",
                message="DoD uses bare `pytest` but project has pyproject.toml — may not find installed packages",
                line=task.get("line", 0),
                suggestion="Use `uv run pytest` to ensure the project's virtual environment is activated",
            ))


# ─── Manifest Loader ─────────────────────────────────────────────────────────


_manifest_cache: dict | None = None
_file_index_cache: set[str] | None = None
_basename_index_cache: set[str] | None = None


def load_manifest() -> dict | None:
    global _manifest_cache
    if _manifest_cache is not None:
        return _manifest_cache
    if MANIFEST_PATH.exists():
        try:
            _manifest_cache = json.loads(MANIFEST_PATH.read_text())
            return _manifest_cache
        except Exception:
            pass
    return None


def _build_file_indexes() -> tuple[set[str], set[str]]:
    """Build exact-path and basename indexes for fast claim checks."""
    global _file_index_cache, _basename_index_cache
    if _file_index_cache is not None and _basename_index_cache is not None:
        return _file_index_cache, _basename_index_cache

    exact_paths: set[str] = set()
    basenames: set[str] = set()

    try:
        result = subprocess.run(
            ["rg", "--files", str(PROJECT_ROOT)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                rel = os.path.relpath(line, PROJECT_ROOT)
                rel_posix = Path(rel).as_posix()
                exact_paths.add(rel_posix)
                basenames.add(Path(rel_posix).name)
        else:
            raise RuntimeError("rg --files failed")
    except Exception:
        skip_dirs = {
            ".git",
            "node_modules",
            ".venv",
            "__pycache__",
            ".mypy_cache",
            ".pytest_cache",
        }
        for current_root, dirnames, filenames in os.walk(PROJECT_ROOT):
            current_path = Path(current_root)
            rel_parts = current_path.relative_to(PROJECT_ROOT).parts if current_path != PROJECT_ROOT else ()
            dirnames[:] = [
                dirname
                for dirname in dirnames
                if dirname not in skip_dirs and not (rel_parts == (".pi",) and dirname == ".worktrees")
            ]
            for filename in filenames:
                rel_path = (current_path / filename).relative_to(PROJECT_ROOT).as_posix()
                exact_paths.add(rel_path)
                basenames.add(filename)

    _file_index_cache = exact_paths
    _basename_index_cache = basenames
    return exact_paths, basenames


def _reference_exists(ref: str, repo_root: str | None = None) -> bool:
    """Return True if the referenced path already exists in the repo."""
    if ref.startswith("~"):
        return True

    if ref.startswith("/") and not ref.startswith("/."):
        return Path(ref).exists()

    root = Path(repo_root) if repo_root else PROJECT_ROOT
    normalized = Path(ref).as_posix().lstrip("./")
    if (root / normalized).exists():
        return True

    exact_paths, basenames = _build_file_indexes()
    return normalized in exact_paths or Path(normalized).name in basenames


# ─── Check 9 & 10: Design Board + PNG Evidence (see ux_checks.py) ────────────
from ux_checks import check_design_board, check_png_evidence, check_lab_subagent


# ─── Commands ────────────────────────────────────────────────────────────────


def run_review_checks(task_file: str) -> ReviewResult:
    """Full deterministic review of a task file."""
    path = Path(task_file)
    if not path.exists():
        path = CALLER_ROOT / task_file
    if not path.exists():
        # Try relative to project root
        path = PROJECT_ROOT / task_file
    if not path.exists():
        logger.error(f"Task file not found: {task_file}")
        raise typer.Exit(1)

    content = path.read_text()
    structured_result = None
    plan_data = None
    if is_structured_plan(path):
        plan_data = load_structured_plan(path)
        structured_result = validate_structured_plan(plan_data)
        tasks, phases = parse_structured_task_file(path)
    else:
        tasks = parse_task_file(content)
        phases = count_phases(content)
    manifest = load_manifest()

    result = ReviewResult(file=str(path), tasks=len(tasks), phases=phases)

    for task in tasks:
        check_claims(task, result.findings)
        check_skill_overlap(task, manifest, result.findings)
        check_dod(task, result.findings)
        check_gate(task, result.findings)
        check_adversarial_test(task, result.findings)
        check_skill_chains(task, result.findings)
        check_tool_names(task, result.findings)
        check_sanity_scripts(task, result.findings)
        check_blockers_resolved(task, result.findings)
        check_persona_routing(task, result.findings)
        check_execution_routing(task, result.findings)
        check_design_board(task, result.findings)
        check_png_evidence(task, result.findings)
        check_lab_subagent(task, result.findings)
        # Preflight checks for scillm, endpoints, and tooling
        check_scillm_backend(task, result.findings)
        check_endpoint_routes(task, plan_data, result.findings)
        check_python_tooling(task, plan_data, result.findings)

    if structured_result:
        for issue in structured_result["issues"]:
            result.findings.append(Finding(
                task="Plan",
                check="structured-schema",
                grade="FAIL",
                message=issue,
                line=1,
            ))
        for warning in structured_result["warnings"]:
            result.findings.append(Finding(
                task="Plan",
                check="structured-schema",
                grade="WARN",
                message=warning,
                line=1,
            ))

    return result


def review_result_to_dict(result: ReviewResult, suggest_fixes: bool = False) -> dict:
    return {
        "file": result.file,
        "tasks": result.tasks,
        "phases": result.phases,
        "pass": result.pass_count,
        "warn": result.warn_count,
        "fail": result.fail_count,
        "findings": [
            {
                "task": f.task,
                "check": f.check,
                "grade": f.grade,
                "message": f.message,
                "line": f.line,
                **({"suggestion": f.suggestion} if suggest_fixes and f.suggestion else {}),
            }
            for f in result.findings
        ],
    }


_ASK_GATE_PASS_VERDICTS = frozenset(
    {"SAFE", "PASS", "SAFE_WITH_CONDITIONS", "READY_FOR_PLAN_ITERATE"}
)
_ASK_GATE_BLOCK_VERDICTS = frozenset(
    {"NOT_SAFE", "NEEDS_CHANGES", "BLOCKED", "INSUFFICIENT_EVIDENCE"}
)
_REVIEW_BUNDLE_REQUIRED_SECTIONS = (
    "## Review request",
    "## This round acceptance",
    "## Local gates",
)
_REVIEW_BUNDLE_MAX_BYTES = 2 * 1024 * 1024  # 2 MiB, matches $ask inline cap


def validate_review_evidence_bundle(bundle_path: Path) -> list[str]:
    """Return human-readable issues for a markdown review bundle (empty if ok)."""
    issues: list[str] = []
    if not bundle_path.exists():
        return [f"review bundle not found: {bundle_path}"]
    if bundle_path.suffix.lower() in {".zip", ".tar", ".gz", ".tgz", ".7z"}:
        return ["use --ask-attach-file for zip archives, not --ask-review-bundle"]
    try:
        size = bundle_path.stat().st_size
    except OSError as exc:
        return [f"cannot stat review bundle: {exc}"]
    if size > _REVIEW_BUNDLE_MAX_BYTES:
        issues.append(
            f"review bundle is {size} bytes (max {_REVIEW_BUNDLE_MAX_BYTES} for $ask inline attach)"
        )
    try:
        body = bundle_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"cannot read review bundle: {exc}"]
    lowered = body.lower()
    for heading in _REVIEW_BUNDLE_REQUIRED_SECTIONS:
        if heading.lower() not in lowered:
            issues.append(f"missing required section: {heading}")
    return issues


def validate_review_attach_zip(zip_path: Path, *, max_files: int = 5) -> list[str]:
    """Return issues for a WebGPT zip attach bundle (empty if ok)."""
    import zipfile

    issues: list[str] = []
    if not zip_path.exists():
        return [f"attach zip not found: {zip_path}"]
    if zip_path.suffix.lower() != ".zip":
        issues.append("ask-attach-file must be a .zip path for $ask webgpt")
    try:
        with zipfile.ZipFile(zip_path) as zf:
            members = [i.filename for i in zf.infolist() if not i.is_dir()]
    except Exception as exc:
        return [f"cannot read zip: {exc}"]
    if not members:
        issues.append("zip archive is empty")
    elif len(members) > max_files:
        issues.append(f"zip has {len(members)} files (maximum {max_files} for $ask webgpt)")
    names = {Path(m).name.lower() for m in members}
    if not any(n.endswith(".md") for n in names):
        issues.append("zip should include REQUEST.md, PLAN.md, REVIEW.md, or review.md markdown file")
    return issues





def _import_webgpt_runtime():
    ask_src = Path(__file__).resolve().parent.parent / "ask" / "src"
    if str(ask_src) not in sys.path:
        sys.path.insert(0, str(ask_src))
    from ask.webgpt_runtime import WebgptBackendError, call_webgpt  # type: ignore

    return call_webgpt, WebgptBackendError


def _assert_webgpt_safe_text(text: str, *, label: str) -> None:
    lowered = text.lower()
    for forbidden in _ASK_WEBGPT_FORBIDDEN_SUBSTRINGS:
        if forbidden.lower() in lowered:
            raise ValueError(f"{label} must not contain {forbidden!r} (breaks $ask routing)")


def _build_webgpt_readiness_prompt(
    *,
    attach_file: str,
    review_bundle: Path | None,
    target: Path,
) -> str:
    """Prompt for external tech-lead readiness (never use /review-plan in text)."""
    intro = (
        "You are the external tech lead reviewing orchestration plan readiness before "
        "task execution. Return ONLY:\n"
        "VERDICT: PASS | NEEDS_CHANGES | BLOCKED | INSUFFICIENT_EVIDENCE\n"
        "then concrete blockers (if any). Do not implement fixes or run shell commands.\n\n"
    )
    if attach_file:
        prompt = intro + f"Evidence is in the attached zip ({Path(attach_file).name})."
    else:
        chunks = [intro]
        if review_bundle is not None:
            chunks.append("## Evidence bundle\n\n")
            chunks.append(review_bundle.read_text(encoding="utf-8"))
        chunks.append(f"\n## Plan target\n\n{target.resolve()}\n")
        prompt = "".join(chunks)
    _assert_webgpt_safe_text(prompt, label="webgpt readiness prompt")
    return prompt


def _recommended_next_step(verdict: str, result: ReviewResult) -> str:
    if verdict == "PASS":
        return "Run /orchestrate on this plan file now."
    if result.fail_count > 0 or result.warn_count > 0:
        return (
            "Fix deterministic findings once, then re-run /review-plan without --ask-gate; "
            "do not loop external review."
        )
    return (
        "Address external gate blockers once, then run /orchestrate or /plan-iterate; "
        "avoid re-running /review-plan with --ask-gate in a loop."
    )


def _apply_spiral_guards(
    *,
    max_rounds: int,
    allow_extended_review: bool,
    ask_gate: bool,
    oracle_iterations: int,
    ask_gate_backend: str,
) -> tuple[int, int, list[str]]:
    """Cap review-plan iteration knobs so plans lead to execution, not review spirals."""
    notes: list[str] = []
    effective_max_rounds = max_rounds
    if max_rounds > REVIEW_PLAN_MAX_ROUNDS_DEFAULT and not allow_extended_review:
        notes.append(
            f"--max-rounds {max_rounds} capped to {REVIEW_PLAN_MAX_ROUNDS_DEFAULT} "
            "(execution-first; pass --allow-extended-review only for one extra human preflight)"
        )
        effective_max_rounds = REVIEW_PLAN_MAX_ROUNDS_DEFAULT
    if allow_extended_review and max_rounds > REVIEW_PLAN_MAX_ROUNDS_HARD_CAP:
        raise ValueError(
            f"--max-rounds {max_rounds} exceeds hard cap {REVIEW_PLAN_MAX_ROUNDS_HARD_CAP} "
            "even with --allow-extended-review"
        )
    effective_oracle = oracle_iterations
    if ask_gate and ask_gate_backend.strip().lower() == "webgpt":
        if oracle_iterations > REVIEW_PLAN_MAX_WEBGPT_ORACLE_ITERATIONS:
            notes.append(
                f"--oracle-iterations {oracle_iterations} capped to "
                f"{REVIEW_PLAN_MAX_WEBGPT_ORACLE_ITERATIONS} for webgpt preflight"
            )
            effective_oracle = REVIEW_PLAN_MAX_WEBGPT_ORACLE_ITERATIONS
    return effective_max_rounds, effective_oracle, notes



def _gate_verdict(result: ReviewResult, ask_artifacts: dict | None = None) -> tuple[str, str]:
    """Map deterministic and ask-gate evidence to a controller verdict."""
    if result.fail_count > 0 or result.warn_count > 0:
        return "NEEDS_CHANGES", "deterministic_review_has_warn_or_fail_findings"
    if ask_artifacts:
        status = ask_artifacts.get("status")
        verdict = str(ask_artifacts.get("verdict") or "").upper()
        if status == "skipped":
            return "INSUFFICIENT_EVIDENCE", str(ask_artifacts.get("reason") or "ask_gate_skipped")
        if status != "passed":
            return "INSUFFICIENT_EVIDENCE", "ask_gate_did_not_pass"
        if verdict in _ASK_GATE_BLOCK_VERDICTS:
            return "NEEDS_CHANGES", "ask_gate_returned_blocking_verdict"
        if verdict and verdict not in _ASK_GATE_PASS_VERDICTS:
            return "INSUFFICIENT_EVIDENCE", "ask_gate_verdict_unparseable"
    return "PASS", "no_warn_fail_or_blocking_ask_gate_findings"


def _next_iteration_plan(
    result: ReviewResult,
    *,
    verdict: str = "",
    ask_artifacts: dict | None = None,
) -> list[str]:
    items: list[str] = []
    for finding in result.findings:
        if finding.grade not in {"FAIL", "WARN"}:
            continue
        suffix = f" Suggestion: {finding.suggestion}" if finding.suggestion else ""
        items.append(f"{finding.task} [{finding.grade} {finding.check}]: {finding.message}.{suffix}")
    if ask_artifacts and ask_artifacts.get("status") == "blocked" and ask_artifacts.get("verdict"):
        items.append(
            f"External gate ({ask_artifacts.get('backend')}): {ask_artifacts.get('verdict')} — "
            "fix blockers in plan or evidence bundle once."
        )
    step = _recommended_next_step(verdict or "NEEDS_CHANGES", result)
    if verdict == "PASS":
        items.insert(0, step)
    else:
        items.append(step)
        items.append(
            "Anti-spiral: do not auto-re-run /review-plan with --ask-gate; "
            "use /orchestrate or /plan-iterate for implementation work."
        )
    return items


def _extract_ask_verdict(review_json_path: Path | None) -> str | None:
    if review_json_path is None or not review_json_path.exists():
        return None
    try:
        data = json.loads(review_json_path.read_text())
    except Exception:
        return None
    queue: list[object] = [data]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            for key in ("verdict", "status", "decision"):
                value = current.get(key)
                if isinstance(value, str):
                    normalized = value.strip().upper()
                    if normalized:
                        return normalized
            queue.extend(current.values())
        elif isinstance(current, list):
            queue.extend(current)
    return None


def _extract_verdict_from_text(text: str) -> str | None:
    if not text.strip():
        return None
    match = re.search(
        r"VERDICT:\s*([A-Z][A-Z0-9_]+)",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).upper()
    ask_src = Path(__file__).resolve().parent.parent / "ask" / "src"
    if str(ask_src) not in sys.path:
        sys.path.insert(0, str(ask_src))
    try:
        from ask.webgpt_review import extract_verdict  # type: ignore

        verdict, _data = extract_verdict(text)
        if verdict:
            return str(verdict).upper()
    except Exception:
        pass
    return None


def _ask_runtime_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "ask"


def _collect_ask_run_artifacts(ask_root: Path, ask_id: str) -> dict:
    run_dir = ask_root / ".ask_artifacts" / "runs" / ask_id
    status_path = run_dir / f"{ask_id}.status.json"
    request_path = run_dir / f"{ask_id}.request.json"
    events_path = run_dir / f"{ask_id}.events.jsonl"
    review_md_path: Path | None = None
    review_json_path: Path | None = None
    status_data: dict = {}
    answer_text = ""
    if status_path.exists():
        try:
            status_data = json.loads(status_path.read_text())
        except Exception:
            status_data = {}
        result = status_data.get("result")
        if isinstance(result, dict):
            answer_text = str(result.get("answer") or "").strip()
        artifacts = status_data.get("artifacts", {})
        if isinstance(artifacts, dict):
            for key in ("review_md", "markdown"):
                value = artifacts.get(key)
                if isinstance(value, str):
                    review_md_path = Path(value)
                    if not review_md_path.is_absolute():
                        review_md_path = ask_root / review_md_path
                    break
            for key in ("review_json", "json"):
                value = artifacts.get(key)
                if isinstance(value, str):
                    review_json_path = Path(value)
                    if not review_json_path.is_absolute():
                        review_json_path = ask_root / review_json_path
                    break
    if review_json_path is None:
        candidates = sorted((ask_root / ".ask_artifacts" / "deep-review").glob("*/review.json"))
        review_json_path = candidates[-1] if candidates else None
    if review_md_path is None and review_json_path is not None:
        review_md_path = review_json_path.with_name("review.md")
    return {
        "run_dir": str(run_dir),
        "status_path": status_path,
        "request_path": request_path,
        "events_path": events_path,
        "status_data": status_data,
        "review_md_path": review_md_path,
        "review_json_path": review_json_path,
        "answer_text": answer_text,
    }


def _finalize_ask_gate_result(
    *,
    proc: subprocess.CompletedProcess[str],
    ask_id: str,
    command: list[str],
    backend: str,
    collected: dict,
) -> dict:
    status_path = collected["status_path"]
    request_path = collected["request_path"]
    events_path = collected["events_path"]
    review_md_path = collected["review_md_path"]
    review_json_path = collected["review_json_path"]
    verdict = _extract_ask_verdict(review_json_path)
    if not verdict:
        verdict = _extract_verdict_from_text(collected["answer_text"])
    if not verdict:
        verdict = _extract_verdict_from_text(proc.stdout)
    passed = proc.returncode == 0 and verdict in _ASK_GATE_PASS_VERDICTS
    return {
        "status": "passed" if passed else "blocked",
        "backend": backend,
        "returncode": proc.returncode,
        "ask_id": ask_id,
        "command": command,
        "request_json": str(request_path),
        "status_json": str(status_path),
        "events_jsonl": str(events_path),
        "run_dir": collected["run_dir"],
        "review_md": str(review_md_path) if review_md_path else None,
        "review_json": str(review_json_path) if review_json_path else None,
        "verdict": verdict,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }


def _run_ask_gate_webgpt(
    *,
    target: Path,
    review_bundle: Path | None,
    attach_file: str,
    ask_id: str,
    ask_timeout: int,
    webgpt_tab_id: str,
    webgpt_project: str,
    oracle_iterations: int,
    run_output_root: str,
    webgpt_allow_foreground: bool = False,
) -> dict:
    if not webgpt_tab_id and not webgpt_project:
        return {
            "status": "blocked",
            "backend": "webgpt",
            "reason": "webgpt_tab_or_project_required",
        }
    try:
        call_webgpt, WebgptBackendError = _import_webgpt_runtime()
    except Exception as exc:
        return {
            "status": "blocked",
            "backend": "webgpt",
            "reason": "webgpt_runtime_import_failed",
            "error": str(exc),
        }

    artifact_dir = (
        Path(run_output_root) / ask_id
        if run_output_root
        else Path(tempfile.mkdtemp(prefix="review-plan-webgpt-"))
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)

    old_fg = os.environ.get("ASK_WEBGPT_ALLOW_FOREGROUND")
    if webgpt_allow_foreground:
        os.environ["ASK_WEBGPT_ALLOW_FOREGROUND"] = "1"
    try:
        prompt = _build_webgpt_readiness_prompt(
            attach_file=attach_file,
            review_bundle=review_bundle,
            target=target,
        )
        wg = call_webgpt(
            prompt,
            tab_id=webgpt_tab_id,
            project=webgpt_project,
            attach_file=attach_file or "",
            timeout=float(ask_timeout),
            artifact_dir=artifact_dir,
            no_activate=True,
        )
    except WebgptBackendError as exc:
        return {
            "status": "blocked",
            "backend": "webgpt",
            "reason": "webgpt_call_failed",
            "error": str(exc),
            "artifact_dir": str(artifact_dir),
            "ask_id": ask_id,
        }
    except ValueError as exc:
        return {
            "status": "blocked",
            "backend": "webgpt",
            "reason": "webgpt_prompt_invalid",
            "error": str(exc),
            "ask_id": ask_id,
        }
    finally:
        if webgpt_allow_foreground:
            if old_fg is None:
                os.environ.pop("ASK_WEBGPT_ALLOW_FOREGROUND", None)
            else:
                os.environ["ASK_WEBGPT_ALLOW_FOREGROUND"] = old_fg

    response_text = wg.response
    verdict = _extract_verdict_from_text(response_text)
    passed = verdict in _ASK_GATE_PASS_VERDICTS
    response_path = artifact_dir / "02_response.md"
    result = {
        "status": "passed" if passed else "blocked",
        "backend": "webgpt",
        "returncode": 0 if passed else 1,
        "ask_id": ask_id,
        "command": ["call_webgpt", "in_process"],
        "artifact_dir": str(artifact_dir),
        "response_md": str(response_path),
        "review_md": str(response_path),
        "verdict": verdict,
        "stdout_tail": response_text[-4000:],
        "stderr_tail": "",
        "oracle_iterations": max(1, min(oracle_iterations, REVIEW_PLAN_MAX_WEBGPT_ORACLE_ITERATIONS)),
    }
    if review_bundle is not None:
        result["review_bundle"] = str(review_bundle.resolve())
    result["plan_target"] = str(target.resolve())
    if attach_file:
        result["attach_file"] = attach_file
    return result


def _run_ask_gate(
    *,
    backend: str,
    target: Path,
    review_bundle: Path | None,
    attach_file: str,
    ask_id: str,
    ask_model: str,
    ask_reasoning: str,
    ask_timeout: int,
    focus: str,
    webgpt_tab_id: str,
    webgpt_project: str,
    oracle_iterations: int,
    run_output_root: str,
    webgpt_allow_foreground: bool = False,
) -> dict:
    normalized = backend.strip().lower()
    if normalized == "webgpt":
        return _run_ask_gate_webgpt(
            target=target,
            review_bundle=review_bundle,
            attach_file=attach_file,
            ask_id=ask_id,
            ask_timeout=ask_timeout,
            webgpt_tab_id=webgpt_tab_id,
            webgpt_project=webgpt_project,
            oracle_iterations=oracle_iterations,
            run_output_root=run_output_root,
            webgpt_allow_foreground=webgpt_allow_foreground,
        )
    if normalized not in {"", "scillm", "deep-review"}:
        return {
            "status": "blocked",
            "backend": normalized,
            "reason": f"unsupported ask gate backend: {backend}",
        }
    return _run_ask_deep_review(
        target=target,
        ask_id=ask_id,
        ask_model=ask_model,
        ask_reasoning=ask_reasoning,
        ask_timeout=ask_timeout,
        focus=focus,
        run_output_root=run_output_root,
    )


def _run_ask_deep_review(
    target: Path,
    ask_id: str,
    ask_model: str,
    ask_reasoning: str,
    ask_timeout: int,
    focus: str,
    run_output_root: str = "",
) -> dict:
    ask_root = _ask_runtime_dir()
    ask_run = ask_root / "run.sh"
    if not ask_run.exists():
        return {
            "status": "blocked",
            "reason": "ask runtime not found",
            "ask_run": str(ask_run),
        }

    question = (
        "Deep review this /review-plan target. Return a readiness verdict and "
        "only concrete blockers. Any critical, high, or medium blocker, missing "
        "artifact, failed validator, or insufficient evidence must prevent PASS."
    )
    command = [
        str(ask_run),
        "ask",
        question,
        "--deep-review",
        "--deep-review-target",
        str(target),
        "--deep-review-focus",
        focus,
        "--oracle-backend",
        "scillm",
        "--oracle-model",
        ask_model,
        "--oracle-reasoning",
        ask_reasoning,
        "--oracle-timeout",
        str(ask_timeout),
        "--ask-id",
        ask_id,
        "--overwrite",
        "--json",
    ]
    if run_output_root:
        command.extend(["--run-output-root", run_output_root])

    proc = subprocess.run(
        command,
        cwd=ask_root,
        capture_output=True,
        text=True,
        timeout=ask_timeout + 90,
    )
    collected = _collect_ask_run_artifacts(ask_root, ask_id)
    result = _finalize_ask_gate_result(
        proc=proc,
        ask_id=ask_id,
        command=command,
        backend="scillm",
        collected=collected,
    )
    result["plan_target"] = str(target.resolve())
    return result


def _write_gate_artifact(
    result: ReviewResult,
    output_dir: Path,
    iterations: int,
    ask_artifacts: dict | None = None,
    suggest_fixes: bool = True,
    spiral_guard: list[str] | None = None,
) -> GateResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    verdict, reason = _gate_verdict(result, ask_artifacts)
    payload = {
        "schema": "review_plan.gate.v1",
        "target": result.file,
        "verdict": verdict,
        "reason": reason,
        "iterations": iterations,
        "execution_policy": "single_preflight_then_orchestrate",
        "recommended_next_step": _recommended_next_step(verdict, result),
        "spiral_guard": spiral_guard or [],
        "counts": {
            "pass": result.pass_count,
            "warn": result.warn_count,
            "fail": result.fail_count,
        },
        "findings": review_result_to_dict(result, suggest_fixes=suggest_fixes)["findings"],
        "severity_to_loop_rule": "WARN and FAIL findings both block PASS for review-plan auto mode.",
        "next_iteration_plan": _next_iteration_plan(
            result, verdict=verdict, ask_artifacts=ask_artifacts
        ),
        "ask_artifacts": ask_artifacts or {},
    }
    path = output_dir / "review_result.json"
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return GateResult(
        verdict=verdict,
        reason=reason,
        review_result_json=str(path),
        iterations=iterations,
        next_iteration_plan=payload["next_iteration_plan"],
        ask_artifacts=ask_artifacts or {},
    )


def print_review_result(result: ReviewResult, path: Path, suggest_fixes: bool) -> None:
    print(f"# Review: {path.name}\n")
    print(f"## Summary")
    print(f"- Tasks: {result.tasks}")
    print(f"- Phases: {result.phases}")
    print(f"- WARN: {result.warn_count} | FAIL: {result.fail_count}\n")

    if result.fail_count > 0:
        print("## FAIL\n")
        for f in result.findings:
            if f.grade == "FAIL":
                print(f"### {f.task} (line {f.line})")
                print(f"- **{f.check}**: {f.message}")
                if suggest_fixes and f.suggestion:
                    print(f"- **Fix**: {f.suggestion}")
                print()

    if result.warn_count > 0:
        print("## WARN\n")
        for f in result.findings:
            if f.grade == "WARN":
                print(f"### {f.task} (line {f.line})")
                print(f"- **{f.check}**: {f.message}")
                if suggest_fixes and f.suggestion:
                    print(f"- **Suggest**: {f.suggestion}")
                print()

    if result.warn_count == 0 and result.fail_count == 0:
        print("All checks passed.")


@app.command()
def review(
    task_file: str = typer.Argument(..., help="Path to task file (0N_TASKS.md or plan)"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    suggest_fixes: bool = typer.Option(False, "--suggest-fixes", help="Include fix suggestions"),
    max_rounds: int = typer.Option(1, "--max-rounds", help="Bounded review rounds. >1 enables controller artifacts and fail-closed iteration status."),
    output_dir: str = typer.Option("", "--output-dir", help="Directory for review_result.json (default: artifacts/review-plan/<target>-<timestamp>)"),
    ask_gate: bool = typer.Option(False, "--ask-gate", help="Run real $ask as an external gate after deterministic checks pass"),
    ask_gate_backend: str = typer.Option("scillm", "--ask-gate-backend", help="Ask gate backend: scillm (deep-review) or webgpt"),
    ask_review_bundle: str = typer.Option(
        "",
        "--ask-review-bundle",
        help="Markdown review bundle for webgpt (text-only). Required sections: Review request, This round acceptance, Local gates",
    ),
    ask_attach_file: str = typer.Option(
        "",
        "--ask-attach-file",
        help="Zip path for webgpt when bundle includes images (max 5 files; include REQUEST.md, PLAN.md, or REVIEW.md)",
    ),
    ask_model: str = typer.Option("gpt-5.5", "--ask-model", help="Model for scillm --deep-review gate"),
    ask_reasoning: str = typer.Option("high", "--ask-reasoning", help="Reasoning effort for scillm --deep-review gate"),
    ask_timeout: int = typer.Option(900, "--ask-timeout", help="Timeout seconds for $ask gate"),
    ask_focus: str = typer.Option("plan-contract,ordering,definition-of-done,skill-overlap,iteration-gates", "--ask-focus", help="Comma-separated deep-review focus labels (scillm backend)"),
    webgpt_tab_id: str = typer.Option("", "--webgpt-tab-id", help="Chrome tab id for webgpt ask gate"),
    webgpt_project: str = typer.Option("", "--webgpt-project", help="Bound ChatGPT project name for webgpt ask gate"),
    oracle_iterations: int = typer.Option(
        1,
        "--oracle-iterations",
        help="Oracle rounds for webgpt gate (capped at 1; use /plan-iterate for phase loops)",
    ),
    allow_extended_review: bool = typer.Option(
        False,
        "--allow-extended-review",
        help="Allow --max-rounds up to 2 for a second human-driven preflight only (no automated loop)",
    ),
    webgpt_allow_foreground: bool = typer.Option(
        False,
        "--webgpt-allow-foreground",
        help="Set ASK_WEBGPT_ALLOW_FOREGROUND=1 when the controlled tab is the active Chrome tab",
    ),
):
    """Full review of a task file: claims, overlap, ordering, DoD, chains, tools."""
    if max_rounds < 1:
        logger.error("--max-rounds must be >= 1")
        raise typer.Exit(2)
    try:
        effective_max_rounds, effective_oracle_iterations, spiral_guard_notes = _apply_spiral_guards(
            max_rounds=max_rounds,
            allow_extended_review=allow_extended_review,
            ask_gate=ask_gate,
            oracle_iterations=oracle_iterations,
            ask_gate_backend=ask_gate_backend,
        )
    except ValueError as exc:
        logger.error(str(exc))
        raise typer.Exit(2)
    result = run_review_checks(task_file)
    path = Path(result.file)

    auto_mode = effective_max_rounds > 1 or ask_gate or bool(output_dir)
    gate: GateResult | None = None
    ask_artifacts: dict | None = None
    if auto_mode:
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", path.name).strip("-") or "plan"
        gate_dir = Path(output_dir) if output_dir else PROJECT_ROOT / "artifacts" / "review-plan" / f"{safe_name}-{ts}"
        if ask_gate and result.fail_count == 0 and result.warn_count == 0:
            bundle_path = Path(ask_review_bundle).resolve() if ask_review_bundle else None
            attach_path = ask_attach_file.strip()
            bundle_issues: list[str] = []
            if ask_gate_backend.strip().lower() == "webgpt":
                if attach_path:
                    bundle_issues.extend(validate_review_attach_zip(Path(attach_path)))
                elif bundle_path is not None:
                    bundle_issues.extend(validate_review_evidence_bundle(bundle_path))
                elif not attach_path and bundle_path is None:
                    bundle_issues.append(
                        "webgpt ask-gate requires --ask-review-bundle (.md) or --ask-attach-file (.zip)"
                    )
            if bundle_issues:
                ask_artifacts = {
                    "status": "blocked",
                    "backend": ask_gate_backend,
                    "reason": "review_evidence_bundle_invalid",
                    "bundle_issues": bundle_issues,
                }
            elif bundle_path is not None and not bundle_path.exists():
                ask_artifacts = {
                    "status": "blocked",
                    "backend": ask_gate_backend,
                    "reason": "ask_review_bundle_missing",
                    "review_bundle": str(bundle_path),
                }
            else:
                ask_artifacts = _run_ask_gate(
                    backend=ask_gate_backend,
                    target=path,
                    review_bundle=bundle_path,
                    attach_file=attach_path,
                    ask_id=f"review-plan-{safe_name}-{ts}",
                    ask_model=ask_model,
                    ask_reasoning=ask_reasoning,
                    ask_timeout=ask_timeout,
                    focus=ask_focus,
                    webgpt_tab_id=webgpt_tab_id,
                    webgpt_project=webgpt_project,
                    oracle_iterations=effective_oracle_iterations,
                    run_output_root=str(gate_dir / "ask-runs"),
                    webgpt_allow_foreground=webgpt_allow_foreground,
                )
        elif ask_gate:
            ask_artifacts = {
                "status": "skipped",
                "reason": "deterministic_review_findings_block_external_gate",
            }
        gate = _write_gate_artifact(
            result=result,
            output_dir=gate_dir,
            iterations=1,
            ask_artifacts=ask_artifacts,
            suggest_fixes=True,
            spiral_guard=spiral_guard_notes,
        )

    if output_json:
        output = review_result_to_dict(result, suggest_fixes=suggest_fixes)
        if gate:
            output["gate"] = {
                "verdict": gate.verdict,
                "reason": gate.reason,
                "review_result_json": gate.review_result_json,
                "iterations": gate.iterations,
                "next_iteration_plan": gate.next_iteration_plan,
                "ask_artifacts": gate.ask_artifacts,
            }
        print(json.dumps(output, indent=2))
    else:
        print_review_result(result, path, suggest_fixes=suggest_fixes)
        if gate:
            print("\n## Gate\n")
            print(f"- Verdict: {gate.verdict}")
            print(f"- Reason: {gate.reason}")
            print(f"- Artifact: {gate.review_result_json}")
            if gate.ask_artifacts:
                print(f"- Ask status: {gate.ask_artifacts.get('status')}")
                print(f"- Ask review JSON: {gate.ask_artifacts.get('review_json')}")

    blocked = result.fail_count > 0 or (gate is not None and gate.verdict != "PASS")
    raise typer.Exit(1 if blocked else 0)


@app.command()
def check(
    task_file: str = typer.Argument(..., help="Path to task file"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Quick check: claims + DoD only (skip chain validation)."""
    path = Path(task_file)
    if not path.exists():
        path = CALLER_ROOT / task_file
    if not path.exists():
        path = PROJECT_ROOT / task_file
    if not path.exists():
        logger.error(f"Task file not found: {task_file}")
        raise typer.Exit(1)

    content = path.read_text()
    structured_result = None
    if is_structured_plan(path):
        structured_result = validate_structured_plan(load_structured_plan(path))
        tasks, phases = parse_structured_task_file(path)
    else:
        tasks = parse_task_file(content)
        phases = count_phases(content)

    result = ReviewResult(file=str(path), tasks=len(tasks), phases=phases)

    for task in tasks:
        check_claims(task, result.findings)
        check_dod(task, result.findings)
        check_execution_routing(task, result.findings)
        check_scillm_backend(task, result.findings)

    if structured_result:
        for issue in structured_result["issues"]:
            result.findings.append(Finding("Plan", "structured-schema", "FAIL", issue, 1))
        for warning in structured_result["warnings"]:
            result.findings.append(Finding("Plan", "structured-schema", "WARN", warning, 1))

    if output_json:
        output = {
            "file": result.file,
            "tasks": result.tasks,
            "warn": result.warn_count,
            "fail": result.fail_count,
            "findings": [
                {"task": f.task, "check": f.check, "grade": f.grade, "message": f.message}
                for f in result.findings
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"Quick check: {path.name} — {result.tasks} tasks, {result.warn_count} WARN, {result.fail_count} FAIL")
        for f in result.findings:
            print(f"  [{f.grade}] {f.task}: {f.message}")

    raise typer.Exit(1 if result.fail_count > 0 else 0)



from dag_readiness import (
    validate_dag_readiness,
    validate_plans_two_file_layout,
    write_dag_readiness_report,
)


@app.command("dag-preflight")
def dag_preflight(
    dag_file: str = typer.Argument(
        "plans/review-design-subagent-orchestration.dag.json",
        help="Path to DAG JSON",
    ),
    registry_file: str = typer.Option(
        "workers-registry.json",
        "--registry",
        help="Workers registry JSON",
    ),
    output: str = typer.Option(
        "artifacts/review-design-orchestration/preflight/dag_readiness.json",
        "--output",
        help="Output path for dag_readiness.json",
    ),
    skip_phart: bool = typer.Option(False, "--skip-phart", help="Skip phart validate"),
    output_json: bool = typer.Option(False, "--json", help="Print report JSON to stdout"),
):
    """DAG readiness preflight (Phase 0) for orchestration plans."""
    dag_path = Path(dag_file)
    if not dag_path.is_absolute():
        for base in (CALLER_ROOT, PROJECT_ROOT):
            candidate = base / dag_file
            if candidate.exists():
                dag_path = candidate
                break
    if not dag_path.exists():
        logger.error(f"DAG not found: {dag_file}")
        raise typer.Exit(1)

    registry_path = Path(registry_file)
    if not registry_path.is_absolute():
        for base in (CALLER_ROOT, PROJECT_ROOT):
            candidate = base / registry_file
            if candidate.exists():
                registry_path = candidate
                break
    if not registry_path.exists():
        logger.error(f"Registry not found: {registry_file}")
        raise typer.Exit(1)

    out_path = Path(output)
    if not out_path.is_absolute():
        base = CALLER_ROOT if (CALLER_ROOT / "plans").is_dir() else PROJECT_ROOT
        out_path = base / output

    repo_root = CALLER_ROOT if (CALLER_ROOT / "plans").is_dir() else PROJECT_ROOT

    report = validate_dag_readiness(
        dag_path=dag_path,
        registry_path=registry_path,
        project_root=repo_root,
        run_phart=not skip_phart,
    )
    written = write_dag_readiness_report(report, out_path)

    bundle_script = repo_root / "scripts" / "build_review_bundle.py"
    if bundle_script.is_file():
        proc = subprocess.run(
            [sys.executable, str(bundle_script), "--skip-checks"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            report.blocking_errors.append(
                f"build_review_bundle: exit {proc.returncode}: {(proc.stderr or proc.stdout or '')[:500]}"
            )
            report.ok = False
        elif proc.stdout.strip():
            print(proc.stdout.strip())

    layout_errors, layout_warnings = validate_plans_two_file_layout(repo_root)
    for err in layout_errors:
        report.blocking_errors.append(f"plans_layout: {err}")
    report.warnings.extend(layout_warnings)
    if layout_errors:
        report.ok = False

    if output_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"DAG preflight: {'PASS' if report.ok else 'FAIL'}")
        print(f"Report: {written}")
        if report.missing_agents:
            print(f"  missing_agents: {report.missing_agents}")
        if report.missing_agents_md:
            print(f"  missing_agents_md: {report.missing_agents_md}")
        for err in report.blocking_errors:
            print(f"  BLOCK: {err}")
        for warn in report.warnings:
            print(f"  WARN: {warn}")

    raise typer.Exit(0 if report.ok else 1)


if __name__ == "__main__":
    app()
