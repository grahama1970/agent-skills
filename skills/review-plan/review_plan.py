"""review-plan: Validate task files before /orchestrate."""
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import typer
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
MANIFEST_PATH = PROJECT_ROOT / ".pi" / "skills-manifest.json"

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
    tasks: list[dict] = []
    planned_paths = {
        str(path_ref)
        for item in summary["tasks"]
        for field_name in ("allowlist", "tests", "blind_tests")
        for path_ref in (item.get(field_name) or [])
        if isinstance(path_ref, str)
    }
    for item in summary["tasks"]:
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
        tasks.append({
            "id": item.get("id", ""),
            "title": item.get("title", ""),
            "line": 1,
            "body": "\n".join(body_parts),
            "dod": json.dumps(dod),
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
            "definition_of_done": item.get("definition_of_done") or {},
            "planned_paths": planned_paths,
        })
    return tasks, 0


def count_phases(content: str) -> int:
    return len(re.findall(r"^#{1,2}\s+Phase\s+\d+", content, re.MULTILINE))


# ─── Checkers ────────────────────────────────────────────────────────────────


def check_claims(task: dict, findings: list[Finding]):
    """Check 1: Verify file paths and references exist in the codebase."""
    body = task["body"]

    # Extract file paths from backticks and markdown
    file_refs = re.findall(r"`([^`]*(?:\.(?:py|ts|js|rs|go|sh|json|toml|yaml|yml|md))\b[^`]*)`", body)
    # Also catch paths in **bold** or plain text
    file_refs += re.findall(r"(?:^|\s)((?:\.?/)?(?:[\w.-]+/)+[\w.-]+\.(?:py|ts|js|rs|go|sh|json|toml|yaml|yml|md))\b", body)

    for ref in file_refs:
        # Clean up the reference
        ref = ref.strip().split(":")[0]  # Remove :line_number
        if ref.startswith("~"):
            continue  # Skip home-relative paths
        if ref.startswith("/tmp/"):
            continue  # Skip generated temp artifacts
        if ref in task.get("planned_paths", set()):
            continue  # Skip files this structured plan declares as future outputs/tests
        if ref.startswith("/") and not ref.startswith("/."):
            full_path = Path(ref)
        else:
            full_path = PROJECT_ROOT / ref

        if not full_path.exists() and not any(
            PROJECT_ROOT.glob(f"**/{Path(ref).name}")
        ):
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
        if any(k in body or k in title for k in ["edit", "implement", "refactor", "patch", "build page", "write file"]):
            # Skip for pattern-following design tasks — scillm one-shot is correct
            combined = f"{title}\n{body}"
            pattern_reuse_kw = [
                r"same\s+pattern\s+as", r"reuse\s+.*pattern", r"follow.*pattern",
                r"pattern\s+from", r"follows\s+existing", r"existing\s+pattern",
            ]
            design_kw = [
                r"\.tsx", r"component", r"react", r"embry", r"gatechain", r"recallcard",
                r"ux-lab", r"types\.ts", r"routes\.ts", r"artifact", r"shared-chat",
            ]
            has_pattern = any(re.search(p, combined, re.I) for p in pattern_reuse_kw)
            has_design = any(re.search(p, combined, re.I) for p in design_kw)
            if has_pattern and has_design:
                pass  # Pattern-following design task — scillm one-shot is appropriate
            else:
                findings.append(Finding(
                    task=f"Task {task['id']}",
                    check="routing",
                    grade="FAIL",
                    message="Task appears iterative/edit-heavy but is routed to `scillm` one-shot.",
                    line=task["line"],
                    suggestion="Use `code-runner` for iterative or file-editing work.",
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
                grade="WARN",
                message="code-runner task missing backend — defaults to sonnet",
                line=task["line"],
                suggestion="Set `backend:` explicitly (sonnet for boilerplate, opus for complex).",
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
        if len(depends) >= 3 and not read_ctx:
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="routing",
                grade="WARN",
                message=f"code-runner task depends on {len(depends)} tasks but has no read_context. "
                        f"Empirical data: ~50% fail rate on text backend without read_context for 3+ deps.",
                line=task["line"],
                suggestion="Add `read_context:` listing the dependency files the LLM should read for interface context. "
                           "Code-runner extracts interface maps (signatures + types) from these files.",
            ))
        # Allowlist check
        if not allowlist and not task.get("allowlist_optional"):
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="routing",
                grade="WARN",
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
                grade="WARN",
                message="code-runner without allowlist or DoD assertion — use scillm for simple edits",
                line=task["line"],
                suggestion="code-runner is expensive (worktree, git cycle, multi-round). "
                           "Use runner: scillm for mechanical edits, config changes, text generation.",
            ))
        if dod_cmd and not dod_assert and "assert" not in dod_cmd.lower() and "test" not in dod_cmd.lower():
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="routing",
                grade="WARN",
                message="code-runner DoD has no assertion and doesn't run tests — LLM may game it",
                line=task["line"],
                suggestion="Add `assertion:` or include assert statements in the DoD command. "
                           "Consider adding `blind_tests:` for adversarial verification.",
            ))
        # Blind tests enforcement — code-runner tasks MUST have blind_tests for adversarial verification
        blind_tests = task.get("blind_tests") or task.get("tests") or []
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
        # External API detection — DoD should use mocks, real API calls go in blind_tests
        import re as _re
        if dod_cmd and _re.search(r'https?://|curl\s|requests\.get|httpx\.\w+|urllib', dod_cmd):
            findings.append(Finding(
                task=f"Task {task['id']}",
                check="routing",
                grade="WARN",
                message="code-runner DoD calls an external URL/API — flaky and non-deterministic",
                line=task["line"],
                suggestion="Use mock-based DoD for code-runner (test against fake responses). "
                           "Move the real API integration test to `blind_tests:` which runs in "
                           "/test-lab Docker with network access.",
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
    "text-gemini", "text-gemini-oauth", "text-gemini-paid", "text-gemini-3", "text-gemini-3-paid",
    "text-claude", "text-claude-opus", "text-claude-haiku",
    "gpt-5.5", "gpt-5.3-codex", "text-glm",
    "vlm", "vlm-paid", "vlm-claude", "vlm-codex",
    "local-text", "moonshot-text",
    # Pattern-based (auto-routed)
    # claude-*, gpt-*, codex-*, gemini-*, Org/Model, model:tag
}

# Legacy/deprecated backend names that need updating
LEGACY_BACKEND_NAMES = {
    "sonnet": "text-claude",
    "opus": "text-claude-opus",
    "haiku": "text-claude-haiku",
    "codex": "gpt-5.5",
    "gemini": "text-gemini-oauth",
    "claude": "text-claude",
}


# code-runner accepts short backend names and translates them internally
CODE_RUNNER_BACKENDS = {"codex", "claude", "text", "gemini", "deepseek", "test"}


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
                   f"Common models: text, text-claude, text-claude-opus, gpt-5.5, text-gemini-oauth",
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
            import subprocess
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


# ─── Check 9 & 10: Design Board + PNG Evidence (see ux_checks.py) ────────────
from ux_checks import check_design_board, check_png_evidence, check_lab_subagent


# ─── Commands ────────────────────────────────────────────────────────────────


@app.command()
def review(
    task_file: str = typer.Argument(..., help="Path to task file (0N_TASKS.md or plan)"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    suggest_fixes: bool = typer.Option(False, "--suggest-fixes", help="Include fix suggestions"),
):
    """Full review of a task file: claims, overlap, ordering, DoD, chains, tools."""
    path = Path(task_file)
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

    if output_json:
        output = {
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
        print(json.dumps(output, indent=2))
    else:
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

    raise typer.Exit(1 if result.fail_count > 0 else 0)


@app.command()
def check(
    task_file: str = typer.Argument(..., help="Path to task file"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Quick check: claims + DoD only (skip chain validation)."""
    path = Path(task_file)
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


if __name__ == "__main__":
    app()
