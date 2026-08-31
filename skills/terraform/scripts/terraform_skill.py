"""Terraform-made-easy CLI for the /terraform skill.

Purpose: make plain Terraform usable end to end — scaffold a best-practice
project layout in a target root, audit an existing root's .tf organization,
run fmt/validate checks (delegated to /ops-terraform), generate a deployment
interview for the human (delegated to /interview), and run gated
init/plan/apply for deployment.

Inputs: a target module/project directory, optional flags per subcommand.
Outputs: typed JSON outcomes on stdout with status PASS|FAIL|NOT_CONFIGURED
and a failure_code on every non-PASS. Logs go to stderr via loguru.

Failure modes: missing terraform binary (NOT_CONFIGURED), missing target dir,
subprocess failure/timeout, refusal to overwrite existing files, and apply
without the explicit --yes human gate. All failures exit non-zero.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import typer
from loguru import logger

app = typer.Typer(add_completion=False, no_args_is_help=True)

SKILL_DIR = Path(__file__).resolve().parents[1]
SKILLS_ROOT = SKILL_DIR.parent
OPS_TERRAFORM_RUN = SKILLS_ROOT / "ops-terraform" / "run.sh"
INTERVIEW_RUN = SKILLS_ROOT / "interview" / "run.sh"

SUBPROCESS_TIMEOUT_S = 120
PLAN_TIMEOUT_S = 900
APPLY_TIMEOUT_S = 3600


class Status(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class FailureCode(StrEnum):
    TERRAFORM_MISSING = "terraform_missing"
    TARGET_MISSING = "target_missing"
    TARGET_NOT_EMPTY = "target_not_empty"
    DELEGATE_MISSING = "delegate_missing"
    SUBPROCESS_FAILED = "subprocess_failed"
    SUBPROCESS_TIMEOUT = "subprocess_timeout"
    LAYOUT_VIOLATIONS = "layout_violations"
    APPLY_NOT_CONFIRMED = "apply_not_confirmed"
    PLAN_FILE_MISSING = "plan_file_missing"


@dataclass
class Outcome:
    command: str
    status: Status
    detail: dict = field(default_factory=dict)
    failure_code: FailureCode | None = None

    def emit(self) -> None:
        payload = {
            "schema": "terraform_skill.outcome.v1",
            "command": self.command,
            "status": self.status.value,
            "failure_code": self.failure_code.value if self.failure_code else None,
            "ts": datetime.now(UTC).isoformat(),
            "detail": self.detail,
        }
        print(json.dumps(payload, indent=2))
        if self.status is not Status.PASS:
            raise typer.Exit(code=1)


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = SUBPROCESS_TIMEOUT_S) -> subprocess.CompletedProcess:
    logger.info("exec: {} (cwd={})", " ".join(cmd), cwd or Path.cwd())
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _terraform_bin() -> str | None:
    return shutil.which("terraform")


# ---------------------------------------------------------------------------
# Scaffold templates: HashiCorp standard module structure
# (main.tf / variables.tf / outputs.tf split, versions pinning, tfvars per
# environment, modules/ for reusable children, no secrets in VCS).
# ---------------------------------------------------------------------------

VERSIONS_TF = """terraform {
  required_version = ">= 1.5.0"

  required_providers {
    # Pin every provider you use. Example:
    # aws = {
    #   source  = "hashicorp/aws"
    #   version = "~> 5.0"
    # }
  }

  # Configure a remote backend before team use. Example:
  # backend "s3" {}
}
"""

MAIN_TF = """# Root module resources and child module calls live here.
# Keep this file for composition; put reusable pieces under modules/.
"""

VARIABLES_TF = """# All input variables for the root module.
# Every variable gets a type and a description; defaults only when safe.

variable "environment" {
  type        = string
  description = "Deployment environment name (e.g. dev, staging, prod)."
}
"""

OUTPUTS_TF = """# All root module outputs, each with a description.
"""

PROVIDERS_TF = """# Provider configuration blocks. Credentials come from the
# environment or shared config files — never hardcode them here.
"""

TFVARS_EXAMPLE = """# Copy to <env>.tfvars and fill in real values.
environment = "dev"
"""

GITIGNORE = """# Local .terraform directories
**/.terraform/*

# State files contain secrets — never commit them
*.tfstate
*.tfstate.*

# Crash logs
crash.log
crash.*.log

# Real variable values (commit only *.tfvars.example)
*.tfvars
*.tfvars.json
!*.tfvars.example

# Override files
override.tf
override.tf.json
*_override.tf
*_override.tf.json

# Plan output files
*.tfplan

# CLI config
.terraformrc
terraform.rc
"""

README_MD = """# {name}

Terraform root module scaffolded by the /terraform skill using the standard
HashiCorp module structure.

## Layout

- `main.tf` — resources and child module calls (composition only)
- `variables.tf` — all input variables, typed and described
- `outputs.tf` — all outputs, described
- `versions.tf` — Terraform + provider version pins, backend config
- `providers.tf` — provider blocks (no credentials)
- `envs/` — per-environment `*.tfvars` files (gitignored; commit `.example` only)
- `modules/` — reusable child modules, each with its own main/variables/outputs

## Workflow

```bash
terraform init
terraform fmt -recursive
terraform validate
terraform plan -var-file=envs/dev.tfvars -out=dev.tfplan
terraform apply dev.tfplan
```
"""

SCAFFOLD_FILES: dict[str, str] = {
    "versions.tf": VERSIONS_TF,
    "main.tf": MAIN_TF,
    "variables.tf": VARIABLES_TF,
    "outputs.tf": OUTPUTS_TF,
    "providers.tf": PROVIDERS_TF,
    ".gitignore": GITIGNORE,
    "envs/dev.tfvars.example": TFVARS_EXAMPLE,
}

EXPECTED_ROOT_FILES = ("main.tf", "variables.tf", "outputs.tf", "versions.tf")
SECRETY_TRACKED = ("terraform.tfstate", "*.tfstate")


@app.command()
def doctor() -> None:
    """Report terraform binary, version, and delegate skill availability."""
    tf = _terraform_bin()
    detail: dict = {
        "terraform_path": tf,
        "ops_terraform_delegate": OPS_TERRAFORM_RUN.exists(),
        "interview_delegate": INTERVIEW_RUN.exists(),
    }
    if tf is None:
        Outcome("doctor", Status.NOT_CONFIGURED, detail, FailureCode.TERRAFORM_MISSING).emit()
        return
    proc = _run([tf, "version", "-json"])
    if proc.returncode != 0:
        detail["stderr"] = proc.stderr.strip()
        Outcome("doctor", Status.FAIL, detail, FailureCode.SUBPROCESS_FAILED).emit()
        return
    detail["version"] = json.loads(proc.stdout).get("terraform_version")
    Outcome("doctor", Status.PASS, detail).emit()


@app.command()
def scaffold(
    target: Path = typer.Argument(..., help="Project root to scaffold"),
    name: str = typer.Option(None, help="Project name for README (default: dir name)"),
    force: bool = typer.Option(False, help="Write into a directory that already has .tf files"),
) -> None:
    """Create a best-practice Terraform project layout in TARGET."""
    target = target.expanduser().resolve()
    existing_tf = list(target.glob("*.tf")) if target.exists() else []
    if existing_tf and not force:
        Outcome(
            "scaffold",
            Status.FAIL,
            {"target": str(target), "existing_tf": [p.name for p in existing_tf]},
            FailureCode.TARGET_NOT_EMPTY,
        ).emit()
        return

    written: list[str] = []
    skipped: list[str] = []
    for rel, content in SCAFFOLD_FILES.items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not force:
            skipped.append(rel)
            continue
        path.write_text(content, encoding="utf-8")
        written.append(rel)
    readme = target / "README.md"
    if not readme.exists():
        readme.write_text(README_MD.format(name=name or target.name), encoding="utf-8")
        written.append("README.md")
    (target / "modules").mkdir(exist_ok=True)

    # Read-back receipt: verify every claimed file actually exists on disk.
    missing_after_write = [rel for rel in written if not (target / rel).is_file()]
    status = Status.PASS if not missing_after_write else Status.FAIL
    Outcome(
        "scaffold",
        status,
        {
            "target": str(target),
            "written": written,
            "skipped_existing": skipped,
            "missing_after_write": missing_after_write,
        },
        None if status is Status.PASS else FailureCode.SUBPROCESS_FAILED,
    ).emit()


@app.command()
def organize(
    target: Path = typer.Argument(..., help="Existing Terraform project root to audit"),
) -> None:
    """Audit TARGET against the standard layout; report violations (dry-run, no moves)."""
    target = target.expanduser().resolve()
    if not target.is_dir():
        Outcome("organize", Status.FAIL, {"target": str(target)}, FailureCode.TARGET_MISSING).emit()
        return

    violations: list[dict] = []
    tf_files = sorted(p.name for p in target.glob("*.tf"))
    for expected in EXPECTED_ROOT_FILES:
        if expected not in tf_files:
            violations.append(
                {
                    "rule": "standard-root-files",
                    "message": f"missing {expected} in project root",
                    "fix": f"create {expected} (run: ./run.sh scaffold {target} --force to fill gaps)",
                }
            )
    for state in target.glob("*.tfstate*"):
        violations.append(
            {
                "rule": "no-state-in-root-vcs",
                "message": f"state file present: {state.name} — state holds secrets",
                "fix": "move state to a remote backend and gitignore *.tfstate",
            }
        )
    gitignore = target / ".gitignore"
    if not gitignore.exists() or "*.tfstate" not in gitignore.read_text(encoding="utf-8"):
        violations.append(
            {
                "rule": "gitignore-state",
                "message": ".gitignore missing or does not exclude *.tfstate / *.tfvars",
                "fix": "add the terraform .gitignore from ./run.sh scaffold",
            }
        )
    for tfvars in target.glob("*.tfvars"):
        violations.append(
            {
                "rule": "tfvars-per-env",
                "message": f"{tfvars.name} sits in root; environment values belong in envs/",
                "fix": f"move {tfvars.name} to envs/ and commit only a .example twin",
            }
        )
    monoliths = [
        p.name
        for p in target.glob("*.tf")
        if p.name not in EXPECTED_ROOT_FILES + ("providers.tf",)
        and len(p.read_text(encoding="utf-8").splitlines()) > 300
    ]
    for m in monoliths:
        violations.append(
            {
                "rule": "split-monoliths",
                "message": f"{m} exceeds 300 lines — extract reusable pieces into modules/",
                "fix": "create modules/<component>/{main,variables,outputs}.tf and call it from main.tf",
            }
        )

    status = Status.PASS if not violations else Status.FAIL
    Outcome(
        "organize",
        status,
        {"target": str(target), "tf_files": tf_files, "violations": violations},
        None if status is Status.PASS else FailureCode.LAYOUT_VIOLATIONS,
    ).emit()


@app.command()
def check(
    target: Path = typer.Argument(..., help="Module directory to fmt-check and validate"),
) -> None:
    """Delegate fmt -check + validate (backend=false) to /ops-terraform."""
    if not OPS_TERRAFORM_RUN.exists():
        Outcome("check", Status.NOT_CONFIGURED, {"delegate": str(OPS_TERRAFORM_RUN)}, FailureCode.DELEGATE_MISSING).emit()
        return
    try:
        proc = _run([str(OPS_TERRAFORM_RUN), "check", str(target.expanduser().resolve())], timeout=PLAN_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        Outcome("check", Status.FAIL, {"target": str(target)}, FailureCode.SUBPROCESS_TIMEOUT).emit()
        return
    detail: dict = {"target": str(target), "delegate": "ops-terraform"}
    try:
        detail["delegate_report"] = json.loads(proc.stdout)
    except json.JSONDecodeError:
        detail["stdout"] = proc.stdout.strip()[-4000:]
        detail["stderr"] = proc.stderr.strip()[-4000:]
    status = Status.PASS if proc.returncode == 0 else Status.FAIL
    Outcome("check", status, detail, None if status is Status.PASS else FailureCode.SUBPROCESS_FAILED).emit()


DEPLOY_QUESTIONS = {
    "title": "Terraform Deployment Interview",
    "context": "Answers drive backend, environment, and apply decisions for this Terraform project.",
    "questions": [
        {
            "id": "cloud_provider",
            "header": "Provider",
            "text": "Which cloud provider is this deployment targeting?",
            "options": [
                {"label": "AWS", "description": "hashicorp/aws provider"},
                {"label": "GCP", "description": "hashicorp/google provider"},
                {"label": "Azure", "description": "hashicorp/azurerm provider"},
                {"label": "Other/local", "description": "Another provider or local-only resources"},
            ],
            "multi_select": False,
        },
        {
            "id": "backend",
            "header": "Backend",
            "text": "Where should Terraform state live?",
            "options": [
                {"label": "Remote object store (Recommended)", "description": "S3/GCS/Azure blob with locking — safe for teams"},
                {"label": "HCP Terraform", "description": "app.terraform.io workspace manages state and runs (pairs with tfctl)"},
                {"label": "Local state", "description": "Only for throwaway experiments; state holds secrets"},
            ],
            "multi_select": False,
        },
        {
            "id": "environments",
            "header": "Envs",
            "text": "Which environments do you need tfvars files for?",
            "options": [
                {"label": "dev", "description": "Development"},
                {"label": "staging", "description": "Pre-production"},
                {"label": "prod", "description": "Production"},
            ],
            "multi_select": True,
        },
        {
            "id": "apply_gate",
            "header": "Apply gate",
            "text": "Who approves terraform apply?",
            "options": [
                {"label": "Human reviews plan first (Recommended)", "description": "Agent runs plan; human confirms before apply --yes"},
                {"label": "Auto-apply in CI", "description": "Pipeline applies after plan passes policy checks"},
            ],
            "multi_select": False,
        },
        {
            "id": "secrets",
            "header": "Secrets",
            "text": "How are provider credentials supplied?",
            "options": [
                {"label": "Environment variables", "description": "e.g. AWS_PROFILE / GOOGLE_APPLICATION_CREDENTIALS"},
                {"label": "Vault or secrets manager", "description": "Fetched at plan/apply time"},
                {"label": "Not decided yet", "description": "Blocker — decide before first apply"},
            ],
            "multi_select": False,
        },
    ],
}


@app.command()
def interview(
    out: Path = typer.Option(Path("terraform-interview-questions.json"), help="Where to write the question file"),
    launch: bool = typer.Option(True, help="Launch the /interview skill UI (TUI/HTML)"),
) -> None:
    """Write the deployment questionnaire and hand it to the /interview skill."""
    out = out.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(DEPLOY_QUESTIONS, indent=2), encoding="utf-8")
    detail: dict = {"questions_file": str(out), "question_count": len(DEPLOY_QUESTIONS["questions"])}
    if not launch:
        Outcome("interview", Status.PASS, detail).emit()
        return
    if not INTERVIEW_RUN.exists():
        Outcome("interview", Status.NOT_CONFIGURED, detail, FailureCode.DELEGATE_MISSING).emit()
        return
    proc = _run([str(INTERVIEW_RUN), "--file", str(out)], timeout=APPLY_TIMEOUT_S)
    detail["interview_exit_code"] = proc.returncode
    detail["stdout_tail"] = proc.stdout.strip()[-2000:]
    status = Status.PASS if proc.returncode == 0 else Status.FAIL
    Outcome("interview", status, detail, None if status is Status.PASS else FailureCode.SUBPROCESS_FAILED).emit()


@app.command()
def deploy(
    target: Path = typer.Argument(..., help="Module directory to deploy"),
    var_file: Path = typer.Option(None, help="tfvars file (e.g. envs/dev.tfvars)"),
    yes: bool = typer.Option(False, "--yes", help="Human confirmation gate: required to run apply"),
    plan_only: bool = typer.Option(False, help="Stop after producing the plan"),
) -> None:
    """Run init + plan, and apply only behind the explicit --yes human gate."""
    tf = _terraform_bin()
    target = target.expanduser().resolve()
    if tf is None:
        Outcome("deploy", Status.NOT_CONFIGURED, {}, FailureCode.TERRAFORM_MISSING).emit()
        return
    if not target.is_dir():
        Outcome("deploy", Status.FAIL, {"target": str(target)}, FailureCode.TARGET_MISSING).emit()
        return

    steps: list[dict] = []

    def step(name: str, cmd: list[str], timeout: int) -> bool:
        try:
            proc = _run(cmd, cwd=target, timeout=timeout)
        except subprocess.TimeoutExpired:
            steps.append({"step": name, "ok": False, "error": "timeout"})
            return False
        steps.append(
            {
                "step": name,
                "ok": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stderr_tail": proc.stderr.strip()[-2000:],
            }
        )
        return proc.returncode == 0

    if not step("init", [tf, "init", "-input=false"], SUBPROCESS_TIMEOUT_S):
        Outcome("deploy", Status.FAIL, {"steps": steps}, FailureCode.SUBPROCESS_FAILED).emit()
        return
    plan_path = target / "deploy.tfplan"
    plan_cmd = [tf, "plan", "-input=false", "-out", str(plan_path)]
    if var_file is not None:
        plan_cmd += ["-var-file", str(var_file.expanduser().resolve())]
    if not step("plan", plan_cmd, PLAN_TIMEOUT_S):
        Outcome("deploy", Status.FAIL, {"steps": steps}, FailureCode.SUBPROCESS_FAILED).emit()
        return
    if plan_only or not yes:
        code = None if plan_only else FailureCode.APPLY_NOT_CONFIRMED
        status = Status.PASS if plan_only else Status.FAIL
        detail = {
            "steps": steps,
            "plan_file": str(plan_path),
            "next": f"review the plan, then re-run with --yes to apply: ./run.sh deploy {target} --yes",
        }
        Outcome("deploy", status, detail, code).emit()
        return
    if not plan_path.is_file():
        Outcome("deploy", Status.FAIL, {"steps": steps}, FailureCode.PLAN_FILE_MISSING).emit()
        return
    ok = step("apply", [tf, "apply", "-input=false", str(plan_path)], APPLY_TIMEOUT_S)
    Outcome(
        "deploy",
        Status.PASS if ok else Status.FAIL,
        {"steps": steps, "plan_file": str(plan_path)},
        None if ok else FailureCode.SUBPROCESS_FAILED,
    ).emit()


def main() -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    app()


if __name__ == "__main__":
    main()
