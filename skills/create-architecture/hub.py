"""Examine source targets and delegate diagram drafts to existing skill entrypoints.

The invoking agent owns source interpretation and native scene authorship. This
module binds sources to drafts, validates subprocess boundaries, and publishes an
immutable bundle only after the selected renderer succeeds. Expected failures
carry stable codes; no service mutation or automatic visual approval occurs here.
"""

import hashlib
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from defusedxml import ElementTree
from dotenv import load_dotenv
from hub_models import (
    Artifact,
    AssuranceSelector,
    Delivery,
    ErrorCode,
    Examination,
    FigureInput,
    Request,
    Route,
    Source,
    Surface,
    SvgValidation,
    View,
)

SKILL = Path(__file__).resolve().parent
SKILLS = SKILL.parent
DEFAULT_OUTPUT = Path("/mnt/storage12tb/skills/create-architecture/outputs")
EXCLUDED = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    "build",
    "dist",
    "outputs",
    "sessions",
}
SOURCE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".rs",
    ".go",
    ".java",
    ".sh",
    ".md",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
}


class HubError(ValueError):
    """A code-bearing failure suitable for CLI steering."""

    def __init__(self, code: ErrorCode, message: str):
        self.code = code
        super().__init__(message)


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def artifact(path: Path) -> Artifact:
    data = path.read_bytes()
    return Artifact(path=path, sha256=digest(data), bytes=len(data))


def check_source_path(path: Path, root: Path) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root) or not path.is_relative_to(root):
        raise HubError(
            ErrorCode.SOURCE_SCOPE, f"Source must stay within target scope: {path}"
        )
    for candidate in (path, resolved):
        if any(p in EXCLUDED for p in candidate.relative_to(root).parts):
            raise HubError(
                ErrorCode.SOURCE_SCOPE, f"Excluded source directory: {candidate}"
            )
        if (
            candidate.name.startswith(".env")
            or candidate.suffix in {".pem", ".key"}
            or candidate.name in {"auth.json", "credentials.json"}
        ):
            raise HubError(
                ErrorCode.SENSITIVE_SOURCE,
                f"Do not use credential files as diagram evidence: {candidate.name}",
            )
    if not resolved.is_file() or resolved.stat().st_size > 1_000_000:
        raise HubError(
            ErrorCode.SOURCE_SIZE,
            f"Source must be a regular text file under 1 MB: {path}",
        )
    return resolved


def examine(target: Path) -> Examination:
    target = target.expanduser().resolve(strict=True)
    root = target if target.is_dir() else target.parent
    if target.is_file():
        candidates = [target]
    else:
        result = subprocess.run(
            ["rg", "--files", "--hidden", str(target)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode not in (0, 1):
            raise HubError(ErrorCode.SOURCE_DISCOVERY, result.stderr)
        candidates = sorted(Path(line) for line in result.stdout.splitlines())
    sources = []
    eligible = [
        p
        for p in candidates
        if p.suffix in SOURCE_SUFFIXES
        and not any(part in EXCLUDED for part in p.relative_to(root).parts)
        and not p.name.startswith(".env")
        and p.name not in {"auth.json", "credentials.json"}
    ]
    for path in eligible[:80]:
        checked = check_source_path(path, root)
        data = checked.read_bytes()
        if b"\x00" in data:
            continue
        data.decode("utf-8")
        sources.append(Source(path=checked, sha256=digest(data)))
    if not sources:
        raise HubError(
            ErrorCode.NO_SOURCES,
            "No eligible source files found; narrow or correct the target.",
        )
    return Examination(
        target=target,
        sources=sources,
        discovered=len(eligible),
        truncated=len(eligible) > 80,
    )


def load_request(path: Path) -> Request:
    request = Request.model_validate_json(path.read_bytes())
    base = path.resolve().parent
    request.target = (base / request.target).resolve(strict=True)
    if request.native_input is not None:
        request.native_input = (base / request.native_input).resolve(strict=True)
    for source in request.sources:
        source.path = (base / source.path).absolute()
    verify_sources(request)
    return request


def verify_sources(request: Request) -> None:
    root = request.target if request.target.is_dir() else request.target.parent
    for source in request.sources:
        path = check_source_path(source.path, root)
        if request.target.is_file() and path != request.target:
            raise HubError(
                ErrorCode.SOURCE_SCOPE,
                "A module request may cite only that module; use its directory for broader scope.",
            )
        data = path.read_bytes()
        if digest(data) != source.sha256:
            raise HubError(
                ErrorCode.STALE_SOURCE,
                f"Source changed; reread and regenerate the diagram: {path}",
            )
        lines = data.decode("utf-8").splitlines()
        if (source.end_line or source.start_line) > len(lines):
            raise HubError(
                ErrorCode.SOURCE_LINES, f"Citation exceeds source line count: {path}"
            )


def select_route(view: View, surface: Surface) -> Route:
    if surface == Surface.AUTO:
        surface = (
            Surface.PUBLICATION
            if view in {View.STRUCTURE, View.ASSURANCE}
            else Surface.TERMINAL
            if view == View.DAG
            else Surface.DOCUMENT
        )
    if view == View.ASSURANCE:
        if surface not in {Surface.PUBLICATION, Surface.SVG}:
            raise HubError(
                ErrorCode.UNSUPPORTED_ROUTE,
                "Assurance requires GSN output; do not flatten it into a generic graph.",
            )
        skill, mode, reason = (
            "create-gsn-diagram",
            "executable",
            "Preserve claims, arguments, and evidence semantics.",
        )
    elif surface == Surface.TERMINAL:
        if view != View.DAG:
            raise HubError(
                ErrorCode.UNSUPPORTED_ROUTE,
                "PHART requires a DAG; cycles and sequence semantics cannot be silently discarded.",
            )
        skill, mode, reason = (
            "phart-dag-chart",
            "executable",
            "Render the native execution DAG for terminal reading.",
        )
    elif surface == Surface.SVG:
        skill, mode, reason = (
            "create-svg",
            "executable",
            "Use a bounded native SVG scene; unsupported layouts need another surface.",
        )
    elif surface == Surface.PUBLICATION and view == View.STRUCTURE:
        skill, mode, reason = (
            "create-figure",
            "executable",
            "Render a source-authored component/dependency graph.",
        )
    elif surface == Surface.INTERACTIVE:
        skill, mode, reason = (
            "ux-lab",
            "agent-handoff",
            "Reuse the owning application's React Flow components; no generic runtime adapter is installed.",
        )
    elif surface == Surface.WHITEBOARD:
        skill, mode, reason = (
            "ops-excalidraw",
            "agent-handoff",
            "Use editable Excalidraw tooling; preserve its approval and publication gates.",
        )
    elif surface == Surface.DOCUMENT:
        skill, mode, reason = (
            "project-infographic",
            "agent-handoff",
            "Compose a source-grounded explanation through the existing agent workflow. Archify is deferred.",
        )
    else:
        raise HubError(
            ErrorCode.UNSUPPORTED_ROUTE,
            f"No lossless route for {view}/{surface}; choose a supported surface.",
        )
    instructions = SKILLS / skill / "SKILL.md"
    if not instructions.is_file():
        raise HubError(
            ErrorCode.MISSING_SKILL, f"Missing canonical skill: {instructions}"
        )
    return Route(
        skill=skill,
        mode=mode,
        view=view,
        surface=surface,
        reason=reason,
        instructions=instructions,
    )


def run_skill(
    skill: str, args: list[str], commands: list[list[str]], directory: Path
) -> str:
    # Preserve exported values; support direct Python invocation as well as run.sh.
    load_dotenv(SKILLS.parent.parent / ".env", override=False)
    executable = SKILLS / skill / "run.sh"
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise HubError(
            ErrorCode.MISSING_ENTRYPOINT, f"Missing executable: {executable}"
        )
    argv = [str(executable), *args]
    commands.append(argv)
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env.pop("UV_PROJECT_ENVIRONMENT", None)
    # Some existing wrappers resolve sibling skills from cwd. Inputs/outputs
    # are absolute, so invoke each skill from its canonical directory.
    result = subprocess.run(
        argv,
        cwd=executable.parent,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    (directory / f"command-{len(commands)}.stdout").write_text(
        result.stdout, encoding="utf-8"
    )
    (directory / f"command-{len(commands)}.stderr").write_text(
        result.stderr, encoding="utf-8"
    )
    if result.returncode:
        raise HubError(
            ErrorCode.DOWNSTREAM_FAILED,
            f"{skill} exited {result.returncode}: {result.stderr[-4000:]} {result.stdout[-2000:]}",
        )
    return result.stdout


def render(request: Request, output: Path | None = None) -> Delivery:
    route = select_route(request.view, request.surface)
    if route.mode != "executable":
        raise HubError(
            ErrorCode.AGENT_HANDOFF_REQUIRED,
            f"Read {route.instructions}. {route.reason}",
        )
    if request.native_input is None:
        raise HubError(
            ErrorCode.NATIVE_INPUT_REQUIRED,
            f"Author native input using {route.instructions}; do not ask the human for renderer JSON.",
        )
    verify_sources(request)
    native_bytes = request.native_input.read_bytes()
    if len(native_bytes) > 2_000_000:
        raise HubError(ErrorCode.INPUT_SIZE, "Native diagram input exceeds 2 MB.")
    destination = (output or DEFAULT_OUTPUT / uuid4().hex).expanduser().absolute()
    if destination.exists():
        raise HubError(
            ErrorCode.OUTPUT_EXISTS,
            "Bundles are immutable. Choose a new output directory; previous output is preserved.",
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    commands: list[list[str]] = []
    with TemporaryDirectory(
        prefix=".architecture-", dir=destination.parent
    ) as temporary:
        staging = Path(temporary)
        native = staging / ("input" + request.native_input.suffix)
        native.write_bytes(native_bytes)
        frozen = staging / "request.json"
        frozen.write_text(request.model_dump_json(indent=2), encoding="utf-8")
        diagram = staging / (
            "diagram.txt" if route.skill == "phart-dag-chart" else "diagram.svg"
        )
        if route.skill == "phart-dag-chart":
            run_skill(
                route.skill, ["validate", str(native), "--json"], commands, staging
            )
            diagram.write_text(
                run_skill(route.skill, ["chart", str(native)], commands, staging),
                encoding="utf-8",
            )
            if not diagram.read_text(encoding="utf-8").strip():
                raise HubError(ErrorCode.EMPTY_DIAGRAM, "PHART produced no chart.")
        elif route.skill == "create-svg":
            # Freeze local theme inputs too; bundled theme names stay backend-owned.
            import yaml

            scene = yaml.safe_load(native_bytes)
            if (
                isinstance(scene, dict)
                and isinstance(scene.get("theme"), str)
                and (
                    "/" in scene["theme"] or scene["theme"].endswith((".yml", ".yaml"))
                )
            ):
                raise HubError(
                    ErrorCode.THEME_SCOPE,
                    "Use a bundled theme for hub drafts; custom assets require direct create-svg workflow.",
                )
            run_skill(
                route.skill, ["render", str(native), str(diagram)], commands, staging
            )
            validation = staging / "backend.receipt.json"
            run_skill(
                route.skill,
                ["validate", str(diagram), "--receipt", str(validation)],
                commands,
                staging,
            )
            receipt = SvgValidation.model_validate_json(validation.read_bytes())
            if receipt.source_sha256 != artifact(diagram).sha256:
                raise HubError(
                    ErrorCode.RECEIPT_HASH,
                    "SVG validation receipt does not match artifact bytes.",
                )
        elif route.skill == "create-figure":
            FigureInput.model_validate_json(native_bytes)
            run_skill(
                route.skill,
                [
                    "architecture",
                    "--project",
                    str(native),
                    "--output",
                    str(diagram),
                    "--format",
                    "svg",
                    "--backend",
                    "graphviz",
                ],
                commands,
                staging,
            )
        else:
            selector = AssuranceSelector.model_validate_json(native_bytes)
            args = (
                ["--control", selector.control]
                if selector.control
                else ["--framework", selector.framework]
            )
            run_skill(
                route.skill,
                ["render", *args, "--output", str(diagram)],
                commands,
                staging,
            )
        preview = None
        if diagram.suffix == ".svg":
            root = ElementTree.fromstring(diagram.read_bytes())
            if root.tag.rsplit("}", 1)[-1] != "svg" or not list(root):
                raise HubError(
                    ErrorCode.INVALID_SVG,
                    "Renderer did not produce a nonempty SVG document.",
                )
            preview = staging / "preview.html"
            run_skill(
                "create-svg", ["preview", str(diagram), str(preview)], commands, staging
            )
        verify_sources(request)
        if request.native_input.read_bytes() != native_bytes:
            raise HubError(
                ErrorCode.STALE_NATIVE_INPUT,
                "Native input changed during rendering; regenerate from current sources.",
            )
        receipt = Delivery(
            route=route,
            request=artifact(frozen).model_copy(
                update={"path": destination / frozen.name}
            ),
            native_input=artifact(native).model_copy(
                update={"path": destination / native.name}
            ),
            artifact=artifact(diagram).model_copy(
                update={"path": destination / diagram.name}
            ),
            preview=artifact(preview).model_copy(
                update={"path": destination / preview.name}
            )
            if preview
            else None,
            sources=request.sources,
            commands=commands,
            created_at=datetime.now(UTC).isoformat(),
            proof_scope="Real renderer invocation, input/artifact hashes, current source fingerprints, and structural validation. Not semantic accuracy or visual acceptance.",
            limitations=request.limitations
            + [
                "Draft only: complete the selected skill's human and visual gates before publication."
            ],
        )
        (staging / "receipt.json").write_text(
            receipt.model_dump_json(indent=2), encoding="utf-8"
        )
        if destination.exists():
            raise HubError(
                ErrorCode.OUTPUT_EXISTS,
                "Output appeared during rendering; refusing replacement.",
            )
        os.rename(staging, destination)
    return receipt
