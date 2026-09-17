"""Delegate to installed owning skills; never imitate their receipt schemas or green gates."""
import os
import shutil
import subprocess
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from loguru import logger

from a_detection.errors import Code, DetectionError
from a_detection.io import atomic_json, utc_now

load_dotenv(override=False)
def invoke_native(skill: Literal["setup-project", "agentic-evals"], project: Path,
                  output: Path, mode: str = "audit") -> int:
    root_text = os.environ.get("AGENT_SKILLS_ROOT")
    root = Path(root_text).expanduser().resolve() if root_text else None
    executable = root / "skills" / skill / "run.sh" if root else None
    if executable is None or not executable.is_file() or shutil.which("bash") is None:
        atomic_json(output, {"schema_version": "a_detection.native_invocation.v1", "skill": skill,
            "executed": False, "status": "BLOCKED_EXTERNAL", "created_at": utc_now(),
            "reason": "Set AGENT_SKILLS_ROOT to a local checkout containing the owning skill.",
            "native_receipt": None})
        raise DetectionError(Code.BLOCKED, "The owning skill is not present in the local runtime.")
    if skill == "setup-project":
        config = yaml.safe_load((project / "setup-project.yaml").read_text(encoding="utf-8"))
        config["project_root"] = str(project.resolve())
        runtime_config = output.parent / "setup-project.resolved.yaml"
        runtime_config.parent.mkdir(parents=True, exist_ok=True)
        runtime_config.write_text(yaml.safe_dump(config), encoding="utf-8")
        argv = ["bash", str(executable), mode, "--config", str(runtime_config.resolve())]
    else:
        fixture = project / "fixtures" / ("agentic_eval.json" if mode == "release" else "mechanisms.json")
        argv = ["bash", str(executable), "run", str(fixture.resolve()), "--output", str(output.resolve())]
    # The owning skill owns schema validation and exit semantics. Retain stdout opaquely.
    with (output.parent / f"{skill}.stdout.log").open("wb") as stdout, \
         (output.parent / f"{skill}.stderr.log").open("wb") as stderr:
        try:
            result = subprocess.run(argv, cwd=project, check=False, stdout=stdout, stderr=stderr,
                                    timeout=1800)
        except subprocess.TimeoutExpired as exc:
            logger.error("native_skill_timeout skill={}", skill)
            raise DetectionError(Code.BLOCKED, "The owning skill exceeded its invocation timeout.") from exc
    if skill == "setup-project":
        raw = (output.parent / f"{skill}.stdout.log").read_bytes()
        output.write_bytes(raw)
    return result.returncode
