"""Exercise the real hub CLI and renderers against current production source.

Modes emit retained command logs and independently read back output bytes.
No renderer or service is mocked. Failures exit nonzero; these checks establish
local draft delivery only, not agent interpretation or visual acceptance.
"""

import ast
import hashlib
import json
import subprocess
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

import typer
from defusedxml import ElementTree
from loguru import logger

SKILL = Path(__file__).resolve().parents[1]
OUTPUT = Path("/mnt/storage12tb/skills/create-architecture/outputs/evals")


class Mode(StrEnum):
    SMOKE = "smoke"
    LIVE = "live"
    ADVERSARIAL = "adversarial"
    GSN = "gsn"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def invoke(
    directory: Path,
    name: str,
    args: list[str],
    code: int = 0,
    cwd: Path = SKILL.parent.parent,
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [str(SKILL / "run.sh"), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    write_json(
        directory / f"{name}.command.json",
        {
            "argv": result.args,
            "cwd": str(cwd),
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )
    require(
        result.returncode == code,
        f"{name}: expected {code}, got {result.returncode}: {result.stderr}",
    )
    return result


def request_for(directory: Path) -> dict:
    source = SKILL / "hub.py"
    inventory = json.loads(invoke(directory, "examine", [str(source)]).stdout)
    require(inventory["target"] == str(source), "Caller target was changed")
    require(
        inventory["status"] == "NEEDS_SOURCE_READING",
        "Inventory claimed semantic analysis",
    )
    require(
        inventory["sources"][0]["sha256"] == sha(source), "Source fingerprint mismatch"
    )
    return {
        "target": str(source),
        "question": "Explain the bounded module dependency view",
        "rationale": "Source-authored diagram with explicit omissions",
        "sources": inventory["sources"],
        "view": "structure",
        "surface": "publication",
        "limitations": ["Not a full runtime architecture; source subset only."],
    }


def native_inputs() -> dict:
    tree = ast.parse((SKILL / "hub.py").read_text(encoding="utf-8"))
    imports = sorted(
        {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    )
    require("hub_models" in imports, "Live source no longer imports hub_models")
    names = imports[:4]
    require(len(names) == 4, "Fanout proof needs four real imported modules")
    commands = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "run_skill"
    ]
    operations = {
        n.value
        for call in commands
        for n in ast.walk(call)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }
    require(
        {"chart", "validate"} <= operations,
        "PHART source branch changed; reauthor proof",
    )
    return {
        "publication": {
            "project_name": "Hub imports",
            "components": [
                {"name": "hub", "dependencies": names},
                *[{"name": name, "type": "external"} for name in names],
            ],
        },
        "svg": {
            "schema_version": 1,
            "template": "fanout-anatomy",
            "theme": "fixing-opus-neon-v1",
            "metadata": {
                "title": "Hub imports",
                "description": "Four selected imports from current hub.py; other imports omitted",
            },
            "source": {"title": "hub.py", "subtitle": "selected module imports"},
            "targets": [
                {
                    "number": i + 1,
                    "heading": name,
                    "detail": "imported dependency",
                    "accent": accent,
                }
                for i, (name, accent) in enumerate(
                    zip(names, ["green", "cyan", "amber", "orange"], strict=True)
                )
            ],
            "caption": "SELECTED IMPORTS ONLY; NOT RUNTIME ORDER",
        },
        "terminal": {
            "schema_version": "ask.dag.v1",
            "graph_id": "hub-phart-render",
            "description": "PHART branch calls validate before chart; rendering only, not task execution",
            "nodes": [
                {
                    "id": "validate",
                    "type": "skill.run",
                    "depends_on": [],
                    "input": {"skill": "phart-dag-chart", "args": ["validate"]},
                },
                {
                    "id": "chart",
                    "type": "skill.run",
                    "depends_on": ["validate"],
                    "input": {"skill": "phart-dag-chart", "args": ["chart"]},
                },
            ],
        },
    }


def smoke(directory: Path) -> None:
    request_for(directory)
    default = json.loads(invoke(directory, "default-target", [], cwd=SKILL).stdout)
    require(default["target"] == str(SKILL), "No-argument invocation lost caller cwd")
    relative = json.loads(
        invoke(directory, "relative-target", ["hub.py"], cwd=SKILL).stdout
    )
    require(relative["target"] == str(SKILL / "hub.py"), "Relative module path changed")
    for view, surface, expected in [
        ("dag", "terminal", "phart-dag-chart"),
        ("structure", "svg", "create-svg"),
        ("assurance", "auto", "create-gsn-diagram"),
        ("structure", "auto", "create-figure"),
        ("structure", "interactive", "ux-lab"),
        ("structure", "whiteboard", "ops-excalidraw"),
        ("sequence", "auto", "project-infographic"),
    ]:
        route = json.loads(
            invoke(
                directory,
                f"route-{surface}-{view}",
                ["route", "--view", view, "--surface", surface],
            ).stdout
        )
        require(route["skill"] == expected, f"Wrong route for {view}/{surface}")
        require(Path(route["instructions"]).is_file(), "Route instruction file missing")
    gate = invoke(
        directory,
        "legacy-gate",
        ["create", "--name", "Unauthorized", "--json", '[{"id":"a","label":"A"}]'],
        3,
    )
    require(
        "REJECTED_SCOPE_EXPANSION" in gate.stderr + gate.stdout,
        "Legacy mutation gate changed",
    )


def live(directory: Path) -> None:
    base = request_for(directory)
    for surface, native in native_inputs().items():
        input_path = directory / f"{surface}.json"
        write_json(input_path, native)
        request = {
            **base,
            "surface": surface,
            "native_input": str(input_path),
            "view": "dag" if surface == "terminal" else "structure",
        }
        request_path = directory / f"{surface}-request.json"
        write_json(request_path, request)
        bundle = directory / surface
        invoke(
            directory,
            surface,
            ["render", str(request_path), "--output-dir", str(bundle)],
        )
        receipt = json.loads((bundle / "receipt.json").read_text(encoding="utf-8"))
        for field in (
            "request",
            "native_input",
            "artifact",
            *(["preview"] if surface != "terminal" else []),
        ):
            record = receipt[field]
            file = Path(record["path"])
            require(
                sha(file) == record["sha256"]
                and file.stat().st_size == record["bytes"],
                f"{field} not bound to actual bytes",
            )
        diagram = Path(receipt["artifact"]["path"])
        if surface == "terminal":
            text = diagram.read_text(encoding="utf-8")
            require("validate" in text and "chart" in text, "Missing DAG nodes")
        else:
            preview = Path(receipt["preview"]["path"])
            require(
                'src="diagram.svg"' in preview.read_text(encoding="utf-8"),
                "Preview points outside retained bundle",
            )
            root = ElementTree.fromstring(diagram.read_bytes())
            text = " ".join(root.itertext())
            require("hub" in text.lower(), "Source module label absent")
            for name in native_inputs()["publication"]["components"][0]["dependencies"]:
                require(name in text, f"Missing imported module {name}")
        require(
            receipt["status"] == "DRAFT" and receipt["visual_review"] == "NOT_RUN",
            "Draft silently approved",
        )
        original = sha(diagram)
        rejected = invoke(
            directory,
            f"{surface}-immutable",
            ["render", str(request_path), "--output-dir", str(bundle)],
            1,
        )
        require(
            "output_exists" in rejected.stderr and sha(diagram) == original,
            "Previous diagram not preserved",
        )


def gsn(directory: Path) -> None:
    request = request_for(directory)
    native = directory / "selector.json"
    write_json(native, {"control": "AC-1"})
    request.update(view="assurance", surface="svg", native_input=str(native))
    request_path = directory / "request.json"
    write_json(request_path, request)
    bundle = directory / "gsn"
    invoke(directory, "gsn", ["render", str(request_path), "--output-dir", str(bundle)])
    receipt = json.loads((bundle / "receipt.json").read_text(encoding="utf-8"))
    diagram = Path(receipt["artifact"]["path"])
    require(sha(diagram) == receipt["artifact"]["sha256"], "GSN artifact hash mismatch")
    labels = " ".join(ElementTree.fromstring(diagram.read_bytes()).itertext())
    require("AC-1" in labels and "G1" in labels, "GSN goal/control labels missing")
    require(
        all("--dry-run" not in command for command in receipt["commands"]),
        "GSN silently used sample evidence",
    )
    require(receipt["status"] == "DRAFT", "GSN draft was promoted to approval")


def adversarial(directory: Path) -> None:
    base = request_for(directory)
    native_path = directory / "native.json"
    write_json(native_path, native_inputs()["publication"])
    base["native_input"] = str(native_path)
    for name, changes, code, error in [
        (
            "stale",
            {"sources": [{**base["sources"][0], "sha256": "0" * 64}]},
            1,
            "stale_source",
        ),
        ("no-evidence", {"sources": []}, 2, "invalid_request"),
        ("unknown-field", {"execute": True}, 2, "extra_forbidden"),
        (
            "lossy-route",
            {"view": "lifecycle", "surface": "terminal"},
            1,
            "unsupported_route",
        ),
        ("handoff", {"surface": "interactive"}, 1, "agent_handoff_required"),
        ("out-of-scope", {"target": str(SKILL / "hub_cli.py")}, 1, "source_scope"),
    ]:
        request_path = directory / f"{name}.json"
        write_json(request_path, {**base, **changes})
        bundle = directory / name
        result = invoke(
            directory,
            name,
            ["render", str(request_path), "--output-dir", str(bundle)],
            code,
        )
        require(
            error in result.stderr and not bundle.exists(),
            f"{name}: invalid input published output or missing error",
        )
    for name, payload, changes, error in [
        (
            "query-injection",
            {"control": 'AC-1" OR true'},
            {"view": "assurance", "surface": "svg"},
            "string_pattern_mismatch",
        ),
        (
            "unknown-edge",
            {
                "project_name": "Hub",
                "components": [{"name": "hub", "dependencies": ["absent"]}],
            },
            {},
            "figure_dependency",
        ),
        (
            "identity-collision",
            {"project_name": "Hub", "components": [{"name": "a-b"}, {"name": "a_b"}]},
            {},
            "figure_identity",
        ),
    ]:
        write_json(native_path, payload)
        request_path = directory / f"{name}.json"
        write_json(request_path, {**base, **changes})
        result = invoke(
            directory,
            name,
            ["render", str(request_path), "--output-dir", str(directory / name)],
            2,
        )
        require(
            error in result.stderr and not (directory / name).exists(),
            f"{name} accepted unsafe native input",
        )
    dag = native_inputs()["terminal"]
    dag["nodes"][0]["depends_on"] = ["chart"]
    write_json(native_path, dag)
    request_path = directory / "cycle.json"
    write_json(request_path, {**base, "view": "dag", "surface": "terminal"})
    result = invoke(
        directory,
        "cycle",
        ["render", str(request_path), "--output-dir", str(directory / "cycle")],
        1,
    )
    require(
        "cycle" in result.stderr and not (directory / "cycle").exists(),
        "Cycle was flattened or published",
    )


def main(mode: Mode = Mode.SMOKE) -> None:
    directory = OUTPUT / f"{mode}-{uuid4().hex}"
    directory.mkdir(parents=True)
    try:
        {
            Mode.SMOKE: smoke,
            Mode.LIVE: live,
            Mode.ADVERSARIAL: adversarial,
            Mode.GSN: gsn,
        }[mode](directory)
    except Exception as exc:
        logger.error("Hub eval failed; retained commands at {}: {}", directory, exc)
        raise typer.Exit(1) from exc
    typer.echo(
        json.dumps(
            {
                "mode": mode,
                "readback": True,
                "mocked": False,
                "live": True,
                "evidence": str(directory),
            }
        )
    )


if __name__ == "__main__":
    typer.run(main)
