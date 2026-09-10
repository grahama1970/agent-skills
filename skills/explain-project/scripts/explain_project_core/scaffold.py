"""Generic project intake for explain-project.

Scaffolding is deliberately conservative: it finds an entrypoint, reads nearby
project state and diagram references, then emits one strict explainer record the
project agent can refine. It does not infer full architecture.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import FeatureExplainer

DIAGRAM_RE = re.compile(
    r"https?://\S*excalidraw\S*|(?<![\w/-])([\w./-]+\.(?:excalidraw|svg))"
)
PROJECT_STATE = Path(__file__).resolve().parents[3] / "project-state/run.sh"
OPS_EXCALIDRAW = Path(__file__).resolve().parents[3] / "ops-excalidraw/run.sh"
DEBUGGER = Path(__file__).resolve().parents[3] / "debugger/run.sh"


@dataclass(frozen=True)
class SourceTarget:
    file: str
    start_line: int
    end_line: int
    symbol: str | None
    breakpoint_line: int | None


@dataclass(frozen=True)
class DiagramRef:
    source: str
    source_kind: str
    rendered_svg: str | None
    editable: bool
    found_in: str


def _rel(repo: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return str(path)


def _first_code_target(repo: Path, entrypoint: Path) -> SourceTarget:
    text = entrypoint.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines() or [""]

    if entrypoint.suffix == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            tree = None
        if tree is not None:
            candidates = [
                node
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            ]
            preferred = next((node for node in candidates if getattr(node, "name", "") == "main"), None)
            node = preferred or (candidates[0] if candidates else None)
            if node is not None:
                body = list(getattr(node, "body", []))
                if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
                    body = body[1:]
                bp = body[0].lineno if body else node.lineno
                return SourceTarget(
                    file=_rel(repo, entrypoint),
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    symbol=getattr(node, "name", None),
                    breakpoint_line=bp,
                )

    for index, line in enumerate(lines, 1):
        if line.strip() and not line.startswith("#!"):
            end = min(len(lines), index + 60)
            return SourceTarget(_rel(repo, entrypoint), index, end, None, index)
    return SourceTarget(_rel(repo, entrypoint), 1, len(lines), None, None)


def _candidate_files(repo: Path, entrypoint: Path) -> list[Path]:
    files = [entrypoint]
    for name in ("README.md", "PROJECT_STATE.md", "PROJECT_KNOWLEDGE.md"):
        path = repo / name
        if path.is_file():
            files.append(path)
    docs = repo / "docs"
    if docs.is_dir():
        files.extend(sorted(docs.rglob("*.md"))[:50])
        files.extend(sorted(docs.rglob("*.py"))[:50])
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in files:
        resolved = path.resolve()
        if resolved not in seen and path.is_file() and path.stat().st_size < 1_000_000:
            unique.append(path)
            seen.add(resolved)
    return unique


def _resolve_ref(repo: Path, owner: Path, raw: str) -> tuple[str, bool]:
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw.rstrip(".,);]\"'"), True
    cleaned = raw.rstrip(".,);]\"'")
    path = Path(cleaned)
    candidates = [path] if path.is_absolute() else [repo / path, owner.parent / path]
    for candidate in candidates:
        if candidate.exists():
            return _rel(repo, candidate), True
    return cleaned, False


def find_diagrams(repo: Path, entrypoint: Path) -> list[DiagramRef]:
    refs: list[DiagramRef] = []
    seen: set[str] = set()
    for path in _candidate_files(repo, entrypoint):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in DIAGRAM_RE.finditer(text):
            raw = match.group(0)
            ref, exists_or_url = _resolve_ref(repo, path, raw)
            if ref in seen:
                continue
            seen.add(ref)
            if "excalidraw" in ref.lower():
                refs.append(DiagramRef(ref, "excalidraw", None, True, _rel(repo, path)))
            elif ref.endswith(".svg") and exists_or_url:
                refs.append(DiagramRef(ref, "svg", ref, False, _rel(repo, path)))
    return refs


def _project_state_boundary(project_state: Path | None) -> str:
    if project_state is None:
        return "No project-state receipt was bound during scaffold generation."
    digest = hashlib.sha256(project_state.read_bytes()).hexdigest() if project_state.is_file() else "missing"
    return f"Project-state receipt: {project_state} sha256:{digest}."


def run_project_state(repo: Path, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(PROJECT_STATE), "report", "--quick", "--json", "--output", str(output)],
        cwd=str(repo),
        check=True,
        text=True,
        capture_output=True,
        timeout=90,
    )
    return output


def scaffold_record(repo: Path, entrypoint: Path, project_state: Path | None = None) -> FeatureExplainer:
    target = _first_code_target(repo, entrypoint)
    diagrams = find_diagrams(repo, entrypoint)
    diagram = diagrams[0] if diagrams else DiagramRef(
        "docs/explain/boards/project-overview.excalidraw",
        "excalidraw",
        None,
        True,
        "default",
    )

    record: dict[str, Any] = {
        "schema": "project.feature_explainer.v1",
        "feature_id": "project.entrypoint",
        "title": f"Project entrypoint: {Path(target.file).name}",
        "question_family": "walkthrough",
        "question": "Walk me through this project from its entrypoint.",
        "teleprompter_points": [
            f"Start at `{target.file}`.",
            "Use `$project-state` as the current health/context receipt.",
            f"Diagram source discovered from `{diagram.found_in}`: `{diagram.source}`.",
            "Use `$debugger` breakpoints only where runtime state answers the human's question.",
        ],
        "source_ranges": [
            {
                "file": target.file,
                "start_line": target.start_line,
                "end_line": target.end_line,
                "symbol": target.symbol,
            }
        ],
        "diagram": {
            "source_kind": diagram.source_kind,
            "source_path": diagram.source,
            "node_ids": ["entrypoint", "state", "diagram"],
            "rendered_svg_path": diagram.rendered_svg,
            "editable": diagram.editable,
            "compiled_by": "discovered from source/docstring/doc references",
        },
        "proof_boundary": (
            "Scaffolded from local files. It identifies a starting point, diagram references, "
            "and breakpoint targets; it does not prove architecture completeness. "
            + _project_state_boundary(project_state)
        ),
        "debugger_stops": [],
        "confidence": "low",
        "steps": [
            {
                "step_id": "entrypoint",
                "title": "Start at the entrypoint",
                "bullets": [
                    f"Open `{target.file}`.",
                    "Explain what calls or owns this code before following branches.",
                ],
                "source_range_index": 0,
                "source_explanation": "Entry point selected by explicit CLI argument.",
                "debugger_stop_index": 0 if target.breakpoint_line else None,
                "diagram_node_ids": ["entrypoint"],
                "proof_boundary": "Entrypoint selection is caller-provided, not inferred architecture.",
                "confidence": "medium",
            },
            {
                "step_id": "project-state",
                "title": "Read current project state",
                "bullets": [
                    "Ground the walkthrough in `$project-state` before claims.",
                    "Separate verified health from unverified architecture guesses.",
                ],
                "source_range_index": 0,
                "source_explanation": _project_state_boundary(project_state),
                "diagram_node_ids": ["state"],
                "proof_boundary": "Project-state is context, not proof that every feature works.",
                "confidence": "medium" if project_state else "low",
            },
            {
                "step_id": "diagram",
                "title": "Bring in existing diagrams",
                "bullets": [
                    f"Use `{diagram.source}` as the first visual artifact.",
                    "If it is stale, update through `$ops-excalidraw` or `$create-svg`.",
                ],
                "source_range_index": 0,
                "source_explanation": f"Diagram reference found in {diagram.found_in}.",
                "diagram_node_ids": ["diagram"],
                "proof_boundary": "Discovered diagram references may still be stale until reviewed.",
                "confidence": "medium" if diagrams else "low",
            },
        ],
    }
    if target.breakpoint_line:
        record["debugger_stops"] = [
            {
                "file": target.file,
                "line": target.breakpoint_line,
                "locals": [],
                "watches": [],
                "proves": "Runtime reached the scaffolded project entrypoint.",
            }
        ]

    return FeatureExplainer.model_validate(record)


def write_scaffold(repo: Path, entrypoint: Path, output: Path, project_state: Path | None) -> dict[str, Any]:
    record = scaffold_record(repo, entrypoint, project_state)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(record.model_dump_json(by_alias=True) + "\n", encoding="utf-8")
    return {
        "schema": "explain_project.scaffold.v1",
        "status": "PASS",
        "repo": str(repo),
        "entrypoint": str(entrypoint),
        "output": str(output),
        "feature_id": record.feature_id,
        "diagram": record.diagram.model_dump(by_alias=True, mode="json"),
        "debugger_stops": [stop.model_dump(by_alias=True, mode="json") for stop in record.debugger_stops],
        "project_state": str(project_state) if project_state else None,
    }


def milestone_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-").lower()
    return slug or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_milestone(repo: Path, entrypoint: Path, milestone: str, output_dir: Path | None = None) -> dict[str, Any]:
    slug = milestone_slug(milestone)
    root = output_dir or repo / "docs/explain/milestones" / slug
    root.mkdir(parents=True, exist_ok=True)
    project_state = run_project_state(repo, root / "project-state.quick.json")
    scaffold = write_scaffold(repo, entrypoint, root / "explainers.jsonl", project_state)
    receipt = {
        "schema": "explain_project.milestone.v1",
        "status": "PASS",
        "milestone": milestone,
        "repo": str(repo),
        "entrypoint": str(entrypoint),
        "output_dir": str(root),
        "project_state": str(project_state),
        "explainers": scaffold["output"],
        "diagram": scaffold["diagram"],
        "debugger_stops": scaffold["debugger_stops"],
        "next_commands": {
            "validate": f"skills/explain-project/run.sh validate {scaffold['output']}",
            "cockpit": f"skills/explain-project/run.sh cockpit --repo {repo} --explainers {scaffold['output']}",
        },
        "proof_boundary": "Milestone refresh updates explain-project scaffolds and a quick project-state receipt. It does not mutate code docstrings, accept Excalidraw proposals, or prove diagram freshness without human/project-agent review.",
    }
    # Curated catalog + stale/missing diagram findings (criterion #11).
    curated_path = repo / "docs" / "explain" / "explainers.jsonl"
    stale_diagrams: list[dict[str, Any]] = []
    curated_count = 0
    if curated_path.is_file():
        from .catalog import read_jsonl as _read_jsonl

        curated_rows = _read_jsonl(curated_path)
        curated_count = len(curated_rows)
        for row in curated_rows:
            finding = {
                "feature_id": row.feature_id,
                "source_path": row.diagram.source_path,
                "verified": bool(row.diagram.sha256),
            }
            rendered = row.diagram.rendered_svg_path
            if not row.diagram.source_path:
                finding["finding"] = "missing-diagram-source"
            elif not row.diagram.sha256:
                finding["finding"] = "unverified-diagram-binding"
            elif rendered and not (repo / rendered).is_file():
                finding["finding"] = "rendered-svg-missing"
            else:
                continue
            stale_diagrams.append(finding)
    receipt["curated_explainers"] = curated_count
    receipt["stale_diagrams"] = stale_diagrams
    dump_path = root / "receipt.json"
    dump_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-").lower()
    return slug[:80] or "question"


def _tokens(value: str) -> set[str]:
    stop = {"the", "and", "for", "that", "this", "with", "does", "why", "what", "how", "from", "into", "wait", "when"}
    return {part for part in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", value.lower()) if part not in stop}


def _code_files(repo: Path) -> list[Path]:
    skip = {".git", ".venv", "node_modules", "dist", "build", "__pycache__"}
    files: list[Path] = []
    for suffix in ("*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.rs", "*.go"):
        for path in repo.rglob(suffix):
            if any(part in skip for part in path.parts):
                continue
            if path.is_file() and path.stat().st_size < 500_000:
                files.append(path)
    return sorted(files)


def _target_for_question_in_file(repo: Path, path: Path, question: str) -> SourceTarget:
    if path.suffix != ".py":
        return _first_code_target(repo, path)
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _first_code_target(repo, path)
    want = _tokens(question)
    best: tuple[int, ast.AST] | None = None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        hay = " ".join(
            part
            for part in (
                getattr(node, "name", ""),
                ast.get_docstring(node) or "",
                ast.get_source_segment(text, node) or "",
            )
        ).lower()
        score = sum(4 if token == getattr(node, "name", "").lower() else 1 for token in want if token in hay)
        if score and (best is None or score > best[0]):
            best = (score, node)
    if best is None:
        return _first_code_target(repo, path)
    node = best[1]
    body = list(getattr(node, "body", []))
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
        body = body[1:]
    bp = body[0].lineno if body else getattr(node, "lineno", None)
    return SourceTarget(
        file=_rel(repo, path),
        start_line=node.lineno,
        end_line=getattr(node, "end_lineno", node.lineno),
        symbol=getattr(node, "name", None),
        breakpoint_line=bp,
    )


def _select_question_target(repo: Path, question: str, entrypoint: Path | None = None) -> SourceTarget:
    if entrypoint is not None:
        return _target_for_question_in_file(repo, entrypoint, question)
    want = _tokens(question)
    best: tuple[int, Path] | None = None
    for path in _code_files(repo):
        text = path.read_text(encoding="utf-8", errors="replace")
        hay = text.lower() + " " + path.as_posix().lower()
        score = sum(3 if token in path.stem.lower() else 1 for token in want if token in hay)
        if score and (best is None or score > best[0]):
            best = (score, path)
    if best is None:
        readme = repo / "README.md"
        if readme.is_file():
            return _first_code_target(repo, readme)
        raise ValueError("no relevant source file found for question")
    return _target_for_question_in_file(repo, best[1], question)


def _diagram_id(repo: Path, question: str) -> str:
    return f"{repo.name}.{_slug(question)}"


def _ensure_question_diagram(repo: Path, question: str, target: SourceTarget, out: Path) -> tuple[DiagramRef, dict[str, Any]]:
    entry = repo / target.file
    existing = find_diagrams(repo, entry)
    diagram_id = _diagram_id(repo, question)
    registry = out / "diagram-registry.json"
    if existing:
        diagram = existing[0]
    else:
        board = out / "diagrams" / f"{diagram_id}.excalidraw"
        board.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                str(OPS_EXCALIDRAW),
                "describe",
                "--source",
                question,
                "--target",
                target.symbol or target.file,
                "--target",
                f"breakpoint {target.file}:{target.breakpoint_line or target.start_line}",
                "--title",
                f"Question: {question[:80]}",
                "--output",
                str(board),
            ],
            check=True,
            text=True,
            capture_output=True,
            timeout=90,
        )
        diagram = DiagramRef(str(board), "excalidraw", None, True, "created by ops-excalidraw describe")
    register = subprocess.run(
        [
            str(OPS_EXCALIDRAW),
            "register-diagram",
            "--diagram-id",
            diagram_id,
            "--owner-project",
            repo.name,
            "--source-path",
            diagram.source,
            "--bound-symbol",
            f"{target.file}:{target.symbol or target.start_line}",
            "--registry",
            str(registry),
        ],
        check=True,
        text=True,
        capture_output=True,
        timeout=90,
    )
    return diagram, json.loads(register.stdout)


def _question_record(question: str, repo: Path, target: SourceTarget, diagram: DiagramRef, project_state: Path) -> FeatureExplainer:
    bp_index = 0 if target.breakpoint_line else None
    record: dict[str, Any] = {
        "schema": "project.feature_explainer.v1",
        "feature_id": _slug(question).replace("-", "."),
        "title": f"Answer: {question[:70]}",
        "question_family": "walkthrough",
        "question": question,
        "teleprompter_points": [
            "Here is the short version in plain English.",
            f"The answer is in `{target.file}`.",
            "We will connect the code, diagram, and runtime proof one step at a time.",
            "Anything not proven by the shown source or receipts stays a non-claim.",
        ],
        "source_ranges": [{"file": target.file, "start_line": target.start_line, "end_line": target.end_line, "symbol": target.symbol}],
        "diagram": {
            "source_kind": diagram.source_kind,
            "source_path": diagram.source,
            "node_ids": ["question", "source", "breakpoint"],
            "rendered_svg_path": diagram.rendered_svg,
            "editable": diagram.editable,
            "compiled_by": "ops-excalidraw registry",
        },
        "proof_boundary": f"Question-first scaffold from local source plus project-state receipt {project_state}. Teaching tone is plain, spoken, and concise; architecture completeness is not claimed.",
        "debugger_stops": [],
        "confidence": "medium",
        "steps": [
            {"step_id": "question", "title": "Answer the question first", "bullets": ["Start with the direct answer.", "Name the source file before details."], "source_range_index": 0, "source_explanation": f"Selected for question tokens: {', '.join(sorted(_tokens(question))[:6])}.", "diagram_node_ids": ["question"], "proof_boundary": "Lexical source selection is a starting point for project-agent review.", "confidence": "medium"},
            {"step_id": "source", "title": "Walk the code slowly", "bullets": [f"Open `{target.file}`.", "Explain one branch or state change at a time."], "source_range_index": 0, "source_explanation": "This source range is the cockpit's first teaching path.", "debugger_stop_index": bp_index, "diagram_node_ids": ["source"], "proof_boundary": "Source explains behavior only for this range.", "confidence": "medium"},
            {"step_id": "breakpoint", "title": "Pause only when state matters", "bullets": ["Use `$debugger` when a live value answers the question.", "Show captured locals as proof, not as decoration."], "source_range_index": 0, "source_explanation": "Breakpoint target is created for the relevant code path.", "debugger_stop_index": bp_index, "diagram_node_ids": ["breakpoint"], "proof_boundary": "Debugger execution requires a debugger-owned proof receipt.", "confidence": "medium"},
        ],
    }
    if target.breakpoint_line:
        record["debugger_stops"] = [{"file": target.file, "line": target.breakpoint_line, "locals": [], "watches": [], "proves": f"Runtime reached the code path that answers: {question}"}]
    return FeatureExplainer.model_validate(record)


def answer_question(repo: Path, question: str, out: Path, entrypoint: Path | None = None, debug_command: str | None = None) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    project_state = run_project_state(repo, out / "project-state.quick.json")
    target = _select_question_target(repo, question, entrypoint)
    diagram, diagram_receipt = _ensure_question_diagram(repo, question, target, out)
    record = _question_record(question, repo, target, diagram, project_state)
    explainers = out / "explainers.jsonl"
    explainers.write_text(record.model_dump_json(by_alias=True) + "\n", encoding="utf-8")
    breakpoints = [{"file": stop.file, "line": stop.line, "proves": stop.proves} for stop in record.debugger_stops]
    debugger_proof = None
    if debug_command and breakpoints:
        proof_path = out / "debugger-proof.json"
        cmd = [str(DEBUGGER), "break", f"{breakpoints[0]['file']}:{breakpoints[0]['line']}", "--capture-all-locals", "--out", str(proof_path), "--", *shlex.split(debug_command)]
        subprocess.run(cmd, cwd=str(repo), check=True, text=True, capture_output=True, timeout=180)
        subprocess.run([str(DEBUGGER), "validate", str(proof_path), "--expect-valid", "--repo-root", str(repo)], cwd=str(repo), check=True, text=True, capture_output=True, timeout=90)
        debugger_proof = str(proof_path)
    monitor = {
        "schema": "explain_project.question_first_monitor.v1",
        "status": "PASS",
        "question": question,
        "route": "CREATED",
        "repo": str(repo),
        "out": str(out),
        "explainers": str(explainers),
        "project_state": str(project_state),
        "selected_source": target.__dict__,
        "breakpoints": breakpoints,
        "debugger_proof": debugger_proof,
        "diagram": record.diagram.model_dump(by_alias=True, mode="json"),
        "diagram_registry_receipt": diagram_receipt,
        "teaching_tone": "plain spoken concise",
        "proof_boundary": "Creates a question-first cockpit bundle, diagram registry metadata, and breakpoint targets. Debugger runtime proof is present only when debug_command is supplied.",
    }
    (out / "monitor.json").write_text(json.dumps(monitor, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return monitor
